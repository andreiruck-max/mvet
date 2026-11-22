# ADR 0067 — Identidade empresarial das vendas

Sale, SaleItem, SaleConsumption e SaleExtraCost recebem FK company obrigatória, PROTECT, default constante Mercadovet (1) e constraint transitória restringindo a empresa 1. DDL aditivo, sem UPDATE de histórico, sem alteração dos gatilhos e sem recálculo de CMV, impostos ou comissões.

Ainda não habilita MVet Agro. Canais, regras tributárias e revisões serão contextualizados em etapa subsequente; consultas e serviços continuam legados. As constraints impedem introduzir dados secundários enquanto isso. O SKU permanece global.

Testes específicos verificam confirmação, propriedade do consumo e CMV congelado após reposição com custo diferente, além da rejeição de empresa secundária. Antes da integração, exigir regressão PostgreSQL/navegador e ensaio da migration com registros históricos confirmados. Não aplicar em produção 2.0.
