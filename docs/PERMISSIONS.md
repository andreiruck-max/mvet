# Permissões
Implementado com User, Group e Permission nativos do Django. Serviços e views verificam permissões, não nomes de grupos. Operacional não ganha indicadores pelo direito de lançar.

| Perfil | Permissões iniciais |
|---|---|
| ADMINISTRADOR | Configuração, indicadores, DRE, custos, financeiro, lançar vendas/estoque/financeiro, consultar auditoria |
| GERENCIAL | Indicadores, DRE, custos |
| FINANCEIRO | Ver financeiro e operar pagamentos/recebimentos |
| VENDAS_OPERACIONAL | Operar vendas |
| ESTOQUE | Operar estoque |

Estoque está implementado. Vendas e financeiro continuam nas próximas fases.
Administração de usuários/grupos exige superusuário ativo. O grupo ADMINISTRADOR não equivale a is_superuser. is_staff permite entrar no admin, mas não concede autorização para promover usuários.
Perfis podem ser personalizados no admin. setup_mvet só atribui permissões quando cria um grupo, preservando ajustes posteriores. Nenhum usuário/senha padrão é criado.
Custos e saldos não aparecem no início comum. URLs de indicadores, DRE e financeiro e /api/v1/indicadores validam autorização mesmo quando acessadas diretamente.
Auditoria registra alterações de configuração, identidades/permissões realizadas pelo admin, login/logout e troca de senha sem salvar credenciais nos logs.
Mudanças por shell/SQL não passam pelo fluxo auditado: são procedimentos administrativos excepcionais, não rotina operacional.

## Estoque (Fase 2)
- operate_stock: cadastro, composição, locais, histórico, saída, redução, transferência e fracionamento.
- operate_stock + view_costs: abertura, entrada, acréscimo, correção de custo, carga inicial e estorno.
- operate_sales: consulta de produtos/quantidades e busca, sem edição e sem custos.
- view_costs: consulta do catálogo, custos e valorização, sem permissão automática de escrita.
- API GET /api/v1/produtos/ retorna cost somente com view_costs. Omissão é aplicada no backend.
- Remoção de produto sem uso é permitida; com saldo, composição ou histórico, somente inativação.
- Marcas, categorias e locais são editáveis/inativáveis; não há exclusão destrutiva desses cadastros pela interface.

Fase 3: `operate_sales` permite rascunhos, confirmação e cancelamento integral auditado; não concede `operate_stock` ou `view_costs`. `view_costs` permite leitura de resultado individual em tela/API sem escrita. `manage_configuration` gerencia canais e regras tributárias. Valores lançados são visíveis ao operacional para conferência; custos, CMV, margem e agregados não são exibidos. Listagem de vendas não contém somatórios financeiros.
