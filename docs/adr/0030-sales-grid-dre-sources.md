# ADR 0030 — Grade de vendas e rastreabilidade da DRE

Data: 08/10/2026. Estado: aceito.

## Decisão
A tabela de vendas usa uma definição comum de colunas para cabeçalho, linhas e totais. Imposto permanece visível; deduções e ajustes aparecem se houver valor não zero em qualquer venda do filtro, inclusive fora da página atual. Totais incluem somente confirmadas e mantêm as permissões de custos/margens. Produtos e quantidades são apresentados por item, sem somar unidades distintas. Canais podem ser recolhidos; cabeçalhos e totais ficam fixos no quadro com rolagem própria.

Somente usuário ativo master pode abrir `/dre/lancamentos/`, inclusive por acesso direto. Seletores de origem são assinados pelo servidor. As fontes usam os mesmos filtros e valores da DRE: snapshots de vendas confirmadas, despesas ativas por competência e categoria histórica, compras sem estoque confirmadas/recebidas, diferenças imutáveis de custo e títulos/juros financeiros com seus estornos. Despesas comuns não são rateadas ao filtrar canal.

O detalhamento é somente leitura e leva às ações existentes de cada origem. Lançamentos extras usam os serviços e permissões do módulo correspondente. Não libera edição direta de livro, CMV, impostos históricos ou registros transacionais; cancelamentos/reclassificações/correções continuam auditados. Nenhuma migration ou alteração automática dos dados existentes é necessária.

## Validação
Cobrir totais de todas as páginas, colunas condicionais, valores negativos, permissões diretas, categorias históricas, compras sem estoque, diferença de custo e juros estornados. Validar em navegador alinhamento, cabeçalhos fixos, recolhimento, navegação às origens e larguras desktop/celular.
