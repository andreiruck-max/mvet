# Implantação na Mercadovet

O código fica no GitHub; o servidor da empresa mantém PostgreSQL e aplicação. Os demais computadores acessam pelo navegador, com usuário próprio. Não precisam instalar Python, PostgreSQL ou Excel. O frontend já faz parte do repositório e da imagem Docker.

## Definir o destino

Registrar com o responsável técnico: sistema operacional e versão, memória e espaço livre, máquina que ficará ligada durante a operação, IP interno reservado ou nome DNS, responsável pelos backups e destino externo protegido. Não enviar senhas no GitHub ou em chamados públicos. Instalação no PC da empresa e acesso à rede ainda precisam ser executados presencialmente ou por acesso autorizado.

No Windows, seguir a instalação do Docker Desktop/WSL compatível com a máquina e suas políticas; no Linux, Docker Engine com Compose. A configuração concreta de HTTPS, certificado confiável e firewall depende da rede. Usar um servidor dedicado quando possível; impedir suspensão durante o expediente.

## Instalar e configurar

1. Seguir os comandos do README para clonar, configurar segredos, construir a imagem, aplicar migrations, inicializar a empresa e criar o master.
2. Manter o banco sem porta publicada. Validar inicialmente na própria máquina; antes do acesso compartilhado, configurar HTTPS conforme DEPLOYMENT.md. Não ativar redirecionamento SSL sem HTTPS funcionando.
3. Entrar como master, cadastrar canais e revisar Estoque Mercadovet/Full, estoque padrão, regras de imposto e contas financeiras. Campos comerciais podem ficar pendentes em rascunhos do master; a confirmação exige contexto e estoque válidos.
4. Criar usuários individuais em **Usuários e acessos**. Conceder faturamento, custos, margens, caixa, DRE e exportações de forma independente. Testar também a retirada de uma permissão.
5. Abrir saldos de estoque e financeiros conforme os guias de cada domínio, com corte em 15/09/2026. A carga do estoque em desenvolvimento não significa que os dados estejam no novo servidor. Não importar compras, vendas ou caixa da planilha integralmente.

## Checagem automática, sem escrita

Com a aplicação instalada:

```sh
docker compose exec -T web python manage.py check_installation
docker compose exec -T web python manage.py check_installation --network
docker compose exec -T web python manage.py check_installation --network --json
```

Saída 0 significa apenas que as verificações automáticas passaram. Saída 1 indica pendências. `--json` mantém relatório estruturado em stdout e mensagem de falha em stderr. O comando não cria cadastros, aplica migrations, testa senhas nem imprime configuração sensível. Verifica PostgreSQL/conexão, histórico e plano de migrations, DEBUG/hosts, master ativo, empresa, estoque padrão e canal ativo. `--network` também exige flags de cookies seguros e redirecionamento HTTPS.

Essas flags não comprovam certificado, proxy, firewall, isolamento da rede ou funcionamento do HTTPS. O comando tampouco valida força das senhas, privilégios do usuário PostgreSQL, arquivos estáticos, integridade dos saldos, agenda de backup ou recuperação. Executar também `check`, `check --deploy` e `check_inventory`; analisar cada resultado com o responsável técnico. Bling desconectado não impede a operação manual.

## Aceite no destino

Registrar data, versão do código (`git rev-parse HEAD`), responsável e resultado de cada verificação em registro interno protegido, sem dados comerciais no GitHub.

| Verificação | Evidência necessária |
|---|---|
| Rede | Dois computadores acessam por HTTPS confiável, sem publicar PostgreSQL |
| Sessões | Login individual, logout e acesso após reiniciar servidor |
| Permissões | Operador vê somente indicadores autorizados; URLs diretas e exportações respeitam restrições |
| Vendas | Venda manual sem NF, imposto zero pelo master, taxa MDR, escolha do estoque e confirmação |
| Estoque | Transferência entre locais e conciliação por check_inventory |
| Financeiro | Compra e parcela, pagamento único, caixa diário e transferência entre contas |
| Relatórios | Excel/PDF abrem e respeitam período, filtros e permissões |
| Recuperação | Backup restaurado em banco isolado e cópia externa conferida |
| Agendamento | Notificações e backup executam com log; falhas são detectadas |
| Bling, se utilizado | OAuth e notas reais homologados com conferência, sem usar custo externo |

Executar operações de teste em base isolada. Em produção, usar apenas operações reais aprovadas e estornos rastreáveis quando necessários; nunca apagar histórico para limpar testes.

## Atualização e recuperação

Antes de atualizar uma instalação existente, executar backup e teste de restauração e anotar o commit anterior. Em janela de manutenção, parar escritas, obter a versão aprovada, reconstruir, aplicar migrations e reiniciar; repetir a checagem e os testes de aceite afetados. Não fazer downgrade de código ou migration automaticamente: voltar a versão pode exigir restauração em banco novo. Ver BACKUP_RESTORE.md.

A conclusão desta preparação não equivale à implantação no computador da empresa. Para executar a próxima etapa, precisamos dos dados da máquina e do responsável técnico pelo acesso à rede.
