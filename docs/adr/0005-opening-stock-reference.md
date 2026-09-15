# ADR 0005 — Base inicial de estoque

Data: 15/09/2026. Status: aceito por orientação do usuário.

## Contexto e decisão
A implantação prioriza lançamentos manuais. O usuário autorizou utilizar os dados existentes de estoque como atuais para desenvolvimento e corrigir diferenças posteriormente na ferramenta apropriada.

Usar somente a aba ESTOQUE MVET de ERP Mvet(2).xlsx, com movimentos de abertura em 15/09/2026 e sem efeito na DRE. Não exigir nova contagem prévia. Validar inconsistências e duplicidades e garantir idempotência. Não importar automaticamente outras abas nem reaplicar vendas antigas. Manter dados comerciais fora do Git.

## Consequências
A Fase 2 deve disponibilizar ajustes positivos/negativos com motivo, data, usuário e valores anteriores/posteriores, além de correção de custo auditada. Não alterar diretamente movimentos confirmados ou CMV histórico. Carga e interface ainda não implementadas.
