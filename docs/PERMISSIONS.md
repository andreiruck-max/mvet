# Permissões
Implementado com User, Group e Permission nativos do Django. Serviços e views verificam permissões, não nomes de grupos. Operacional não ganha indicadores pelo direito de lançar.

| Perfil | Permissões iniciais |
|---|---|
| ADMINISTRADOR | Configuração, indicadores, DRE, custos, financeiro, lançar vendas/estoque/financeiro, consultar auditoria |
| GERENCIAL | Indicadores, DRE, custos |
| FINANCEIRO | Ver financeiro e operar pagamentos/recebimentos |
| VENDAS_OPERACIONAL | Operar vendas |
| ESTOQUE | Operar estoque |

Permissões de operar módulos são estrutura preparada; módulos não implementados ainda não têm telas de lançamento.
Administração de usuários/grupos exige superusuário ativo. O grupo ADMINISTRADOR não equivale a is_superuser. is_staff permite entrar no admin, mas não concede autorização para promover usuários.
Perfis podem ser personalizados no admin. setup_mvet só atribui permissões quando cria um grupo, preservando ajustes posteriores. Nenhum usuário/senha padrão é criado.
Custos e saldos não aparecem no início comum. URLs de indicadores, DRE e financeiro e /api/v1/indicadores validam autorização mesmo quando acessadas diretamente.
Auditoria registra alterações de configuração, identidades/permissões realizadas pelo admin, login/logout e troca de senha sem salvar credenciais nos logs.
Mudanças por shell/SQL não passam pelo fluxo auditado: são procedimentos administrativos excepcionais, não rotina operacional.
