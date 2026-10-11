from datetime import timedelta
from unittest.mock import patch
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.db import connection, connections, close_old_connections, transaction, DatabaseError
from django.core.exceptions import PermissionDenied, ValidationError
from django.apps import apps
from .tests import Fixture
from .models import Contact, FirstContactRelease
from . import intake, services


class IntakeTests(Fixture,TestCase):
    def pool(self,n=10):
        return [self.contact(phone='',email=f'person{i}@example.com',name=f'Pessoa {i}') for i in range(n)]

    def config(self,limit=3,paused=False,starts_on=None):
        return intake.configure(actor=self.master,daily_limit=limit,paused=paused,starts_on=starts_on or self.today,revision=intake.settings().revision)

    def test_random_cap_stable_refresh_and_next_day_without_catchup(self):
        people=self.pool();self.config()
        chosen=[p.pk for p in people[-3:]]
        with patch('apps.crm.intake.random.SystemRandom.sample',return_value=chosen) as sample:
            self.assertEqual(intake.release_today(actor=self.worker),3)
        sample.assert_called_once()
        self.assertEqual(set(FirstContactRelease.objects.values_list('contact_id',flat=True)),set(chosen))
        self.assertEqual(intake.release_today(actor=self.worker),0)
        self.assertEqual(intake.release_today(actor=self.master),0)
        with patch('django.utils.timezone.localdate',return_value=self.today+timedelta(days=9)):
            self.assertEqual(intake.release_today(actor=self.worker),3)
        self.assertEqual(FirstContactRelease.objects.count(),6)
        self.assertEqual(Contact.objects.filter(awaiting_first_release=True).count(),4)

    def test_returns_and_paused_intake_are_independent(self):
        people=self.pool(7)
        self.record(people[0]);people[0].refresh_from_db()
        services.change_state(actor=self.worker,pk=people[0].pk,revision=people[0].revision,action='reschedule',date=self.today,justification='Retorno combinado')
        self.config(2)
        self.assertEqual(intake.release_today(actor=self.worker),2)
        self.config(2,paused=True)
        self.client.force_login(self.worker)
        response=self.client.get(reverse('crm_queue'))
        self.assertEqual(response.context['page'].paginator.count,3)
        self.assertContains(response,people[0].name)
        self.assertEqual(response.context['queued_count'],4)
        self.assertEqual(intake.release_today(actor=self.master),0)
        self.config(1);self.assertEqual(intake.release_today(actor=self.worker),0)
        self.config(4);self.assertEqual(intake.release_today(actor=self.worker),2)

    def test_future_eligibility_inactive_owner_and_dnc(self):
        people=self.pool(5);self.config(10)
        for i,p in enumerate(people):
            if i==0:services.change_state(actor=self.worker,pk=p.pk,revision=p.revision,action='pause',date=self.today+timedelta(days=5),justification='Depois')
            elif i==1:services.change_state(actor=self.worker,pk=p.pk,revision=p.revision,action='dnc',justification='Pedido explícito')
            elif i==2:Contact.objects.filter(pk=p.pk).update(owner=self.other)
        self.other.is_active=False;self.other.save()
        self.assertEqual(intake.release_today(actor=self.worker),2)
        with patch('django.utils.timezone.localdate',return_value=self.today+timedelta(days=5)):
            self.assertEqual(intake.release_today(actor=self.worker),1)

    def test_global_quota_does_not_leak_other_wallet_or_depend_on_filter(self):
        people=self.pool(4);Contact.objects.filter(pk__in=[p.pk for p in people[2:]]).update(owner=self.other)
        self.config(4);self.client.force_login(self.worker)
        response=self.client.get(reverse('crm_queue'),{'q':'inexistente'})
        self.assertEqual(response.context['page'].paginator.count,0)
        self.assertEqual(FirstContactRelease.objects.count(),4)
        response=self.client.get(reverse('crm_queue'))
        self.assertEqual(response.context['page'].paginator.count,2)
        for p in people[2:]:self.assertNotContains(response,p.name)
        self.assertEqual(self.client.get(reverse('crm_intake')).status_code,403)
        self.assertEqual(self.client.post(reverse('crm_intake'),{'daily_limit':100}).status_code,403)
        with self.assertRaises(PermissionDenied):intake.configure(actor=self.worker,daily_limit=5,paused=False,starts_on=self.today,revision=0)

    def test_initial_pause_and_existing_date_is_eligibility_not_overdue(self):
        people=self.pool(2);Contact.objects.filter(pk=people[0].pk).update(next_date=self.today-timedelta(days=5))
        self.client.force_login(self.worker)
        response=self.client.get(reverse('crm_queue'))
        self.assertEqual(response.context['page'].paginator.count,0)
        self.assertEqual(response.context['queued_count'],2)
        detail=self.client.get(reverse('crm_detail',args=[people[0].pk]))
        self.assertContains(detail,'Aguardando distribuição');self.assertNotContains(detail,'dias de atraso')
        self.client.force_login(self.master)
        report=self.client.get(reverse('crm_report'))
        self.assertEqual(report.context['metrics']['overdue'],0)
        self.assertEqual(report.context['metrics']['due'],0)
        self.assertEqual(report.context['metrics']['queued'],2)
        self.assertEqual(self.client.post(reverse('crm_intake'),{'daily_limit':'2','starts_on':self.today,'revision':intake.settings().revision}).status_code,302)
        self.assertEqual(intake.release_today(actor=self.worker),2)

    def test_migration_preserves_history_and_dates(self):
        people=self.pool(2);self.record(people[1]);people[1].refresh_from_db()
        original_date=people[1].next_date
        Contact.objects.filter(pk=people[1].pk).update(awaiting_first_release=True)
        import_module('apps.crm.migrations.0004_seed_intake_and_protect_releases').seed(apps,type('Editor',(),{'connection':connection})())
        people[0].refresh_from_db();people[1].refresh_from_db()
        self.assertTrue(people[0].awaiting_first_release)
        self.assertFalse(people[1].awaiting_first_release)
        self.assertEqual(people[1].next_date,original_date)

    def test_completion_does_not_refill_daily_slot_and_config_revision(self):
        self.pool(4);config=self.config(1);intake.release_today(actor=self.worker)
        obj=FirstContactRelease.objects.get().contact;self.record(obj)
        self.assertEqual(intake.release_today(actor=self.worker),0)
        self.config(1,paused=True)
        with self.assertRaises(ValidationError):intake.configure(actor=self.master,daily_limit=5,paused=False,starts_on=self.today,revision=config.revision)
        if connection.vendor=='postgresql':
            with self.assertRaises(DatabaseError),transaction.atomic():FirstContactRelease.objects.all().delete()


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL locking')
class IntakeConcurrencyTests(Fixture,TransactionTestCase):
    def test_two_requests_share_one_daily_quota(self):
        for i in range(8):self.contact(phone='',email=f'concurrent{i}@example.com')
        intake.configure(actor=self.master,daily_limit=3,paused=False,starts_on=self.today,revision=intake.settings().revision)
        def release(_):
            close_old_connections()
            try:return intake.release_today(actor=self.worker)
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(release,range(2)))
        self.assertEqual(sum(results),3)
        self.assertEqual(FirstContactRelease.objects.count(),3)
