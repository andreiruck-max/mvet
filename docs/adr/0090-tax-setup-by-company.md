# ADR 0090 — Preparar a tributação do segundo CNPJ

Os modelos passaram a separar alíquotas por empresa na ADR 0087. O master
agora pode prepará-las na ficha de cada empresa inativa e sem vendas, antes de
habilitar qualquer transação. A tela mostra a empresa e, quando cadastrado, o
CNPJ. A lista usa a última vigência até a data de hoje da própria regra e
considera início, fim e inativação. Histórico e alterações futuras continuam
visíveis na revisão; a configuração inicial não é sobrescrita.

A preparação usa os serviços transacionais de cadastro e vigência já existentes.
O proprietário vem da rota; regra, histórico e vendas afetadas são buscados
no mesmo CNPJ. O master não pode usar a sessão Grupo para escrever. O formulário
só aceita campos fiscais e a auditoria identifica a empresa. A exceção é restrita
ao laboratório multiempresa e não libera venda, estoque, lançamento financeiro ou
integração externa. Na empresa principal os usuários continuam sujeitos às suas
permissões de gestão e retroatividade. Não há migration; voltar o código conserva
as regras e revisões registradas em 0021.
