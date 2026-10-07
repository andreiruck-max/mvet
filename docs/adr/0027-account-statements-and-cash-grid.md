# ADR 0027 — Quadro bancário e página da conta

Data: 07/10/2026. Solicitação do proprietário.

O intervalo padrão do quadro é ontem até hoje + 13, inclusive: 15 dias. Intervalos personalizados de até 366 dias permanecem disponíveis, sem dividir datas em páginas. A rolagem horizontal mantém apenas a coluna Banco / conta fixa; não fixa a primeira célula de cada linha do cabeçalho.

Quadro, cartões e exportações/API correspondentes usam contas ativas. Inativação não apaga abertura, movimentos, obrigações ou saldos; conta pode ser reativada. Indicadores consolidados da empresa continuam contando saldos de contas inativas, evitando apagar patrimônio dos indicadores por mudança cadastral. A página individual continua disponível a usuários com view_finance, mesmo inativa.

Extrato é cronológico por data e ID, com soma acumulada do livro POSTED. Transferências previstas/canceladas são identificadas e não alteram saldo realizado. A paginação de movimentos mantém a soma anterior; alterações retroativas repercutem nas consultas posteriores. Títulos pendentes ficam em seção separada, com vínculo à liquidação original.

Lançamento manual realizado pela conta compõe create_title e settle em uma transação. Reutiliza validação de datas, abertura, conta ativa, permissões e travas do domínio, UUID/fingerprint e chave derivada de liquidação. Não cria uma segunda via de edição direta do livro. Permissões: view_finance, operate_finance, create_financial_titles e pay_titles ou receive_titles conforme direção. Reenvio idêntico não duplica; alteração do envio é rejeitada. Estornos usam o fluxo existente e reabrem o título, que deve ser tratado na tela correspondente.

Previsões e transferências usam telas existentes com conta sugerida. Cadastro/edição/inativação seguem manage_financial_accounts e proteção do saldo inicial utilizado. A entrada/saída de caixa não substitui o reconhecimento de despesa por competência nem deve duplicar obrigações existentes.

Sem mudança de schema. Padrões numéricos Decimal e histórico financeiro permanecem.
