"""Read only the primary A:D inventory table, using Excel's cached numeric values."""
import hashlib
import posixpath
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.models import Company
from apps.core.services import require
from apps.products.services import save_product
from apps.products.models import Product
from .models import OpeningImport, StockLocation
from .services import domain_lock, execute, number, QTY, MONEY, quant

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def read_inventory(path, *, merge_duplicates=False):
    errors=[];warnings=[];groups=defaultdict(list)
    with ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist())>30_000_000:
            raise ValidationError('Arquivo descompactado excede o limite de 30 MB.')
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        sheet=next((s for s in workbook.findall('s:sheets/s:sheet',NS) if s.get('name')=='ESTOQUE MVET'),None)
        if sheet is None:raise ValidationError('Aba ESTOQUE MVET não encontrada.')
        rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target=next(r.get('Target') for r in rels if r.get('Id')==rid)
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        def value(cell):
            if cell.get('t')=='inlineStr':return ''.join(cell.find('s:is',NS).itertext())
            v=cell.findtext('s:v',default='',namespaces=NS)
            return shared[int(v)] if cell.get('t')=='s' and v else v
        for row in ET.fromstring(archive.read(target)).findall('s:sheetData/s:row',NS):
            line=int(row.get('r'));cells={''.join(filter(str.isalpha,c.get('r'))):c for c in row}
            if line<=2:continue
            sku=value(cells['A']).strip() if 'A' in cells else ''
            if not sku:continue
            if sku.endswith('.0'):sku=sku[:-2]
            try:
                name=value(cells['B']).strip();qty=Decimal(value(cells['C']));cost=Decimal(value(cells['D']))
                # Excel caches binary arithmetic; normalize only sub-nanounit noise.
                for label,value_,quantum in [('quantity',qty,QTY),('cost',cost,MONEY)]:
                    if value_.is_finite() and abs(value_-value_.quantize(quantum)) <= Decimal('0.000000001'):
                        if label=='quantity':qty=value_.quantize(quantum)
                        else:cost=value_.quantize(quantum)
                if cost.is_finite() and cost>=0 and cost != quant(cost):
                    warnings.append(f'Linha {line}: custo arredondado de {cost} para {quant(cost)} (6 casas).')
                    cost=quant(cost)
                number(qty,QTY,zero=True);number(cost,MONEY,zero=True)
                if not name:raise ValueError('nome ausente')
                groups[sku].append({'sku':sku,'name':name,'quantity':qty,'cost':cost,'lines':[line]})
            except (KeyError,ValueError,InvalidOperation,ValidationError):errors.append(f'Linha {line}: produto, quantidade ou custo inválido/sem cache de fórmula.')
    result=[]
    for sku,items in groups.items():
        if len(items)==1:result.extend(items);continue
        if not merge_duplicates:
            errors.append(f'SKU {sku}: duplicado nas linhas {[i["lines"][0] for i in items]}. Use consolidação explícita após revisar.');continue
        names={i['name'] for i in items};qty=sum(i['quantity'] for i in items)
        if len(names)!=1 or (qty==0 and len({i['cost'] for i in items})>1):
            errors.append(f'SKU {sku}: duplicidade ambígua. Corrija a origem.');continue
        cost=quant(sum(i['quantity']*i['cost'] for i in items)/qty) if qty else items[0]['cost']
        item={**items[0],'quantity':qty,'cost':cost,'lines':[n for i in items for n in i['lines']]}
        result.append(item);warnings.append(f'SKU {sku}: linhas {item["lines"]} consolidadas por quantidade e valor; linhas zeradas não ponderam o custo.')
    return result,{'errors':errors,'warnings':warnings,'products':len(result),'source_rows':sum(len(i) for i in groups.values())}

@transaction.atomic
def load_opening(*,actor,path,location_name,merge_duplicates=False,commit=False):
    require(actor,'core.operate_stock');require(actor,'core.view_costs')
    rows,report=read_inventory(path,merge_duplicates=merge_duplicates)
    if not commit or report['errors']:return report
    digest=hashlib.sha256(open(path,'rb').read()).hexdigest()
    domain_lock()
    previous=OpeningImport.objects.filter(digest=digest).first()
    if previous:return {**previous.report,'already_loaded':True}
    if Product.objects.filter(sku__in=[r['sku'] for r in rows]).exists():
        raise ValidationError('Um ou mais SKUs já existem. A carga inicial não sobrescreve produtos; use ajustes ou cadastre manualmente.')
    location,_=StockLocation.objects.get_or_create(name=location_name)
    if not location.active:raise ValidationError('Local de abertura inativo.')
    date=Company.objects.get(pk=1).cutover_date
    for row in rows:
        p=save_product(actor=actor,data={'sku':row['sku'],'name':row['name'],'unit':'UN','kind':'SIMPLE'})
        execute(actor=actor,key=uuid.uuid5(uuid.NAMESPACE_URL,digest+':'+row['sku']),kind='OPENING',date=date,
            reason=f'Abertura da planilha; linhas {row["lines"]}',product_id=p.pk,location_id=location.pk,quantity=row['quantity'],cost=row['cost'])
    report['loaded']=len(rows)
    OpeningImport.objects.create(digest=digest,actor=actor,report=report)
    return report
