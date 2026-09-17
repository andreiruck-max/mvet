#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p backups
target="backups/mvet-$(date -u +%Y%m%dT%H%M%S)-$$.dump"
temporary="${target}.partial"
backup_done=0
cleanup() {
  result=$?
  rm -f "$temporary"
  if [ "$result" -ne 0 ] && [ "$backup_done" -eq 0 ]; then
    docker compose exec -T web python manage.py record_backup failure || echo "Não foi possível registrar a falha no ERP; confira o log do agendador." >&2
  fi
  exit "$result"
}
trap cleanup EXIT
docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' > "$temporary"
docker compose exec -T db pg_restore --list < "$temporary" > /dev/null
test -s "$temporary"
mv "$temporary" "$target"
backup_done=1
backup_size=$(wc -c < "$target")
backup_hash=$(sha256sum "$target")
backup_hash=${backup_hash%% *}
docker compose exec -T web python manage.py record_backup success --size "$backup_size" --sha256 "$backup_hash" || {
  echo "Arquivo criado, mas a evidência não foi registrada no ERP. Confira o agendador." >&2
  exit 1
}
echo "Backup criado: $target"
echo "Copie para armazenamento externo e execute o teste de restauração."
