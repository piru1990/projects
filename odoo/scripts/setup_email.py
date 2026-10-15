#!/usr/bin/env python3
"""Configura el correo de Odoo (envío y recepción) para hola@gatheringsgt.com (JOBS-80).

Crea o actualiza, de forma idempotente y por XML-RPC:
  - un servidor de correo saliente (Gmail SMTP, STARTTLS 587),
  - un servidor de correo entrante (Gmail IMAP, SSL 993),
  - el dominio de alias y el remitente por defecto.

Los secretos se leen de variables de entorno (por ejemplo del `.env` de la Mac mini); nunca
se escriben en el repo. Ver odoo/EMAIL.md.

Uso, desde odoo/:  set -a; . ./.env; set +a; python3 scripts/setup_email.py [--dry-run] [--no-test]
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client

DOMAIN = "gatheringsgt.com"
MAILBOX = f"hola@{DOMAIN}"
SMTP_NAME = "Gmail SMTP (hola@gatheringsgt.com)"
IMAP_NAME = "Gmail IMAP (hola@gatheringsgt.com)"


def build_smtp_vals(user: str, password: str) -> dict:
    return {
        "name": SMTP_NAME,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_encryption": "starttls",
        "smtp_authentication": "login",
        "smtp_user": user,
        "smtp_pass": password,
        # Solo este remitente sale por este servidor; evita que Gmail reescriba el From.
        "from_filter": MAILBOX,
        "sequence": 1,
    }


def build_imap_vals(user: str, password: str, model_id: int | None) -> dict:
    vals = {
        "name": IMAP_NAME,
        "server_type": "imap",
        "server": "imap.gmail.com",
        "port": 993,
        "is_ssl": True,
        "user": user,
        "password": password,
    }
    if model_id:
        # Correos nuevos (que no son respuesta a un hilo) crean un registro de este modelo.
        vals["object_id"] = model_id
    return vals


def build_params() -> dict:
    """Parámetros del sistema: dominio de alias y remitente por defecto."""
    return {
        "mail.catchall.domain": DOMAIN,
        "mail.catchall.alias": "hola",
        "mail.default.from": MAILBOX,
    }


class Rpc:
    def __init__(self, url: str, db: str, user: str, password: str):
        url = url.rstrip("/")
        self.db, self.password = db, password
        self._models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, password, {})
        if not self.uid:
            raise SystemExit("Odoo rechazó el usuario o la contraseña de ODOO_ADMIN_LOGIN / ODOO_ADMIN_PASSWORD")

    def call(self, model: str, method: str, *args, **kw):
        return self._models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)


def upsert(rpc: Rpc, model: str, name: str, vals: dict, dry_run: bool) -> int | None:
    found = rpc.call(model, "search", [("name", "=", name)], limit=1)
    action = "actualizar" if found else "crear"
    print(f"- {model}: {action} «{name}»" + (" (dry-run)" if dry_run else ""))
    if dry_run:
        return found[0] if found else None
    if found:
        rpc.call(model, "write", found, vals)
        return found[0]
    return rpc.call(model, "create", vals)


def lead_model_id(rpc: Rpc) -> int | None:
    """crm.lead si CRM está instalado; si no, los correos nuevos no crean registros."""
    ids = rpc.call("ir.model", "search", [("model", "=", "crm.lead")], limit=1)
    return ids[0] if ids else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="solo muestra qué haría")
    ap.add_argument("--no-test", action="store_true", help="no probar las conexiones al terminar")
    args = ap.parse_args()

    env = os.environ
    missing = [k for k in ("ODOO_ADMIN_PASSWORD", "MAIL_APP_PASSWORD") if not env.get(k)]
    if missing:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(missing)} (ver odoo/EMAIL.md)")
    # Desde la Mac mini se usa el puerto local, no el túnel (que está tras Cloudflare Access).
    rpc = Rpc(
        env.get("ODOO_URL", "http://127.0.0.1:8069"),
        env.get("ODOO_DB", "gatherings"),
        env.get("ODOO_ADMIN_LOGIN", "admin"),
        env["ODOO_ADMIN_PASSWORD"],
    )
    mail_user = env.get("MAIL_USER", MAILBOX)
    password = env["MAIL_APP_PASSWORD"].replace(" ", "")  # Google la muestra en bloques de 4

    smtp_id = upsert(rpc, "ir.mail_server", SMTP_NAME, build_smtp_vals(mail_user, password), args.dry_run)
    imap_id = upsert(
        rpc, "fetchmail.server", IMAP_NAME, build_imap_vals(mail_user, password, lead_model_id(rpc)), args.dry_run
    )
    for key, value in build_params().items():
        print(f"- ir.config_parameter: {key} = {value}" + (" (dry-run)" if args.dry_run else ""))
        if not args.dry_run:
            rpc.call("ir.config_parameter", "set_param", key, value)
    if args.dry_run or args.no_test:
        return 0

    ok = True
    for model, rid, method, label in (
        ("ir.mail_server", smtp_id, "test_smtp_connection", "SMTP"),
        ("fetchmail.server", imap_id, "button_confirm_login", "IMAP"),
    ):
        try:
            rpc.call(model, method, [rid])
            print(f"✓ {label}: conexión correcta")
        except xmlrpc.client.Fault as e:
            ok = False
            print(f"✗ {label}: {e.faultString.strip().splitlines()[-1]}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
