# ADR 0083 — Política comercial por empresa e SKU

CompanyProductPolicy separa mínimo, markup individual e preço fixo do catálogo
SKU global. Unicidade empresa/produto; valores não negativos; zero difere de
vazio. Migration aditiva copia as configurações existentes somente para empresa
1 sem atualizar Product, estoque, movimentos ou vendas. Não herdar configurações
Mercadovet para Agro automaticamente.

Serviços de cadastro/preço mantêm espelho dos três campos legados da Mercadovet
na mesma transação e lock. Preço consultado e mínimo do catálogo/planejamento
preferem a política empresarial; catálogo pré-carrega políticas para evitar uma
consulta por preço. Fallback legado exclusivo da empresa 1 mantém compatibilidade
com produtos criados por caminhos antigos. Configuração e consulta secundária
continuam bloqueadas até ativação completa; grupo não altera cadastro/preços.

Campos legados ainda não podem ser removidos: edição/formulários, alertas e
algumas integrações leem esse espelho. Escritas diretas de campos comerciais por
ORM fora dos serviços não são uma interface suportada para sincronização.
Políticas podem existir para empresas inativas como preparação, sem autorizar
operações. CASCADE de produto remove apenas configuração de produto nunca usado;
proteções transacionais existentes continuam impedindo excluir produto utilizado.

Testes: migração preserva todos os campos Product, zero/vazio/inativos; mesmo SKU
com duas políticas sem sobrescrita cruzada; edição/auditoria legada; grupo negado;
catálogo com mínimo empresarial e consulta de preço pré-carregada. CI integral
PostgreSQL/Chromium antes da integração. Não implanta nem ativa Agro.
