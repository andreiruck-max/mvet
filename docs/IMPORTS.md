# Importações
Fora do caminho crítico por instrução do usuário: a operação inicial será manual, sem importação integral de ERP Mvet.xlsx. Não há comando de migração implementado nesta entrega.

## Arquitetura futura
Upload → leitura isolada → validação → preview → confirmação → processamento → relatório.
ImportBatch: origem, hash, arquivo, ator, horários e contadores.
ImportRow: dados, erros e registro destino. Identificadores externos únicos impedem duplicidade.
Rollback só quando seguro; registros dependentes exigem estornos e revisão, nunca exclusão destrutiva.
Arquivos reais e relatórios comerciais não são versionados no GitHub.

## Política de abertura
Corte 15/09/2026. Estoque inicial deve produzir movimentos auditados. Não executar vendas anteriores contra saldo já atualizado. Títulos pendentes anteriores não são novas despesas da DRE.
