from datetime import datetime, timedelta, time
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import Interaction, Contact


class ActivityReportTests(Fixture, TestCase):
    def activity(self, contact, actor=None, when=None, **changes):
        return Interaction.objects.create(contact=contact, actor=actor or self.worker,
            occurred_at=when or self.now, channel='WHATSAPP', kind='ATTEMPT',
            result=changes.pop('result', 'NO_REPLY'), sent=changes.pop('sent', 'Mensagem sintética'), **changes)

    def report(self, **params):
        self.client.force_login(self.master)
        return self.client.get(reverse('crm_report'), params)

    def test_author_filter_survives_reassignment_and_inactivation(self):
        contact=self.contact()
        first=self.activity(contact)
        self.activity(contact,actor=self.other)
        Contact.objects.filter(pk=contact.pk).update(owner=self.other)
        self.worker.is_active=False;self.worker.save(update_fields=['is_active'])
        response=self.report(performed_by=self.worker.pk,period='today')
        self.assertEqual(response.context['metrics']['period'],1)
        self.assertEqual(list(response.context['page']),[first])
        self.assertContains(response,'Mensagem sintética')
        self.assertEqual(response.context['activity_owners'][0]['actor__username'],self.worker.username)
        self.assertEqual(response.context['form'].fields['owner'].label,'Responsável atual da carteira')

    def test_dates_results_and_counts_use_historical_activity(self):
        contact=self.contact()
        yesterday=self.now-timedelta(days=1)
        past=self.activity(contact,when=yesterday,result='NO_REPLY')
        self.activity(contact,result='WAITING')
        Contact.objects.filter(pk=contact.pk).update(last_result='WAITING')
        response=self.report(start=yesterday.date(),end=yesterday.date(),result='NO_REPLY')
        self.assertEqual(list(response.context['page']),[past])
        self.assertEqual(response.context['metrics']['period'],1)
        self.assertEqual(response.context['metrics']['today'],0)
        self.assertContains(response,'Nenhuma atividade',count=0)
        response=self.report(period='yesterday',start=self.today,end=self.today)
        self.assertEqual(list(response.context['page']),[past])
        self.assertEqual(response.context['form']['start'].value(),yesterday.date().isoformat())

    def test_pagination_totals_escaping_and_permissions(self):
        contact=self.contact()
        for _ in range(31):self.activity(contact,sent='<script>alert(1)</script>')
        response=self.report(performed_by=self.worker.pk,period='today')
        self.assertEqual(len(response.context['page']),30)
        self.assertEqual(response.context['metrics']['period'],31)
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'performed_by='+str(self.worker.pk))
        second=self.report(performed_by=self.worker.pk,period='today',page=2)
        self.assertEqual(len(second.context['page']),1)
        self.client.force_login(self.worker)
        self.assertEqual(self.client.get(reverse('crm_report')).status_code,403)
        self.assertEqual(self.report(start=self.today,end=self.today-timedelta(days=1)).status_code,400)

    @override_settings(TIME_ZONE='America/Sao_Paulo')
    def test_local_day_boundaries(self):
        contact=self.contact()
        midnight=timezone.make_aware(datetime.combine(self.today,time.min))
        before=self.activity(contact,when=midnight-timedelta(seconds=1))
        at=self.activity(contact,when=midnight)
        response=self.report(start=self.today,end=self.today)
        self.assertEqual(list(response.context['page']),[at])
        response=self.report(start=self.today-timedelta(days=1),end=self.today-timedelta(days=1))
        self.assertEqual(list(response.context['page']),[before])
