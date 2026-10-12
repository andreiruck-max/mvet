# ADR 0041 — MVet 2.0 e permissões operacionais explícitas

Aceito em 12/10/2026. A lista única dificultava revisar concessões e a criação exigia a administração técnica.

Funcionários passam a ser criados pelo master na própria interface, sem permissões, staff ou master. Perfis são sugestões editáveis de seleção, não grupos que concedem direitos silenciosamente. A edição preserva o lock do usuário, revisão otimista, negações explícitas e auditoria; inclui identificação e situação. Senhas passam pelos validadores Django e sua redefinição não registra conteúdo sensível.

A chave `__complete__` de AccessPolicy marca políticas revisadas pela versão 2.0. Nessas políticas, novas capacidades core são negadas por padrão. Não alterar políticas históricas parciais automaticamente; compatibilidade é preservada até a revisão do master. Nenhuma migration de estrutura é necessária.

A central de configurações admite gestores de domínios específicos apenas para seus atalhos; POST de parâmetros continua exigindo manage_configuration. Identificação 2.0 usa config/version.py nos templates e admin. Históricos, migrations anteriores e ADRs mantêm seus números originais.

Validação: criação forjada sem elevação, master protegido, redefinição e revogação de sessão, política completa sem herança de novas permissões, isolamento de configuração por domínio e fluxo no navegador desktop/celular.
