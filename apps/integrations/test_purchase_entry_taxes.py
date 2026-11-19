"""Regression of invoice 163303 composition (synthetic counterparty/IDs)."""
from datetime import timedelta
from decimal import Decimal as D
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.products.models import Product
from apps.purchases.models import Supplier
from apps.purchases import services as purchases
from apps.finance.models import FinancialEntry, FinancialTitle
from apps.inventory.models import StockMovement
from .models import BlingConnection
from .tests import ISSUER
from .test_purchase_import import SUPPLIER, incoming
from . import purchase_services as service


# Qty, unit price, line discount, IPI included in invoice, NCM, landed value.
ROWS = [
    ('ZK50', 5, '140.65', '35.16', '43.42', '85437092', '834.00'),
    ('ZK200', 5, '400.90', '100.22', '123.78', '85437092', '2377.20'),
    ('PPCR', 3, '75.00', '11.25', '13.89', '85437092', '266.83'),
    ('RAIO', 5, '25.75', '6.44', '0.00', '85354010', '145.83'),
    ('FIO', 2, '70.00', '7.00', '12.96', '73121090', '157.16'),
    ('ARAME', 2, '232.00', '23.20', '14.32', '72172090', '455.12'),
    ('PORTEIRA', 2, '35.50', '3.55', '2.19', '84369900', '69.64'),
]


class PurchaseEntryTaxTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection=BlingConnection.objects.create(pk=1,issuer=ISSUER,tokens='synthetic')
        self.supplier=Supplier.objects.create(legal_name='Fornecedor de teste',document=SUPPLIER)
        self.products=[Product.objects.create(sku=sku,name=sku) for sku,*_ in ROWS]

    def stage_invoice(self):
        items=[]
        for sku,qty,unit,discount,ipi,ncm,_ in ROWS:
            items.append(dict(codigo=sku,descricao=sku,unidade='UN',quantidade=str(qty),
                valor=unit,tipo='P',cfop='6101'))
        enriched={'total':'186.82','items':[row[3] for row in ROWS],
                  'tax_items':[{'ncm':row[5],'ipi':row[4]} for row in ROWS]}
        return service.stage(actor=self.actor,connection=self.connection,
            payload=incoming(itens=items,valorNota='3760.24',_xml_discounts=enriched))

    def import_note(self, row, **kwargs):
        terms=[(timezone.localdate()+timedelta(days=i+1),amount,'') for i,amount in
            enumerate((D('903.16'),D('952.36'),D('952.36'),D('952.36')))]
        treatments=[dict(mode='STOCK',discount=D(r[3]),ncm=r[5],ipi=D(r[4])) for r in ROWS]
        data=dict(actor=self.actor,invoice_id=row.pk,revision=row.revision,supplier=self.supplier,
            location=self.location,products=self.products,discount=D('0'),freight=D('0'),
            external_freight=D('0'),other_costs=D('0'),installments=terms,reviewed=True,
            treatments=treatments,st_by_ncm='85437092=510,82\n85354010=23,52',
            difal_by_ncm='73121090=11,20')
        data.update(kwargs)
        return service.create_draft(**data)

    def test_zebu_multiple_lines_share_st_by_value_not_quantity(self):
        before_movements=StockMovement.objects.count()
        invoice=self.stage_invoice()
        purchase=self.import_note(invoice)
        lines=list(purchase.items.order_by('pk'))
        self.assertEqual(purchase.products_total,D('3736.50'))
        self.assertEqual(purchase.item_discounts,D('186.82'))
        self.assertEqual(sum((x.ipi for x in lines),D(0)),D('210.56'))
        self.assertEqual(purchase.total,D('3760.24'))  # Supplier, includes IPI, excludes ST/DIFAL.
        self.assertEqual(purchase.external_tax_total,D('545.54'))
        self.assertEqual(purchase.acquisition_total,D('4305.78'))
        self.assertEqual([line.st for line in lines[:4]],
            [D('122.49'),D('349.14'),D('39.19'),D('23.52')])
        self.assertEqual(lines[4].difal,D('11.20'))
        self.assertEqual([line.allocated_total for line in lines],
            [D(row[6]) for row in ROWS])
        self.assertEqual([line.landed_unit_cost for line in lines[:3]],
            [D('166.800000'),D('475.440000'),D('88.943333')])
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertEqual(StockMovement.objects.count(),before_movements)

        purchase=purchases.confirm(actor=self.actor,purchase_id=purchase.pk,revision=purchase.revision)
        self.assertEqual(FinancialTitle.objects.count(),4)
        self.assertEqual(sum(FinancialTitle.objects.values_list('amount',flat=True)),D('3760.24'))
        self.assertFalse(FinancialEntry.objects.exists())
        purchase=purchases.receive(actor=self.actor,purchase_id=purchase.pk,
            revision=purchase.revision,date=timezone.localdate())
        self.assertEqual(sum(purchase.receipt.movements.values_list('value',flat=True)),D('4305.78'))
        self.assertEqual([item.movement.value for item in purchase.items.order_by('pk')],
            [D(row[6]) for row in ROWS])

    def test_invalid_or_unknown_ncm_is_rejected_without_persistence(self):
        invoice=self.stage_invoice()
        for st,difal in [
            ('85437092=510,823','73121090=11,20'),
            ('99999999=1,00',''),
            ('85437092=10,00\n85437092=20,00',''),
            ('85437092:510,82',''),
        ]:
            with self.subTest(st=st), self.assertRaises(ValidationError):
                self.import_note(invoice,st_by_ncm=st,difal_by_ncm=difal)
        self.assertFalse(self.supplier.purchases.exists())

    def test_validated_xml_ncm_is_used_when_review_field_is_blank(self):
        invoice=self.stage_invoice()
        treatments=[dict(mode='STOCK',discount=D(r[3]),ipi=D(r[4]),ncm='') for r in ROWS]
        # XML NCM is authoritative even if UI input is missing: derive from validated source.
        purchase=self.import_note(invoice,treatments=treatments)
        self.assertEqual(purchase.items.count(),7)
