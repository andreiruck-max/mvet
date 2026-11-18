# ADR 0061 — Laboratório MVet 3.0 independente

Data: 18/11/2026. Escopo: PR 0, somente desenvolvimento.

O Compose operacional e seu atualizador não são reutilizados para o laboratório.
Projeto, rede interna, volume, banco, porta, cookies e segredos são independentes.
O módulo settings_mvet3 bloqueia Bling explicitamente; o adaptador verifica esse
bloqueio antes de OAuth, transporte, refresh ou XML. O padrão legado permanece
habilitado em settings.py para preservar o 2.0. Rede interna bloqueia egress do
app/banco como defesa adicional. Gateway Nginx sem credenciais publica a porta
8001 em rede separada e encaminha apenas para lab-web. A publicação direta em
rede interna falhou no ensaio Docker; o gateway conserva o bloqueio de egress
sem impedir entrada HTTP. Sem worker automático ou migrations no startup.

Identificação SQL antecede migrations explícitas. Restore de ensaio usa somente
banco temporário do laboratório e dados sintéticos. Nenhum schema empresarial
entra nesta fase. Manual: docs/MVET_3_0_DEVELOPMENT.md; plano: handoff multiempresa.
