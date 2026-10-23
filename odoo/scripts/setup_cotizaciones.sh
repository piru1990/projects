#!/usr/bin/env bash
# Crea el usuario técnico y la llave API que usa el sitio para pedir cotizaciones a Odoo. Correr en la Mac mini, desde odoo/.
# Uso: ./scripts/setup_cotizaciones.sh            (la llave se muestra una vez)
#      GT_NUEVA_LLAVE=1 ./scripts/setup_cotizaciones.sh   (rota la llave)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
# `docker compose exec` no pasa por el entrypoint de la imagen (que arma la conexión a Postgres con HOST/USER/PASSWORD),
# así que se la damos a `odoo shell` con esas mismas variables del contenedor.
docker compose exec -T -e GT_NUEVA_LLAVE="${GT_NUEVA_LLAVE:-0}" odoo sh -c \
  'exec odoo shell -d "$1" --no-http --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD"' sh "${ODOO_DB:-gatherings}" \
  < scripts/setup_cotizaciones_shell.py 2>&1 | grep -v -E ' (INFO|WARNING) |pfb'
