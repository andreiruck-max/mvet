#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Uso: bash scripts/test_restore.sh arquivo.dump" >&2
  exit 1
fi
backup="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$(dirname "$0")/.."
test_db="mvet_restore_test_$(date -u +%Y%m%d%H%M%S)_$$"
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$test_db"
cleanup() {
  docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" "$1"' sh "$test_db"
}
trap cleanup EXIT
docker compose exec -T db sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$1"' sh "$test_db" < "$backup"
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "SELECT count(*) FROM core_company; SELECT count(*) FROM auth_user;"' sh "$test_db"
echo "Restauração em banco isolado concluída."
