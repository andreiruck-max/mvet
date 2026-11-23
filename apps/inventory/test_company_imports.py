from decimal import Decimal as D
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from apps.accounts.company_context import CompanyScope
from .counting import count_snapshot, apply_count, SALT
from .importing import load_opening
from .location_import import load_snapshot
from .reconciliation import reconcile
from .models import StockOperation, StockMovement
from .tests import StockFixtures


class StockImportScopeTests(StockFixtures, TestCase):
    def test_preview_and_commit_deny_group_before_reading_file(self):
        self.actor._mvet_company_scope = CompanyScope((1,),group=True)
        for commit in [False, True]:
            with self.subTest(commit=commit):
                with self.assertRaises(PermissionDenied):
                    load_opening(actor=self.actor,path='not-read.xlsx',location_name='Loja',commit=commit)
                with self.assertRaises(PermissionDenied):
                    load_snapshot(actor=self.actor,path='not-read.json',commit=commit)
                with self.assertRaises(PermissionDenied):
                    reconcile(actor=self.actor,raw='not-parsed',commit=commit)
        self.assertFalse(StockOperation.objects.exists())

    def test_secondary_preview_does_not_read_primary_history(self):
        with self.assertRaises(PermissionDenied):
            reconcile(actor=self.actor,raw='not-parsed',company_id=2)
        with self.assertRaises(PermissionDenied):
            count_snapshot(self.actor,self.p,self.loc,company_id=2)

    def test_count_binds_company_and_keeps_legacy_primary_token(self):
        self.op()
        token=count_snapshot(self.actor,self.p,self.loc)
        data=signing.loads(token,salt=SALT)
        self.assertEqual(data['company'],1)
        args=dict(actor=self.actor,product_id=self.p.pk,location_id=self.loc.pk,
            counted=D('10'),reason='Conferência')
        data['company']=2
        with self.assertRaises(ValidationError):
            apply_count(snapshot=signing.dumps(data,salt=SALT),**args)
        # Previously issued signed primary tokens remain usable for their 24-hour lifetime.
        del data['company']
        legacy=signing.dumps(data,salt=SALT)
        result=apply_count(snapshot=legacy,**args)
        self.assertEqual(result['company'],1)
        self.assertIsNone(result['operation'])
        self.actor._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            apply_count(snapshot=legacy,**args)
        self.assertEqual(StockMovement.objects.count(),1)
