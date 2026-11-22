# ADR 0072 — Titularidade da conexão Bling na transição

Status: aceito para MVet 3.0, fase 2.

A conexão existente recebe company OneToOne obrigatório, PROTECT e default 1.
DDL aditivo preserva issuer, ciphertext, datas e identificadores. Não descriptografa,
não renova tokens e não chama serviços externos. Não altera credenciais reais.

Permanecem o singleton e uma constraint company=1. Assim, a identidade empresarial
é explícita sem permitir uma segunda conexão enquanto OAuth, workers e adaptadores
continuam globais. A igualdade issuer/CNPJ e o contexto explícito serão implantados
na fase 5, antes de remover esses bloqueios (ADR 0060). CNPJ desconhecido do cadastro
não é preenchido por inferência durante a migration.

Teste PostgreSQL compara todos os campos antigos após migration e rejeita troca de
proprietário. Regressão inclui importação, OAuth simulado, agendamento e extratos.
Não representa suporte operacional a duas contas Bling.
