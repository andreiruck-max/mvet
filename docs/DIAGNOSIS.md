# Diagnóstico inicial
Data: 15/09/2026.
O repositório andreiruck-max/mvet foi criado com apenas README.md. Sem código legado, migrations ou AGENTS anteriores. Visibilidade pública na inspeção; somente código e documentação foram adicionados.

A planilha foi consultada como referência funcional. Estoque utiliza SKU/quantidade/custo; vendas têm valores e descrições textuais de itens; compras se organizam por parcelas; fluxo de caixa usa quadros horizontais e totais diários. Essas estruturas não devem virar tabelas mensais nem ser importadas sem validação.

Decisão posterior do usuário: não migrar integralmente os dados. A implementação fornecerá entradas manuais, com corte em 15/09/2026. Não foram publicados registros comerciais da planilha.

## Decisões
Monólito Django/PostgreSQL; custo médio global por produto com locais quantitativos; snapshots históricos; títulos pagar/receber separados de compras/vendas; competência e caixa separados; regras em services; permissões granulares.
Abertura de estoque e bancos fora da DRE. Pendências anteriores identificadas como legadas. Próxima fase funcional: produtos/estoque manual.

## Restrições observadas
Ambiente local perdeu conexão durante desenvolvimento. Fundação foi concluída pelo plugin e testada via CI PostgreSQL. Revisão visual interativa e testes de instalação/backup na máquina destino não realizados.
Proteção de branch e milestones nativos não configurados pelas ferramentas disponíveis.
