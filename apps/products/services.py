from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, number, QTY
from .models import Product, ProductComposition

@transaction.atomic
def save_product(*,actor,data,pk=None):
    require(actor,'core.operate_stock')
    domain_lock()
    obj=Product.objects.select_for_update().get(pk=pk) if pk else Product()
    before={k:str(getattr(obj,k)) for k in data}
    if pk and (obj.movements.exists() or obj.saleitem_set.exists() or obj.purchaseitem_set.exists() or obj.used_in.exists()):
        if data.get('kind',obj.kind)!=obj.kind or data.get('unit',obj.unit)!=obj.unit:
            raise ValidationError('Tipo e unidade não podem mudar após movimentação ou uso em kit.')
    if pk and obj.components.exists() and data.get('kind',obj.kind)!='KIT':
        raise ValidationError('Remova os componentes antes de alterar o tipo.')
    for k,v in data.items():
        if k not in {'sku','name','unit','kind','brand','category','minimum','active'}: raise ValidationError('Campo não editável.')
        setattr(obj,k,v)
    obj.full_clean();obj.save()
    audit(actor,obj,'update_product' if pk else 'create_product',before,{k:str(getattr(obj,k)) for k in data})
    return obj

@transaction.atomic
def remove_product(*,actor,pk):
    require(actor,'core.operate_stock');domain_lock()
    obj=Product.objects.select_for_update().get(pk=pk)
    if obj.movements.exists() or obj.saleitem_set.exists() or obj.purchaseitem_set.exists() or obj.used_in.exists() or obj.components.exists() or obj.balances.exists():
        obj.active=False;obj.save(update_fields=['active']);audit(actor,obj,'inactivate_product');return 'Produto inativado; histórico preservado.'
    audit(actor,obj,'delete_product',{'sku':obj.sku,'name':obj.name});obj.delete();return 'Produto excluído.'

@transaction.atomic
def set_components(*,actor,kit_id,items):
    require(actor,'core.operate_stock');domain_lock()
    ids={kit_id}|{int(i[0]) for i in items}
    products={p.pk:p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    kit=products[kit_id]
    if kit.kind!='KIT': raise ValidationError('Produto não é kit.')
    if len({i[0] for i in items})!=len(items): raise ValidationError('Componente repetido.')
    for pk,qty in items:
        number(qty,QTY)
        if pk==kit_id or pk not in products or products[pk].kind!='SIMPLE' or not products[pk].active: raise ValidationError('Componente inválido ou inativo.')
    before=list(kit.components.values('component_id','quantity'))
    kit.components.all().delete()
    for pk,qty in items: ProductComposition.objects.create(kit=kit,component_id=pk,quantity=qty)
    audit(actor,kit,'set_components',{'items':[(x['component_id'],str(x['quantity'])) for x in before]}, {'items':[(pk,str(qty)) for pk,qty in items]})
