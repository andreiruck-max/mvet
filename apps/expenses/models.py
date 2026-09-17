import uuid
from django.conf import settings
from django.db import models


class ChartOfAccount(models.Model):
    NATURES = [('OPERATING','Despesa operacional'),('FINANCIAL','Despesa financeira'),('ASSET','Ativo'),('LIABILITY','Passivo'),('EQUITY','Patrimônio'),('REVENUE','Receita')]
    code = models.CharField('Código', max_length=47, unique=True)
    name = models.CharField('Nome', max_length=180)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children', verbose_name='Categoria superior')
    nature = models.CharField('Natureza', max_length=12, choices=NATURES)
    postable = models.BooleanField('Aceita lançamentos', default=True)
    active = models.BooleanField('Ativa', default=True)
    class Meta:
        ordering=['code','pk']
    def __str__(self): return f'{self.code} · {self.name}'


class ClassificationRule(models.Model):
    name = models.CharField('Nome', max_length=180)
    priority = models.PositiveIntegerField('Prioridade (menor primeiro)', default=100)
    field = models.CharField('Campo', max_length=20, choices=[('description','Descrição'),('counterparty','Favorecido'),('supplier_document','CPF/CNPJ do fornecedor')])
    operator = models.CharField('Operador', max_length=12, choices=[('CONTAINS','Contém'),('EQUALS','Igual a'),('STARTS','Começa com')])
    value = models.CharField('Valor procurado', max_length=240)
    category = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, verbose_name='Categoria resultante')
    active = models.BooleanField('Ativa', default=True)
    class Meta:
        ordering=['priority','pk']


class Expense(models.Model):
    key = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    fingerprint = models.CharField(max_length=64,editable=False)
    document_date = models.DateField('Data do documento / contrato')
    competence = models.DateField('Competência',db_index=True)
    description = models.CharField('Descrição',max_length=240)
    supplier = models.ForeignKey('purchases.Supplier',null=True,blank=True,on_delete=models.PROTECT,verbose_name='Fornecedor cadastrado')
    counterparty = models.CharField('Favorecido',max_length=240,blank=True)
    amount = models.DecimalField('Valor (R$)',max_digits=18,decimal_places=2)
    category = models.ForeignKey(ChartOfAccount,null=True,blank=True,on_delete=models.PROTECT,related_name='expenses',verbose_name='Plano de contas')
    category_snapshot = models.JSONField(default=dict,blank=True,editable=False)
    classification = models.CharField(max_length=12,choices=[('MANUAL','Manual'),('RULE','Regra automática'),('NONE','A classificar')],default='NONE')
    rule_snapshot = models.JSONField(default=dict,blank=True,editable=False)
    cost_center = models.CharField('Centro de custo',max_length=120,blank=True)
    notes = models.CharField('Observação',max_length=500,blank=True)
    title = models.OneToOneField('finance.FinancialTitle',on_delete=models.PROTECT,related_name='expense',editable=False)
    status = models.CharField(max_length=12,choices=[('ACTIVE','Registrada'),('CANCELLED','Cancelada')],default='ACTIVE',db_index=True)
    recurrence_of = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT,related_name='occurrences',editable=False)
    recurrence_index = models.PositiveIntegerField(default=0,editable=False)
    recurrence_enabled = models.BooleanField('Despesa recorrente mensal',default=False)
    revision = models.PositiveIntegerField(default=0,editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True,editable=False)
    cancellation_reason = models.CharField(max_length=500,blank=True)
    class Meta:
        ordering=['-competence','-pk']
        constraints=[models.CheckConstraint(condition=models.Q(amount__gt=0),name='expense_positive'),models.UniqueConstraint(fields=['recurrence_of','recurrence_index'],condition=models.Q(recurrence_of__isnull=False),name='expense_unique_occurrence')]
        indexes=[models.Index(fields=['status','competence']),models.Index(fields=['category','competence'])]


class ExpenseRevision(models.Model):
    expense = models.ForeignKey(Expense,on_delete=models.PROTECT,related_name='revisions')
    number = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['expense','number'],name='expense_revision_unique')]
