# ADR 0063 — Resolução explícita do contexto empresarial

Primeira parte da PR 1b: serviço resolve_scope valida usuário ativo, empresa ativa e vínculo ativo a cada chamada. Contexto inválido nunca volta silenciosamente à empresa 1. Grupo inclui apenas empresas com autorização explícita de leitura consolidada; não autoriza operações, mesmo para master. A operação segue limitada à empresa 1 durante a transição.

Este serviço não substitui permissões funcionais: os chamadores continuam obrigados a verificá-las. Ainda não conectado às rotas, sessões, jobs ou seletor visual. Não representa isolamento operacional completo. Próxima alteração deve integrar middleware, backend e UI conjuntamente, com regressão das rotas e proteção contra acesso cruzado.

Sem migrations, alteração de saldos, chamadas Bling ou modificações no ambiente 2.0. Testes cobrem vínculo ausente/revogado, empresa inativa, usuário inativo, seleção inválida e escrita no modo Grupo.
