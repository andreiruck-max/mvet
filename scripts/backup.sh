#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p backups
target="backups/mvet-$(date -u +%Y%m%dT%H%M%S)-$$.dump"
temporary="${target}.partial"
trap 'rm -f "$temporary"' EXIT
docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' > "$temporary"
docker compose exec -T db pg_restore --list < "$temporary" > /dev/null
test -s "$temporary"
mv "$temporary" "$target"
echo "Backup criado: $target"
echo "Copie para armazenamento externo e execute o teste de restauração."
