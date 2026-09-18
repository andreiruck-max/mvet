# Backup e restauração
Backup local único é insuficiente. Scripts estão no repositório; agendamento e cópia externa devem ser configurados na máquina da empresa.

## Criar e verificar
```sh
bash scripts/backup.sh
```
Gera dump custom PostgreSQL, valida catálogo com pg_restore --list e move arquivo temporário para nome final. Permissões restritas pelo umask. O script não remove backups antigos.
Copiar resultado para armazenamento externo protegido e verificar cópia. Não versionar dados no Git.

## Política recomendada
Diário: 14 cópias. Semanal: 8 cópias. Mensal: 12 cópias. Manter ao menos uma cópia externa. Agendar por cron ou Agendador do Windows com WSL. Registrar execução, tamanho, hash e cópia externa. Retenção só após validar novas cópias.

## Teste de restauração isolado
```sh
bash scripts/test_restore.sh backups/ARQUIVO.dump
```
Cria banco temporário com nome próprio, restaura, consulta tabelas de empresa e usuários, remove apenas o banco de teste que criou. Não usa nem apaga mvet como destino. Teste periódico obrigatório. Catálogo legível sozinho não demonstra recuperabilidade; restauração é necessária.

## Recuperação real
1. Interromper escritas e preservar banco atual.
2. Selecionar backup já testado e compatível com a versão do código.
3. Criar banco novo vazio, restaurar com pg_restore --exit-on-error --no-owner --no-privileges.
4. Verificar tabelas, usuários, auditoria e totais; executar migrations apenas com plano de atualização.
5. Alterar configuração da aplicação para banco restaurado e reabrir após validação.
Nunca executar restore destrutivo sobre banco ativo sem cópia e revisão.

## Evidências na central
O script registra bytes e SHA-256 após validar o dump. Falhas tentam registrar evento e preservam código de saída; banco/app indisponível exige consultar log do agendador. Ative Monitorar backup em Notificações → Configurar alertas e agende `refresh_notifications` a cada 15 minutos. Sucesso significa arquivo/catalogação validados, não cópia externa nem restauração. Ausência de registro por mais que o prazo configurado gera alerta. Ver NOTIFICATIONS.md.

## Credenciais Bling

Tokens ficam criptografados no banco; guardar BLING_TOKEN_KEY em backup seguro separado. Perder a chave exige reautorização. Restaurar dump antigo pode recuperar refresh token já invalidado: master deve reautorizar antes da próxima consulta. Ambiente de teste de restauração não deve executar sync_bling nem receber segredos de produção.
