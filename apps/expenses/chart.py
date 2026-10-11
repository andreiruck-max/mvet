"""Versioned, additive configuration. No commercial transactions or automatic reclassification."""
from django.db import transaction
from apps.inventory.services import domain_lock
from .models import ChartOfAccount

# Codes reference the supplied chart. Conflicts reserve a new root, never overwrite.
GROUPS = [
 ('01','Deduções da receita','OPERATING',[
 ('01','Simples Nacional — valores não incluídos nas vendas'),
 ('02','Devoluções / cancelamentos — ajustes não registrados nas vendas')]),
 ('02','Despesas com vendas','OPERATING',[
 ('01','Tarifas Mercado Livre'),('02','Tarifas Shopee'),('03','Tarifa Full'),('04','Tarifa afiliados'),
 ('05','Fretes de venda'),('06','Embalagens'),('07','Comissões sobre vendas'),('08','Taxas de pagamento'),
 ('09','Armazenagem / logística'),('10','Perdas e avarias não registradas no estoque')]),
 ('03','Marketing e comercial','OPERATING',[
 ('01','Agência / gestão de marketing'),('02','ADS Mercado Livre'),('03','ADS Shopee'),('04','ADS Mercadovet'),
 ('05','Publicidade / ADS genérico'),('06','Folders / materiais promocionais'),('07','Patrocínios'),
 ('08','Eventos / feiras / congressos'),('09','Cartões de visita / materiais gráficos'),('10','Viagens / visitas comerciais')]),
 ('04','Despesas administrativas','OPERATING',[
 ('01','Honorários contábeis'),('02','Softwares / sistemas / plataformas'),('03','Internet / telefone'),
 ('04','Taxas / licenças / certidões'),('05','Material de uso / consumo'),('06','Associações / entidades'),
 ('07','Tributos operacionais — não incluídos nas vendas'),('08','Honorários jurídicos / consultorias'),('09','Seguros empresariais')]),
 ('05','Despesas com estrutura','OPERATING',[
 ('01','Aluguel'),('02','Água e energia'),('03','Limpeza'),('04','Manutenção / pequenos reparos'),
 ('05','IPTU / lixo'),('06','Segurança / extintores'),('07','Adequações do barracão — manutenção, sem imobilização')]),
 ('06','Despesas com pessoal','OPERATING',[
 ('01','Salários'),('02','Pró-labore'),('03','INSS'),('04','FGTS'),('05','Outros encargos / benefícios'),
 ('06','Serviços de terceiros'),('07','Férias / adicional'),('08','13º salário'),('09','Rescisões'),('10','Treinamento / saúde ocupacional')]),
 ('07','Despesas financeiras','FINANCIAL',[
 ('01','Tarifas bancárias'),('02','Juros / encargos financeiros'),('03','Juros de financiamento de veículos'),
 ('04','Multas / juros por atraso'),('05','Antecipação de recebíveis')]),
 ('08','Depreciação / amortização','DEPRECIATION',[
 ('01','Depreciação / amortização'),('02','Depreciação de veículos'),('03','Depreciação de instalações / equipamentos')]),
 ('09','Despesas com veículos','OPERATING',[
 ('02','Combustíveis'),('03','Pedágios'),('04','Manutenção / reparos de veículos'),('05','Pneus'),
 ('06','Seguro de veículos'),('07','IPVA / licenciamento'),('08','Estacionamento'),('09','Multas / outras despesas com veículos')]),
 ('90','Fora da DRE','GROUP',[
 ('01','Retiradas / distribuições de sócios','EQUITY'),('02','Empréstimos concedidos','ASSET'),
 ('03','Compra de imobilizado / benfeitorias','ASSET'),('04','Principal de empréstimos / financiamento de veículos','LIABILITY'),
 ('05','Outras movimentações patrimoniais','ASSET'),('06','Compra de estoque — recebimento pelo módulo Compras','ASSET'),
 ('07','Aportes de capital','EQUITY'),('08','Despesas pessoais de sócios','EQUITY')]),
 ('99','Pendente de classificação','UNCLASSIFIED',[('01','Pendente de classificação')]),
]


@transaction.atomic
def install_chart():
    domain_lock()
    created = 0
    def ensure(key, code, name, nature, parent=None, postable=True):
        nonlocal created
        existing = ChartOfAccount.objects.filter(seed_key=key).first()
        if existing: return existing
        equivalent = ChartOfAccount.objects.filter(code=code, name=name, nature=nature, parent=parent, postable=postable).first()
        if equivalent:
            equivalent.seed_key=key; equivalent.save(update_fields=['seed_key']); return equivalent
        used=set(ChartOfAccount.objects.values_list('code',flat=True))
        if code in used:
            prefix=parent.code+'.' if parent else ''
            code=next((prefix+f'{n:02d}' for n in range(1,100) if prefix+f'{n:02d}' not in used), None)
            if code is None: raise ValueError('Sem códigos livres para instalar o plano; nenhum cadastro foi alterado.')
        created += 1
        return ChartOfAccount.objects.create(seed_key=key, code=code, name=name, nature=nature, parent=parent, postable=postable)
    for root, name, nature, children in GROUPS:
        parent=ensure('mercadovet-2026:'+root,root,name,nature,postable=False)
        for item in children:
            suffix,label,*specific=item
            ensure('mercadovet-2026:'+root+'.'+suffix,parent.code+'.'+suffix,label,specific[0] if specific else nature,parent)
    return created
