# Changelog
## 0.1.0 — Fundação (15/09/2026)
- Arquitetura, modelo alvo em Mermaid, ADRs e contratos por domínio.
- Decisão de entrada manual e corte em 15/09/2026.
- Django 5.2.17, PostgreSQL, Docker, configuração por ambiente.
- Login/logout, troca de senha, grupos/permissões granulares e controles backend.
- Empresa, margem mínima configurável, auditoria e migração inicial.
- Layout Mercadovet claro/escuro, navegação por permissão.
- Testes PostgreSQL e CI; scripts de backup/teste de restauração.
- Módulos transacionais e relatórios permanecem no backlog. Sem migração da planilha.

## Decisão de estoque inicial — 15/09/2026
- Autorizado usar o estoque da planilha como base atual de desenvolvimento, com abertura na data de corte e ajustes posteriores auditados.
- Alteração documental: carga e tela de ajustes permanecem na Fase 2, sem carga de dados nesta alteração.

## 0.2.0 — Produtos e estoque
- Cadastro manual, pesquisa SKU/nome, paginação, categorias, marcas, locais e inativação.
- Abertura, custo médio, entradas, saídas, ajustes, correção de custo, transferências, fracionamento e kits virtuais.
- Livro imutável, operações atômicas/idempotentes, estornos e auditoria.
- Carga inicial validada/idempotente da aba ESTOQUE MVET e conferência do livro.
- Interface Mercadovet e autorização de custos no backend.
- Testes de domínio, HTTP, permissões, importação, concorrência PostgreSQL e fluxo visual com dados sintéticos.
