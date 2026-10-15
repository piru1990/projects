#!/usr/bin/env bash
# Respaldo diario en odoo/backups/ (ignorado por git; permisos 700), conserva los últimos 14 de cada tipo:
#   gatherings-AAAA-MM-DD.sql.gz            base de datos (pg_dump)
#   gatherings-filestore-AAAA-MM-DD.tar.gz  adjuntos de Odoo (filestore)
# Pensado para launchd en la Mac mini (scripts/install-backup-launchd.sh). Sale con error si algo sale vacío.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"   # launchd arranca con un PATH mínimo (docker vive en Homebrew)
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
DB="${ODOO_DB:-gatherings}"; DIA="$(date +%F)"
umask 077; mkdir -p backups; chmod 700 backups

hecho() { [ -s "$1.tmp" ] || { echo "respaldo vacío: $1" >&2; rm -f "$1.tmp"; exit 1; }; mv "$1.tmp" "$1"; echo "ok $1 ($(du -h "$1" | cut -f1))"; }

docker compose exec -T db pg_dump -U odoo "$DB" | gzip > "backups/$DB-$DIA.sql.gz.tmp"
hecho "backups/$DB-$DIA.sql.gz"
gzip -t "backups/$DB-$DIA.sql.gz"   # verifica que el gzip no esté truncado

# El filestore es opcional: si Odoo todavía no guardó adjuntos, la carpeta puede no existir.
if docker compose exec -T odoo test -d "/var/lib/odoo/filestore/$DB"; then
  docker compose exec -T odoo tar czf - -C /var/lib/odoo/filestore "$DB" > "backups/$DB-filestore-$DIA.tar.gz.tmp"
  hecho "backups/$DB-filestore-$DIA.tar.gz"
fi

ls -1t backups/"$DB"-2*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
ls -1t backups/"$DB"-filestore-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
