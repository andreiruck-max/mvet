import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from apps.products.models import Product
from apps.inventory.models import StockLocation, StockOperation, StockMovement


def money(label):
    return models.DecimalField(label,max_digits=18,decimal_places=2,default=0,validators=[MinValueValidator(0)])

class Supplier(models.Model):
    legal_name=models.CharField('Razão social / nome',max_length=240)
    trade_name=models.CharField('Nome fantasia',max_length=240,blank=True)
    document=models.CharField('CNPJ / CPF',max_length=18,blank=True)
    contact=models.CharField('Contato',max_length=120,blank=True)
    phone=models.CharField('Telefone',max_length=40,blank=True)
    email=models.EmailField('E-mail',blank=True)
    notes=models.TextField('Observações',blank=True,max_length=3000)
    active=models.BooleanField('Ativo',default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['legal_name','pk']
        constraints=[models.UniqueConstraint(fields=['document'],condition=~models.Q(document=''),name='purchase_supplier_document_unique')]
    def __str__(self):return self.trade_name or self.legal_name

class Purchase(models.Model):
    key=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    fingerprint=models.CharField(max_length=64,editable=False)
    revision=models.PositiveIntegerField(default=0,editable=False)
    supplier=models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name='purchases',verbose_name='Fornecedor')
    document=models.CharField('NF / documento',max_length=60)
    series=models.CharField('Série',max_length=20,blank=True)
    date=models.DateField('Data da compra',db_index=True)
    location=models.ForeignKey(StockLocation,on_delete=models.PROTECT,verbose_name='Estoque de destino')
    discount=money('Desconto (R$)')
    freight=money('Frete de aquisição (R$)')
    other_costs=money('Outros custos de aquisição (R$)')
    products_total=money('Total dos produtos')
    total=money('Total da compra')
    notes=models.TextField('Observações',max_length=3000,blank=True)
    status=models.CharField(max_length=12,choices=[('DRAFT','Rascunho'),('ORDERED','Confirmada / a receber'),('RECEIVED','Recebida'),('CANCELLED','Cancelada')],default='DRAFT',db_index=True)
    received_date=models.DateField(null=True,editable=False)
    receipt=models.OneToOneField(StockOperation,null=True,on_delete=models.PROTECT,related_name='purchase_receipt',editable=False)
    reversal=models.OneToOneField(StockOperation,null=True,on_delete=models.PROTECT,related_name='purchase_reversal',editable=False)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='created_purchases')
    confirmed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT,related_name='confirmed_purchases')
    received_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT,related_name='received_purchases')
    cancelled_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT,related_name='cancelled_purchases')
    created_at=models.DateTimeField(auto_now_add=True)
    confirmed_at=models.DateTimeField(null=True,editable=False)
    received_at=models.DateTimeField(null=True,editable=False)
    cancelled_at=models.DateTimeField(null=True,editable=False)
    cancellation_reason=models.CharField(max_length=500,blank=True)
    source=models.CharField(max_length=40,default='manual')
    external_id=models.CharField(max_length=120,blank=True)
    class Meta:
        ordering=['-date','-pk']
        constraints=[models.UniqueConstraint(fields=['supplier','document','series'],name='purchase_unique_document'),models.CheckConstraint(condition=models.Q(discount__gte=0,freight__gte=0,other_costs__gte=0,products_total__gte=0,total__gte=0),name='purchase_nonnegative'),models.CheckConstraint(condition=models.Q(discount__lte=models.F('products_total')),name='purchase_discount_limit')]
        indexes=[models.Index(fields=['supplier','date'])]

class PurchaseItem(models.Model):
    purchase=models.ForeignKey(Purchase,on_delete=models.PROTECT,related_name='items')
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    quantity=models.DecimalField('Quantidade',max_digits=18,decimal_places=4,validators=[MinValueValidator(Decimal('0.0001'))])
    unit_cost=models.DecimalField('Preço unitário (R$)',max_digits=24,decimal_places=6,validators=[MinValueValidator(0)])
    subtotal=money('Subtotal')
    allocated_total=money('Valor incorporado ao estoque')
    landed_unit_cost=models.DecimalField(max_digits=24,decimal_places=6,default=0)
    sku_snapshot=models.CharField(max_length=60,blank=True)
    name_snapshot=models.CharField(max_length=240,blank=True)
    movement=models.OneToOneField(StockMovement,null=True,on_delete=models.PROTECT,editable=False)
    class Meta:
        ordering=['pk']
        constraints=[models.CheckConstraint(condition=models.Q(quantity__gt=0,unit_cost__gte=0,subtotal__gte=0,allocated_total__gte=0),name='purchase_item_nonnegative')]

class PurchaseInstallment(models.Model):
    purchase=models.ForeignKey(Purchase,on_delete=models.PROTECT,related_name='installments')
    number=models.PositiveIntegerField()
    due_date=models.DateField('Vencimento',db_index=True)
    amount=money('Valor (R$)')
    status=models.CharField(max_length=12,choices=[('PENDING','Pendente'),('CANCELLED','Cancelada')],default='PENDING')
    notes=models.CharField('Observação',max_length=500,blank=True)
    class Meta:
        ordering=['number','pk']
        constraints=[models.UniqueConstraint(fields=['purchase','number'],name='purchase_installment_number'),models.CheckConstraint(condition=models.Q(amount__gt=0),name='purchase_installment_positive')]
    @property
    def display_status(self):
        if self.status=='CANCELLED':return 'Cancelada'
        if self.purchase.status=='DRAFT':return 'Planejada (rascunho)'
        return 'Vencida' if self.due_date<timezone.localdate() else 'Pendente'
