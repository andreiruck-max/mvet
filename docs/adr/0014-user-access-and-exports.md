# ADR 0014 — acesso individual e exportações autorizadas

Estado: aceito. Data: 18/09/2026.

## Decisão

Manter grupos/permissões Django e adicionar AccessPolicy individual explícita. Na primeira edição pelo master, cada capacidade conhecida recebe permitido/negado. Negação individual prevalece sobre grupo; novas capacidades permanecem negadas salvo concessão por grupo ou herança legada documentada. Master é superusuário ativo, não nome de grupo.

Backend único aplica a política em `has_perm`; views, serviços, templates e serializers usam o mesmo método. Não adicionar outro backend que possa voltar a conceder permissões negadas. Mudanças são auditadas e protegidas por lock/revisão. Usuários inativos não acessam; contas master não podem ser alteradas pelo formulário comum.

Separar faturamento, relatório detalhado, custo, margem, DRE, saldos e exportação. Conceder exportação não concede leitura. Dados proibidos são excluídos da projeção antes de serializar; não ocultados em planilha/PDF. Não confundir impedir consulta com impedir inferência: acesso a todos os componentes permite recompor lucro.

Serialização executada fora do lock do domínio; apenas leitura consistente usa transação. OOXML portátil e ReportLab mantêm instalação local independente de Excel, rede ou runtime privado. Mudança de autenticação exige novo login das sessões antigas.

## Compatibilidade

Capacidades operacionais específicas herdam permissões legadas até uma política individual explícita. Migration preserva o acesso gerencial antigo com concessões de relatório/margem a seus detentores; não concede exportação em massa. Master deve revisar os acessos antes da implantação. Revogações valem na próxima requisição, não para arquivos já baixados ou requisições em andamento.
