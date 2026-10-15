#!/usr/bin/env bash
# Respaldo de la base a odoo/backups/gatherings-AAAA-MM-DD.sql.gz (conserva 14). Pensado para cron/launchd en la Mac mini.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
mkdir -p backups
docker compose exec -T db pg_dump -U odoo "${ODOO_DB:-gatherings}" | gzip > "backups/${ODOO_DB:-gatherings}-$(date +%F).sql.gz"
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
