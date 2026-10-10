import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from . import choices as c


class Contact(models.Model):
    name = models.CharField('Nome',max_length=180)
    phone = models.CharField('Telefone / WhatsApp',max_length=20,blank=True,db_index=True)
    email = models.EmailField('E-mail',blank=True,db_index=True)
    city = models.CharField('Cidade (recomendada)',max_length=120,blank=True)
    uf = models.CharField('UF',max_length=2,blank=True)
    company = models.CharField('Empresa / fazenda',max_length=180,blank=True)
    segment = models.CharField('Segmento',max_length=20,choices=c.SEGMENTS,blank=True)
    origin = models.CharField('Origem',max_length=20,choices=c.ORIGINS,default='OTHER')
    kind = models.CharField('Tipo',max_length=20,choices=c.TYPES,default='LEAD')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='crm_contacts',verbose_name='Responsável')
    notes = models.TextField('Observações',blank=True,max_length=10000)
    commercial_info = models.TextField('Informações comerciais importantes',blank=True,max_length=10000)
    state = models.CharField(max_length=20,choices=c.STATES,default='ACTIVE',db_index=True)
    next_date = models.DateField('Próximo contato',null=True,blank=True,db_index=True)
    next_reason = models.CharField('Motivo da próxima ação',max_length=300,default='Primeiro contato')
    last_at = models.DateTimeField(null=True,blank=True)
    last_result = models.CharField(max_length=25,choices=c.RESULTS,blank=True)
    created_at = models.DateTimeField(auto_now_add=True,db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name','pk']
        constraints = [
            models.CheckConstraint(condition=~models.Q(phone='',email=''),name='crm_contact_reachable'),
            models.CheckConstraint(condition=~models.Q(state__in=['ACTIVE','WAITING','PAUSED'])|models.Q(next_date__isnull=False),name='crm_active_next_action'),
            models.CheckConstraint(condition=~models.Q(state__in=['DNC','INACTIVE','APPROVAL'])|models.Q(next_date__isnull=True),name='crm_stopped_no_action'),
            models.UniqueConstraint(fields=['phone'],condition=~models.Q(phone=''),name='crm_unique_phone'),
            models.UniqueConstraint(fields=['email'],condition=~models.Q(email=''),name='crm_unique_email'),
        ]
    def __str__(self): return self.name
    @property
    def whatsapp_url(self): return 'https://wa.me/'+self.phone if self.phone and self.state not in ('DNC','INACTIVE','APPROVAL') else ''


class RecurrenceRule(models.Model):
    result = models.CharField(max_length=25,choices=c.RESULTS,unique=True)
    days = models.PositiveIntegerField('Retornar após (dias)',default=7,validators=[MinValueValidator(1),MaxValueValidator(3650)])
    allow_manual = models.BooleanField('Funcionário pode escolher outra data',default=True)
    def __str__(self): return self.get_result_display()


class Interaction(models.Model):
    contact = models.ForeignKey(Contact,on_delete=models.PROTECT,related_name='interactions')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    key = models.UUIDField(default=uuid.uuid4,unique=True)
    occurred_at = models.DateTimeField('Data e horário')
    created_at = models.DateTimeField(auto_now_add=True)
    channel = models.CharField('Canal',max_length=20,choices=c.CHANNELS)
    kind = models.CharField('Tipo',max_length=20,choices=c.ACTIVITY_TYPES,default='CONVERSATION')
    sent = models.TextField('Mensagem enviada',blank=True,max_length=20000)
    received = models.TextField('Mensagem recebida',blank=True,max_length=20000)
    read_state = models.CharField('Visualização (manual)',max_length=20,choices=c.READ_STATES,default='UNKNOWN')
    result = models.CharField('Resultado',max_length=25,choices=c.RESULTS)
    internal_note = models.TextField('Observação interna',blank=True,max_length=10000)
    next_date = models.DateField(null=True,blank=True)
    next_reason = models.CharField(max_length=300,blank=True)
    rule_days = models.PositiveIntegerField(null=True)
    manual_date = models.BooleanField(default=False)
    class Meta: ordering = ['-occurred_at','-pk']


class InactivationRequest(models.Model):
    contact = models.ForeignKey(Contact,on_delete=models.PROTECT,related_name='requests')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    reason = models.CharField('Motivo',max_length=20,choices=c.REASONS)
    justification = models.TextField('Justificativa',max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    decision = models.CharField(max_length=10,default='PENDING',choices=[('PENDING','Pendente'),('APPROVED','Aprovada'),('REJECTED','Recusada')])
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,related_name='+')
    decided_at = models.DateTimeField(null=True)
    decision_note = models.TextField(blank=True,max_length=5000)
    class Meta:
        ordering = ['created_at','pk']
        constraints = [models.UniqueConstraint(fields=['contact'],condition=models.Q(decision='PENDING'),name='crm_one_pending_request')]


class ContactEvent(models.Model):
    contact = models.ForeignKey(Contact,on_delete=models.PROTECT,related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=60)
    note = models.TextField(blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    class Meta: ordering = ['-created_at','-pk']


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    first_date = models.DateField()
    rows = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True)
    report = models.JSONField(default=list)
