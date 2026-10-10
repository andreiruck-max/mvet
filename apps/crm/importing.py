"""Bounded, values-only imports. Preview never writes contacts; commit revalidates."""
import csv
import io
import unicodedata
import zipfile
import posixpath
from xml.etree import ElementTree as ET
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.accounts.access import master
from apps.inventory.services import domain_lock
from apps.core.services import audit
from .models import Contact, ImportBatch
from . import services, choices

MAX_ROWS=2000
def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '').strip().lower()) if not unicodedata.combining(c))

HEADERS={'nome':'name','telefone':'phone','whatsapp':'phone','telefone/whatsapp':'phone','telefone / whatsapp':'phone','email':'email','e-mail':'email','cidade':'city','uf':'uf','empresa':'company','fazenda':'company','empresa/fazenda':'company','empresa / fazenda':'company','segmento':'segment','origem':'origin','tipo':'kind','observacao':'notes','observacoes':'notes','responsavel':'owner','responsavel comercial':'owner','informacoes comerciais importantes':'commercial_info'}

def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValidationError('XML com entidades não permitido.')
    return ET.fromstring(data)

def read_rows(upload):
    if upload.size>5*1024*1024:raise ValidationError('Arquivo excede 5 MB.')
    data=upload.read();extension=upload.name.lower().rsplit('.',1)[-1]
    if extension=='csv':
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValidationError('Salve o CSV em UTF-8.')
        if not text.strip():raise ValidationError('Arquivo vazio.')
        delimiter=';' if text.splitlines()[0].count(';')>text.splitlines()[0].count(',') else ','
        rows=list(csv.reader(io.StringIO(text),delimiter=delimiter))
    elif extension=='xlsx':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist())>200 or sum(i.file_size for i in archive.infolist())>20*1024*1024:raise ValidationError('XLSX excede o limite descompactado.')
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                strings=[]
                if 'xl/sharedStrings.xml' in archive.namelist():
                    strings=[''.join(x.itertext()) for x in xml(archive.read('xl/sharedStrings.xml')).findall('s:si',ns)]
                sheet_path='xl/worksheets/sheet1.xml'
                if 'xl/workbook.xml' in archive.namelist():
                    workbook=xml(archive.read('xl/workbook.xml'))
                    first=workbook.find('s:sheets/s:sheet',ns)
                    relation=first.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
                    relationships=xml(archive.read('xl/_rels/workbook.xml.rels'))
                    target=next(r for r in relationships if r.attrib.get('Id')==relation)
                    if target.attrib.get('TargetMode')=='External':raise ValidationError('Planilhas externas não são aceitas.')
                    path=target.attrib['Target']
                    sheet_path=posixpath.normpath(path.lstrip('/') if path.startswith('/') else 'xl/'+path)
                    if not sheet_path.startswith('xl/worksheets/'):raise ValidationError('Primeira aba deve ser uma planilha de dados.')
                root=xml(archive.read(sheet_path));rows=[]
                for row in root.findall('.//s:sheetData/s:row',ns):
                    values={}
                    for cell in row.findall('s:c',ns):
                        if cell.find('s:f',ns) is not None:raise ValidationError('Use somente valores, sem fórmulas na planilha.')
                        letters=''.join(c for c in cell.attrib.get('r','') if c.isalpha());index=0
                        for letter in letters:index=index*26+ord(letter.upper())-64
                        if not 1<=index<=30:raise ValidationError('Planilha deve ter no máximo 30 colunas.')
                        value=cell.findtext('s:v','',ns)
                        if cell.attrib.get('t')=='s':value=strings[int(value)]
                        elif cell.attrib.get('t')=='inlineStr':value=''.join(cell.find('s:is',ns).itertext())
                        values[index-1]=value
                    rows.append([values.get(i,'') for i in range(max(values,default=-1)+1)])
                    if len(rows)>MAX_ROWS+1:raise ValidationError('Importe no máximo 2.000 contatos por arquivo.')
        except (zipfile.BadZipFile,KeyError,ET.ParseError,IndexError,ValueError,AttributeError,StopIteration):raise ValidationError('XLSX inválido. Use a primeira aba padrão e valores simples.')
    else:raise ValidationError('Envie CSV ou XLSX.')
    if not rows or not any(rows[0]):raise ValidationError('Arquivo vazio ou sem cabeçalho.')
    if len(rows)>MAX_ROWS+1:raise ValidationError('Importe no máximo 2.000 contatos por arquivo.')
    headers=[HEADERS.get(normalized(h)) for h in rows[0]]
    known=[h for h in headers if h]
    if len(known)!=len(set(known)):raise ValidationError('Há colunas repetidas (telefone e WhatsApp devem usar uma única coluna).')
    if 'name' not in headers or not ({'phone','email'} & set(headers)):raise ValidationError('Cabeçalho deve conter nome e telefone/WhatsApp ou e-mail.')
    result=[]
    for number,row in enumerate(rows[1:],2):
        if not any(str(v).strip() for v in row):continue
        if any(len(str(v))>20000 for v in row):raise ValidationError('Célula excede 20.000 caracteres.')
        result.append({'line':number,'data':{key:str(row[i]).strip() for i,key in enumerate(headers) if key and i<len(row)}})
    return result

def prepare(data,owner,first_date):
    data=dict(data)
    username=data.pop('owner','')
    if username:
        owner=get_user_model().objects.filter(username=username).first()
    services.validate_owner(owner)
    data['phone']=services.phone_number(data.get('phone',''));data['email']=data.get('email','').casefold()
    data['uf']=data.get('uf','').upper()
    for field,options,default in [('segment',choices.SEGMENTS,''),('origin',choices.ORIGINS,'IMPORT'),('kind',choices.TYPES,'LEAD')]:
        value=data.get(field,'');mapping={normalized(label):key for key,label in options};mapping.update({normalized(key):key for key,label in options})
        if value and normalized(value) not in mapping:raise ValidationError(f'{field}: opção não reconhecida ({value}).')
        data[field]=mapping.get(normalized(value),default)
    obj=Contact(**data,owner=owner,next_date=first_date)
    obj.full_clean()
    if services.duplicates(obj.phone,obj.email):raise ValidationError('Telefone ou e-mail já cadastrado.')
    data.update(owner=owner,first_date=first_date)
    return data

@transaction.atomic
def preview(*,actor,upload,owner,first_date):
    master(actor);services.future_date(first_date);services.validate_owner(owner)
    rows=read_rows(upload);phones=set();emails=set()
    for row in rows:
        try:
            data=prepare(row['data'],owner,first_date)
            if data['phone'] and data['phone'] in phones or data['email'] and data['email'] in emails:raise ValidationError('Duplicidade dentro do arquivo.')
            if data['phone']:phones.add(data['phone'])
            if data['email']:emails.add(data['email'])
            row['error']='';row['owner_name']=data['owner'].username
        except ValidationError as exc:row['error']='; '.join(exc.messages)
    return ImportBatch.objects.create(actor=actor,owner=owner,first_date=first_date,rows=rows)

@transaction.atomic
def commit(*,actor,batch_id):
    master(actor);domain_lock();batch=ImportBatch.objects.select_for_update().get(pk=batch_id)
    if batch.committed_at:return batch
    services.future_date(batch.first_date)
    report=[]
    for row in batch.rows:
        if row['error']:report.append({'line':row['line'],'error':row['error']});continue
        try:
            with transaction.atomic():
                data=prepare(row['data'],batch.owner,batch.first_date)
                contact=services.save_contact(actor=actor,data=data)
                report.append({'line':row['line'],'contact':contact.pk,'name':contact.name})
        except (ValidationError,IntegrityError) as exc:
            report.append({'line':row['line'],'error':'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Duplicidade concorrente; não importado.'})
    batch.report=report;batch.committed_at=timezone.now();batch.save()
    audit(actor,batch,'crm_import',after={'created':sum('contact' in r for r in report),'skipped':sum('error' in r for r in report)})
    return batch
