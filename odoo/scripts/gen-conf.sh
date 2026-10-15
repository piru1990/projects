#!/usr/bin/env bash
# Genera odoo/odoo.conf (ignorado por git, permisos 600) desde .env.
# Odoo 18 no tiene flag de línea de comandos para la contraseña maestra (admin_passwd): solo va en el archivo de configuración.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Falta .env (copia .env.example)"; exit 1; }
set -a; . ./.env; set +a
: "${ODOO_ADMIN_PASSWD:?define ODOO_ADMIN_PASSWD en .env}"
umask 077
cat > odoo.conf <<CONF
[options]
addons_path = /mnt/extra-addons
data_dir = /var/lib/odoo
admin_passwd = ${ODOO_ADMIN_PASSWD}
CONF
chmod 600 odoo.conf
