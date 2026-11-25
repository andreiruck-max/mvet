from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from apps.core.models import Company
from apps.commissions.models import Payee
from .models import SalesChannel
from .forms import SaleForm, CorrectionForm
from .tests import Fixture


class IndependentChannelTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        self.secondary=SalesChannel.objects.create(company_id=2,name=self.channel.name)

    def test_same_name_allowed_only_across_owners(self):
        self.assertNotEqual(self.secondary.pk,self.channel.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesChannel.objects.create(company_id=2,name=self.channel.name)

    def test_sale_and_correction_choices_exclude_other_company(self):
        sale=self.confirmed()
        self.assertNotIn(self.secondary,SaleForm(actor=self.actor).fields['channel'].queryset)
        self.assertNotIn(self.secondary,CorrectionForm(instance=sale).fields['channel'].queryset)
        self.client.force_login(self.actor)
        response=self.client.get(reverse('sales_configuration',args=['canais']))
        self.assertNotIn(self.secondary,[row for row in response.context['page']])
        target=reverse('sales_configuration_edit',args=['canais',self.secondary.pk])
        self.assertEqual(self.client.get(target).status_code,404)
        self.assertEqual(self.client.post(target,{}).status_code,404)

    def test_correction_cannot_accept_foreign_channel_id(self):
        from .corrections import correct_sale, FIELDS
        sale=self.confirmed()
        original=(sale.channel_id,sale.revision,sale.stock_operation_id)
        with self.assertRaises(ValidationError):
            correct_sale(actor=self.actor,sale_id=sale.pk,revision=sale.revision,
                         key=uuid4(),reason='Teste de isolamento do canal',
                         values={field:getattr(sale,field) for field in FIELDS},
                         channel_id=self.secondary.pk)
        sale.refresh_from_db()
        self.assertEqual((sale.channel_id,sale.revision,sale.stock_operation_id),original)
        with self.assertRaises(ValidationError):
            SaleForm(actor=self.actor).fields['channel'].clean(self.secondary.pk)

    def test_database_rejects_owner_change_or_foreign_payee(self):
        with self.assertRaisesMessage(DatabaseError,'Sales channel owner is immutable'), transaction.atomic():
            SalesChannel.objects.filter(pk=self.channel.pk).update(company_id=2)
        payee=Payee.objects.create(name='Comissionado primário sintético')
        with self.assertRaisesMessage(DatabaseError,'another company'), transaction.atomic():
            SalesChannel.objects.filter(pk=self.secondary.pk).update(commission_payee=payee)
