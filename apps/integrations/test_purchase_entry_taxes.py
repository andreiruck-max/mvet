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
        self.assertEqual([line.landed_unit_cost for line in lines],
            list(map(D,('166.800000','475.440000','88.943333','29.166000','78.580000','227.560000','34.820000'))))
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

    def test_credit_preserved_on_edit_without_required_attestation(self):
        from uuid import uuid4
        invoice=self.stage_invoice()
        treatments=[dict(mode='STOCK',discount=D(r[3]),ncm=r[5],ipi=D(r[4]),recoverable_tax=D('10') if i==0 else D(0)) for i,r in enumerate(ROWS)]
        p=self.import_note(invoice,treatments=treatments)
        self.assertEqual(p.total,D('3760.24'))
        self.assertEqual(p.acquisition_total,D('4295.78'))
        lines=[{k:getattr(i,k) for k in ('product_id','quantity','unit_cost','discount','ncm','ipi','st','difal','invoice_st','invoice_other_tax','recoverable_tax','fiscal_components')} for i in p.items.all()]
        p=purchases.save_draft(actor=self.actor,key=uuid4(),purchase_id=p.pk,revision=p.revision,
            data={k:getattr(p,k) for k in purchases.FIELDS},items=lines,
            installments=[(i.due_date,i.amount,i.notes) for i in p.installments.all()])
        self.assertEqual(p.items.first().recoverable_tax,D('10'))
        self.assertEqual(p.acquisition_total,D('4295.78'))
        purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)

    def test_xml_fields_and_unresolved_2374_difference_block_import(self):
        from .xml_discounts import extract
        items=[];details=[]
        for idx,(sku,qty,unit,discount,ipi,ncm,_) in enumerate(ROWS,1):
            gross=D(qty)*D(unit)
            items.append(dict(codigo=sku,descricao=sku,unidade='UN',quantidade=str(qty),valor=unit,tipo='P',cfop='6101'))
            details.append(f'<det nItem="{idx}"><prod><cProd>{sku}</cProd><NCM>{ncm}</NCM><CFOP>6101</CFOP><qCom>{qty}</qCom><vUnCom>{unit}</vUnCom><vProd>{gross}</vProd><vDesc>{discount}</vDesc></prod><imposto><IPI><IPITrib><vIPI>{ipi}</vIPI></IPITrib></IPI></imposto></det>')
        data=incoming(itens=items,valorNota='3760.24')
        raw=f'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe Id="NFe{data["chaveAcesso"]}">{"".join(details)}<total><ICMSTot><vProd>3736.50</vProd><vDesc>186.82</vDesc><vIPI>210.56</vIPI><vNF>3760.24</vNF></ICMSTot></total></infNFe></NFe>'.encode()
        enriched=extract(raw,data)
        self.assertEqual(enriched['tax_items'][0]['ncm'],'85437092')
        self.assertEqual(enriched['tax_items'][0]['ipi'],'43.42')
        self.assertEqual(enriched['fiscal']['difference'],'0.00')
        valid_data = dict(data,_xml_discounts=enriched)
        correct=service.stage(actor=self.actor,connection=self.connection,payload=valid_data)
        self.assertEqual(correct.source['items'][0]['fiscal_components']['cfop'],'6101')
        data['valorNota']='3783.98'
        data['_xml_discounts']=extract(raw.replace(b'<vNF>3760.24',b'<vNF>3783.98'),data)
        row=service.stage(actor=self.actor,connection=self.connection,payload=data)
        with self.assertRaisesMessage(ValidationError,'23,74'):self.import_note(row)
        self.assertFalse(self.supplier.purchases.exists())
        del data['_xml_discounts']
        sticky=service.stage(actor=self.actor,connection=self.connection,payload=data)
        with self.assertRaisesMessage(ValidationError,'23,74'): self.import_note(sticky)
        restored=service.stage(actor=self.actor,connection=self.connection,payload=valid_data)
        p=self.import_note(restored)
        self.assertEqual((p.total,p.acquisition_total),(D('3760.24'),D('4305.78')))

    def test_imported_draft_cannot_change_supplier_fiscal_total(self):
        from uuid import uuid4
        p=self.import_note(self.stage_invoice())
        lines=[dict(product_id=i.product_id,quantity=i.quantity,unit_cost=i.unit_cost,discount=i.discount,ncm=i.ncm,ipi=i.ipi,st=i.st,difal=i.difal) for i in p.items.all()]
        data={k:getattr(p,k) for k in purchases.FIELDS};data['other_costs']=D('23.74')
        with self.assertRaises(ValidationError):
            purchases.save_draft(actor=self.actor,key=uuid4(),purchase_id=p.pk,revision=p.revision,data=data,items=lines,installments=[])

    def test_confirmed_tax_fields_are_immutable_in_postgres(self):
        from django.db import connection, transaction, DatabaseError
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL trigger')
        p=self.import_note(self.stage_invoice())
        purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        for field in ('ipi','st','difal','invoice_st','invoice_other_tax','recoverable_tax'):
            with self.subTest(field=field),self.assertRaises(DatabaseError),transaction.atomic():
                p.items.update(**{field:D('1')})

    def test_preview_rolls_back_and_requires_purchase_permission(self):
        from django.urls import reverse
        from apps.purchases.models import Purchase
        invoice=self.stage_invoice()
        self.client.force_login(self.actor)
        data=dict(revision=invoice.revision,supplier=self.supplier.pk,location=self.location.pk,
            discount='0',freight='0',other_costs='0',acquisition_kind='NORMAL',
            action='preview',st_by_ncm='85437092=510,82\n85354010=23,52',difal_by_ncm='73121090=11,20')
        data.update({'products-TOTAL_FORMS':7,'products-INITIAL_FORMS':7,'installments-TOTAL_FORMS':0,'installments-INITIAL_FORMS':0})
        for idx,(product,row) in enumerate(zip(self.products,ROWS)):
            data.update({f'products-{idx}-product':product.pk,f'products-{idx}-mode':'STOCK',f'products-{idx}-discount':row[3].replace('.',','),f'products-{idx}-ncm':row[5],f'products-{idx}-ipi':row[4].replace('.',',')})
        response=self.client.post(reverse('bling_purchase_detail',args=[invoice.pk]),data)
        self.assertContains(response,'4.305,78')
        self.assertFalse(Purchase.objects.exists())
        self.assertFalse(FinancialTitle.objects.exists())
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(reverse('bling_purchase_detail',args=[invoice.pk]),data).status_code,403)

    def test_xml_direct_costs_and_internal_st_not_spread_across_other_line(self):
        from uuid import uuid4
        lines=[dict(product_id=p.pk,quantity=D('1'),unit_cost=D('100'),invoice_st=D('30') if idx==0 else D('0'),
            fiscal_components={'freight':'10'} if idx==0 else {}) for idx,p in enumerate(self.products[:2])]
        data=dict(supplier=self.supplier,document='DIRECT',series='',date=timezone.localdate(),location=self.location,
            discount=D(0),freight=D('10'),other_costs=D(0),notes='')
        p=purchases.save_draft(actor=self.actor,key=uuid4(),data=data,items=lines,installments=[])
        self.assertEqual(p.total,D('240'))
        self.assertEqual(list(p.items.values_list('allocated_total',flat=True)),[D('140'),D('100')])

    def test_bonus_keeps_fiscal_ipi_but_zero_inventory_value_and_no_payables(self):
        from uuid import uuid4
        data=dict(supplier=self.supplier,document='BONUS-IPI',series='',date=timezone.localdate(),location=self.location,
            discount=D(0),freight=D(0),other_costs=D(0),notes='',acquisition_kind='BONUS')
        p=purchases.save_draft(actor=self.actor,key=uuid4(),data=data,
            items=[dict(product_id=self.product.pk,quantity=D(1),unit_cost=D(100),ipi=D(10))],installments=[])
        self.assertEqual(p.total,0)
        self.assertEqual(p.items.get().ipi,10)
        self.assertEqual(p.items.get().allocated_total,0)
        p=purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        purchases.receive(actor=self.actor,purchase_id=p.pk,revision=p.revision,date=timezone.localdate())
        self.assertFalse(FinancialTitle.objects.exists())

    def test_received_cost_does_not_rewrite_existing_sale_cmv(self):
        sale=self.confirmed()
        original=sale.cmv
        self.products[0]=self.product
        p=self.import_note(self.stage_invoice())
        p=purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        purchases.receive(actor=self.actor,purchase_id=p.pk,revision=p.revision,date=timezone.localdate())
        sale.refresh_from_db()
        self.assertEqual(sale.cmv,original)


from django.test import SimpleTestCase


class NcmAllocationTests(SimpleTestCase):
    def test_zebu_distributes_only_inside_each_ncm_and_is_exact_to_the_cent(self):
        items=[{'ncm':ncm,'net_basis':D(qty)*D(unit)-D(discount),'st':D(0),'difal':D(0)}
               for _,qty,unit,discount,_,ncm,_ in ROWS]
        service.allocate_ncm_taxes(items,service.parse_ncm_taxes('85437092=510,82\n85354010=23,52','ST'),'st')
        service.allocate_ncm_taxes(items,service.parse_ncm_taxes('73121090=11,20','DIFAL'),'difal')
        landed=[i['net_basis']+D(row[4])+i['st']+i['difal'] for i,row in zip(items,ROWS)]
        self.assertEqual(landed,[D(row[6]) for row in ROWS])
        self.assertEqual(sum(landed),D('4305.78'))
        self.assertEqual([i['st'] for i in items[:3]],list(map(D,('122.49','349.14','39.19'))))

    def test_invalid_grouping_and_zero_basis_do_not_create_a_charge(self):
        for wrong in ('85437092=1.2.3,45','85437092=1e2','85437092=-12,30'):
            with self.subTest(wrong=wrong),self.assertRaises(ValidationError):
                service.parse_ncm_taxes(wrong,'ST')
        with self.assertRaises(ValidationError):
            service.allocate_ncm_taxes([{'ncm':'85437092','net_basis':D(0)}],{'85437092':D(1)},'st')
