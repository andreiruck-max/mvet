"""Project line-level NF-e acquisition evidence after key, products and gross amounts match."""
from decimal import Decimal
from .normalization import decimal_text

NS = {'n':'http://www.portalfiscal.inf.br/nfe'}
LINE_TAGS = {
    'gross':'n:prod/n:vProd', 'freight':'n:prod/n:vFrete', 'insurance':'n:prod/n:vSeg', 'other':'n:prod/n:vOutro',
    'ipi':'n:imposto/n:IPI/n:IPITrib/n:vIPI', 'st':'n:imposto/n:ICMS/*/n:vICMSST', 'fcp_st':'n:imposto/n:ICMS/*/n:vFCPST',
    'import_duty':'n:imposto/n:II/n:vII', 'returned_ipi':'n:impostoDevol/n:IPI/n:vIPIDevol',
    'icms':'n:imposto/n:ICMS/*/n:vICMS','pis':'n:imposto/n:PIS/*/n:vPIS','cofins':'n:imposto/n:COFINS/*/n:vCOFINS',
    'desoneration':'n:imposto/n:ICMS/*/n:vICMSDeson',
}
HEADER_TAGS = {'gross':'vProd','ipi':'vIPI','st':'vST','fcp_st':'vFCPST','freight':'vFrete','insurance':'vSeg',
               'other':'vOutro','import_duty':'vII','returned_ipi':'vIPIDevol','desoneration':'vICMSDeson'}


def project(info):
    header = info.find('n:total/n:ICMSTot',NS)
    details = info.findall('n:det',NS)
    if header.find('n:vProd',NS) is None and all(d.find('n:imposto',NS) is None and d.find('n:prod/n:NCM',NS) is None for d in details):
        return {}  # An older discount-only projection is not a full tax document.
    def amount(node,path):
        return Decimal(decimal_text(node.findtext(path,default='0',namespaces=NS),2))
    totals={tag:amount(header,'n:'+tag) for tag in (*HEADER_TAGS.values(),'vDesc','vNF')}
    issues=[]
    lines=[]
    for n,detail in enumerate(details,1):
        line={k:amount(detail,tag) for k,tag in LINE_TAGS.items()}
        line['invoice_st']=line['st']+line['fcp_st']
        line['invoice_other_tax']=line['import_duty']+line['returned_ipi']
        ncm=detail.findtext('n:prod/n:NCM',default='',namespaces=NS).strip()
        cfop=detail.findtext('n:prod/n:CFOP',default='',namespaces=NS).strip()
        if ncm and not (len(ncm)==8 and ncm.isascii() and ncm.isdecimal()):
            issues.append(f'Item {n}: NCM inválido no XML.'); ncm=''
        if cfop and not (len(cfop)==4 and cfop.isascii() and cfop.isdecimal()):
            issues.append(f'Item {n}: CFOP inválido no XML.'); cfop=''
        if detail.findtext('n:prod/n:indTot',default='1',namespaces=NS)!='1':
            issues.append(f'Item {n} não integra o total de produtos. Confira a composição fiscal.')
        lines.append({**{k:str(v) for k,v in line.items()},'ncm':ncm,'cfop':cfop})
    for key,tag in HEADER_TAGS.items():
        if sum((Decimal(line[key]) for line in lines),Decimal(0))!=totals[tag]:
            issues.append(f'{tag} difere da soma das linhas do XML.')
    if totals['vICMSDeson']:
        issues.append('ICMS desonerado exige classificação da dedução fiscal.')
    reconstructed=totals['vProd']-totals['vDesc']+sum((totals[tag] for tag in
                    ('vIPI','vST','vFCPST','vFrete','vSeg','vOutro','vII','vIPIDevol')),Decimal(0))
    fiscal={**{k:str(v) for k,v in totals.items()},'reconstructed':str(reconstructed),
            'difference':str(reconstructed-totals['vNF']),'issues':issues}
    return {'tax_items':lines,'fiscal':fiscal}
