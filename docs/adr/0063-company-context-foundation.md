# ADR 0063 — Resolução explícita do contexto empresarial

Primeira parte da PR 1b: serviço resolve_scope valida usuário ativo, empresa ativa e vínculo ativo a cada chamada. Contexto inválido nunca volta silenciosamente à empresa 1. Grupo inclui apenas empresas com autorização explícita de leitura consolidada; não autoriza operações, mesmo para master. A operação segue limitada à empresa 1 durante a transição.

Este serviço não substitui permissões funcionais: os chamadores continuam obrigados a verificá-las. Conectado às rotas, sessões e seletor visual exclusivamente no laboratório, conforme seção abaixo. Jobs e serviços transacionais ainda exigem contextualização nas próximas etapas. Não representa isolamento operacional completo. Permissões por objeto continuam negadas para usuários comuns, inclusive quando há concessão funcional por empresa.

Sem migrations, alteração de saldos, chamadas Bling ou modificações no ambiente 2.0. Testes cobrem vínculo ausente/revogado, empresa inativa, usuário inativo, seleção inválida e escrita no modo Grupo.


## Sessão e rotas no laboratório

COMPANY_CONTEXT_ENABLED é ativado exclusivamente em settings_mvet3. O middleware valida cada requisição autenticada e não permite acessar rotas legadas em Grupo ou empresa secundária. Cadastro master e tela de contexto permanecem acessíveis para administração/retorno. O backend aplica permissões explícitas do vínculo ou herança legada na empresa 1. GET não troca o contexto; POST usa CSRF e valida vínculo antes de salvar na sessão.

A página de Grupo nesta fase é apenas preparação, sem totais nem operações. Jobs e chamadas diretas aos serviços ainda não são contextualizados: essa implementação NÃO habilita operações secundárias ou isolamento completo. A suíte legada usa settings padrão; testes específicos habilitam a configuração de contexto.
