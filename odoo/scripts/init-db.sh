#!/usr/bin/env bash
# Crea la base y instala los módulos de Odoo Community. Correr una sola vez, desde la carpeta odoo/.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Falta .env (copiá .env.example)"; exit 1; }
set -a; . ./.env; set +a
DB="${ODOO_DB:-gatherings}"
# contacts+crm: clientes · sale_management: pedidos · stock: inventario · purchase: compras y proveedores
# mrp: lista de materiales (materias primas -> producto terminado), para los costos de Andrea.
docker compose up -d db
docker compose run --rm odoo odoo -d "$DB" -i base,contacts,crm,sale_management,purchase,stock,mrp \
  --without-demo=all --stop-after-init
echo "Listo. Levantá todo con: docker compose up -d   (con túnel: docker compose --profile tunnel up -d)"
