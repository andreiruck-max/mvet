# ADR 0080 — Empresa em contagens e importações de estoque

Contagem, abertura por planilha, carga por depósito e conciliação recebem
company_id e validam o contexto antes da prévia, leitura de arquivo ou replay.
Grupo e secundárias são negados. Consultas de livro e projeções, cutover,
registros de importação e operações usam explicitamente esse proprietário.

Token assinado da contagem contém empresa; conferir empresa antes do replay.
Tokens antigos sem esse campo continuam válidos exclusivamente para empresa 1
pelo prazo já existente de 24 horas. Hashes/digests legados são preservados:
nesta etapa a empresa secundária continua bloqueada, inclusive no banco.

Ainda pendentes: unicidades/digests por empresa, catálogo/políticas, contagem
física compartilhada com atribuição de diferença e liberação da Agro.
Não remover a restrição primária sem concluir esses contratos.

Testes cobrem grupo negado antes de leitura/prévia/confirmação, secundária
negada, token de empresa incompatível, compatibilidade de token legado e
replay negado no grupo. A suíte existente cobre aplicação/idempotência das
planilhas e conciliações, com PostgreSQL e navegador no CI.
