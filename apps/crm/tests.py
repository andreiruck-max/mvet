import io
import zipfile
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction, DatabaseError
from django.urls import reverse
from django.utils import timezone
from apps.core.models import Company
from . import services as s, importing
from .models import Contact, Interaction, RecurrenceRule, InactivationRequest, ContactEvent

class Fixture:
    def setUp(self):
        Company.objects.get_or_create(pk=1)
        self.master=User.objects.create_superuser('master_crm','', 'test-only-password')
        self.worker=User.objects.create_user('commercial_one',password='test-only-password')
        self.other=User.objects.create_user('commercial_two',password='test-only-password')
        permission=Permission.objects.get(codename='operate_crm',content_type__app_label='core')
        self.worker.user_permissions.add(permission);self.other.user_permissions.add(permission)
        self.today=timezone.localdate();self.now=timezone.now().replace(second=0,microsecond=0)
        from .choices import RESULTS, DEFAULT_DAYS
        for result,label in RESULTS:RecurrenceRule.objects.get_or_create(result=result,defaults={'days':DEFAULT_DAYS.get(result,7),'allow_manual':result!='OPT_OUT'})
    def contact(self,**kwargs):
        return s.save_contact(actor=self.worker,data={'name':'Contato de teste','phone':'(45) 99999-0123',**kwargs})
    def data(self,**kwargs):
        return dict(occurred_at=self.now,channel='WHATSAPP',kind='ATTEMPT',sent='  Texto enviado\nexato  ',received='',read_state='UNKNOWN',result='NO_REPLY',internal_note='Contexto interno',**kwargs) if not kwargs else {**self.data(),**kwargs}
    def record(self,obj,**kwargs):
        return s.record(actor=self.worker,pk=obj.pk,revision=obj.revision,key=uuid4(),data=self.data(**kwargs))

class CRMTests(Fixture,TestCase):
    def test_simple_contact_phone_and_duplicate(self):
        obj=self.contact();self.assertEqual(obj.phone,'5545999990123');self.assertEqual(obj.next_date,self.today)
        with self.assertRaises(ValidationError):self.contact(phone='45999990123')
        with self.assertRaises(ValidationError):self.contact(phone='')
        email=self.contact(phone='',email='TEST@EXAMPLE.COM');self.assertEqual(email.email,'test@example.com')
        with self.assertRaises(ValidationError):self.contact(phone='',email='test@example.com')
        self.assertEqual(Contact.objects.count(),2)

    def test_wallet_permission_all_endpoints_and_master(self):
        obj=self.contact();self.client.force_login(self.other)
        for name in ['crm_detail','crm_edit','crm_interaction']:
            self.assertEqual(self.client.get(reverse(name,args=[obj.pk])).status_code,404)
            self.assertEqual(self.client.post(reverse(name,args=[obj.pk]),{}).status_code,405 if name=='crm_detail' else 404)
        self.assertEqual(self.client.get(reverse('crm_state',args=[obj.pk,'pause'])).status_code,404)
        response=self.client.get(reverse('crm_contacts'));self.assertNotContains(response,obj.name)
        for name in ['crm_rules','crm_report','crm_import','crm_approvals']:
            self.assertEqual(self.client.get(reverse(name)).status_code,403)
        with self.assertRaises(PermissionDenied):s.save_contact(actor=self.worker,data={'name':'Other','email':'another@example.com','owner':self.other})
        self.client.force_login(self.master)
        self.assertContains(self.client.get(reverse('crm_contacts')),obj.name)
        self.assertEqual(self.client.get(reverse('crm_report')).status_code,200)

    def test_recurrence_history_waiting_and_opt_out(self):
        obj=self.contact();item=self.record(obj)
        obj.refresh_from_db();self.assertEqual(obj.next_date,self.today+timedelta(days=7))
        self.assertEqual(item.sent,'  Texto enviado\nexato  ');self.assertEqual(item.read_state,'UNKNOWN')
        item=self.record(obj,result='WAITING');obj.refresh_from_db()
        self.assertEqual(obj.state,'WAITING');self.assertEqual(obj.next_date,self.today+timedelta(days=3))
        self.record(obj,result='OPT_OUT');obj.refresh_from_db()
        self.assertEqual(obj.state,'DNC');self.assertIsNone(obj.next_date);self.assertEqual(obj.whatsapp_url,'')
        with self.assertRaises(ValidationError):self.record(obj)
        self.assertEqual(obj.interactions.count(),3)

    def test_rule_manual_permission_and_pause_due(self):
        obj=self.contact();rule=RecurrenceRule.objects.get(result='NO_REPLY');rule.allow_manual=False;rule.save()
        with self.assertRaises(ValidationError):self.record(obj,next_date=self.today+timedelta(days=2))
        self.record(obj);obj.refresh_from_db()
        with self.assertRaises(ValidationError):s.change_state(actor=self.worker,pk=obj.pk,revision=obj.revision,action='reschedule',date=self.today,justification='Retorno')
        rule.allow_manual=True;rule.save()
        s.change_state(actor=self.worker,pk=obj.pk,revision=obj.revision,action='pause',date=self.today+timedelta(days=40),justification='Após safra')
        self.client.force_login(self.worker)
        self.assertNotContains(self.client.get(reverse('crm_queue')),obj.name)
        with patch('django.utils.timezone.localdate',return_value=self.today+timedelta(days=40)):
            self.assertContains(self.client.get(reverse('crm_queue')),obj.name)

    def test_request_reject_approve_reactivate_and_dnc(self):
        obj=self.contact();s.change_state(actor=self.worker,pk=obj.pk,revision=obj.revision,action='request',reason='NO_REPLY',justification='Várias tentativas')
        req=InactivationRequest.objects.get();obj.refresh_from_db();self.assertEqual(obj.state,'APPROVAL')
        with self.assertRaises(PermissionDenied):s.decide(actor=self.worker,request_id=req.pk,approve=True)
        s.decide(actor=self.master,request_id=req.pk,approve=False,date=self.today+timedelta(days=3),note='Tentar novamente')
        obj.refresh_from_db();self.assertEqual(obj.state,'ACTIVE')
        s.change_state(actor=self.worker,pk=obj.pk,revision=obj.revision,action='request',reason='OUTSIDE',justification='Perfil distinto')
        req=InactivationRequest.objects.get(decision='PENDING');s.decide(actor=self.master,request_id=req.pk,approve=True)
        obj.refresh_from_db();self.assertEqual(obj.state,'INACTIVE')
        s.change_state(actor=self.master,pk=obj.pk,revision=obj.revision,action='reactivate',date=self.today,owner=self.other,justification='Novo interesse')
        obj.refresh_from_db();self.assertEqual(obj.owner,self.other);self.assertEqual(obj.next_date,self.today)
        s.change_state(actor=self.other,pk=obj.pk,revision=obj.revision,action='dnc',justification='Pedido explícito por telefone')
        obj.refresh_from_db();self.assertEqual(obj.state,'DNC')

    def test_stale_revision_idempotency_and_date_validation(self):
        obj=self.contact();key=uuid4();first=s.record(actor=self.worker,pk=obj.pk,revision=obj.revision,key=key,data=self.data())
        second=s.record(actor=self.worker,pk=obj.pk,revision=obj.revision,key=key,data=self.data());self.assertEqual(first.pk,second.pk)
        with self.assertRaises(ValidationError):s.record(actor=self.worker,pk=obj.pk,revision=obj.revision,key=key,data=self.data(sent='Changed'))
        with self.assertRaises(ValidationError):s.save_contact(actor=self.worker,pk=obj.pk,revision=obj.revision,data={'name':'Changed'})
        obj.refresh_from_db()
        with self.assertRaises(ValidationError):self.record(obj,occurred_at=self.now+timedelta(days=1))
        with self.assertRaises(ValidationError):self.record(obj,next_date=self.today-timedelta(days=1))

    def test_csv_preview_commit_duplicates_no_overwrite_and_repeat(self):
        self.contact()
        upload=SimpleUploadedFile('contacts.csv','nome;telefone;email;cidade;segmento;responsavel\nDuplicado;45999990123;;;;\nContato novo;;new@example.com;Cidade;Suinocultura;commercial_two\nRepetido;;new@example.com;;;\nSem contato;;;;;\n'.encode())
        batch=importing.preview(actor=self.master,upload=upload,owner=self.worker,first_date=self.today)
        self.assertEqual(Contact.objects.count(),1);self.assertEqual(sum(not row['error'] for row in batch.rows),1)
        batch=importing.commit(actor=self.master,batch_id=batch.pk);self.assertEqual(Contact.objects.count(),2)
        self.assertEqual(Contact.objects.get(email='new@example.com').owner,self.other)
        importing.commit(actor=self.master,batch_id=batch.pk);self.assertEqual(Contact.objects.count(),2)
        self.assertEqual(len(batch.report),4)

    def test_xlsx_values_and_formula_rejected(self):
        def upload(formula=''):
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as archive:archive.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>nome</t></is></c><c r="B1" t="inlineStr"><is><t>email</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>Contato XLSX</t></is>{formula}</c><c r="B2" t="inlineStr"><is><t>xlsx@example.com</t></is></c></row></sheetData></worksheet>')
            return SimpleUploadedFile('contacts.xlsx',buf.getvalue())
        batch=importing.preview(actor=self.master,upload=upload(),owner=self.worker,first_date=self.today)
        self.assertFalse(batch.rows[0]['error']);importing.commit(actor=self.master,batch_id=batch.pk)
        with self.assertRaises(ValidationError):importing.read_rows(upload('<f>1+1</f>'))
        with self.assertRaises(ValidationError):importing.read_rows(SimpleUploadedFile('empty.csv',b''))

    def test_import_revalidates_new_duplicate_at_commit(self):
        batch=importing.preview(actor=self.master,upload=SimpleUploadedFile('x.csv',b'nome,email\nImported,late@example.com'),owner=self.worker,first_date=self.today)
        self.contact(phone='',email='late@example.com')
        result=importing.commit(actor=self.master,batch_id=batch.pk)
        self.assertIn('error',result.report[0]);self.assertEqual(Contact.objects.count(),1)

    def test_forms_render_and_phone_search(self):
        obj=self.contact();self.client.force_login(self.worker)
        for name,args in [('crm_queue',[]),('crm_contacts',[]),('crm_new',[]),('crm_detail',[obj.pk]),('crm_edit',[obj.pk]),('crm_interaction',[obj.pk]),('crm_state',[obj.pk,'pause'])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200,name)
        self.assertContains(self.client.get(reverse('crm_contacts'),{'q':'(45) 99999-0123'}),obj.name)
        self.client.force_login(self.master)
        for name in ['crm_report','crm_rules','crm_approvals','crm_import']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200,name)

    def test_pg_history_and_schedule_constraints(self):
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL trigger verification')
        obj=self.contact();item=self.record(obj)
        for queryset,data in [(Interaction.objects.filter(pk=item.pk),{'sent':'Changed'}),(ContactEvent.objects.filter(contact=obj),{'note':'Changed'}),(Contact.objects.filter(pk=obj.pk),{'next_date':None})]:
            with self.assertRaises(DatabaseError),transaction.atomic():queryset.update(**data)
