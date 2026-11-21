# ADR 0062 — Fundação cadastral de empresas (PR 1a)

19/11/2026. Exclusivo de develop/mvet-3.0; não aplicar no MVet 2.0.

A PR 1 foi dividida: 1a prepara cadastro e vínculos auditados; 1b aplicará seleção
empresarial e bloqueios nas rotas. Não há seletor nem isolamento transacional nesta
entrega. As permissões legadas continuam sendo a fonte das telas existentes.

Company preserva pk=1, todos os campos/histórico e o corte da Mercadovet. Acrescenta
nome fantasia, CNPJ único opcional, situação e revisão. A migration cadastra MVet
Agro com pk=2 INATIVA, sem inventar CNPJ. A restrição temporária no banco impede
ativar qualquer empresa secundária antes do escopo transacional. Principal é pk=1.
Cadastro é exclusivo master, auditado e protegido contra edição concorrente. CNPJ
informado não pode ser trocado pelo editor; correção exigirá procedimento explícito.
A validação atual é formato numérico de 14 posições e unicidade, não consulta fiscal.

UserCompanyAccess possui vínculo único usuário/empresa, situação, permissões
explícitas, autorização futura de Grupo e revisão. Ausência de vínculo nega no
avaliador empresarial. Empresa/usuário inativos sempre negam. Herança da política
legada só é permitida para a empresa 1. A migration vincula usuários já existentes
à Mercadovet sem reescrever AccessPolicy, grupos ou permissões; novos vínculos não
recebem capacidades automaticamente. O avaliador ainda NÃO substitui o backend
legado; interface informa expressamente que os vínculos estão em preparação.

Nenhuma venda, compra, saldo, comissão ou livro é migrado nesta etapa. A migration
de carga não oferece reversão destrutiva: para retornar, restaurar checkpoint
exclusivo do laboratório com código correspondente. Não executar no banco operacional.
A sequência de Company é corrigida após o cadastro explícito para novos IDs não
colidirem com 1/2. setup_mvet continua idempotente e preserva papéis existentes.

Validação: testes de serviços, permissões, CSRF, adulteração de POST, unicidade,
ativação bloqueada no banco, revisão, rollback da auditoria e carga idempotente;
regressão PostgreSQL 16 e Chromium, incluindo cadastro/vínculo pela interface.
Escopo empresarial em todos os módulos e regras de grupo continuam pendentes.
