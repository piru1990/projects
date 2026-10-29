# Se ejecuta DENTRO de `odoo shell` (ver scripts/setup_cotizaciones.sh). Crea o actualiza el usuario técnico «Web Cotizaciones»
# que usa la función /api/cotizar del sitio, y genera su llave API. La llave se muestra una sola vez; Odoo solo guarda su hash.
import os

LOGIN = "web-cotizaciones"
GRUPOS = ["sales_team.group_sale_salesman_all_leads", "base.group_partner_manager"]   # Ventas: todos los documentos + crear contactos
if "crm.lead" in env:
    GRUPOS.append("sales_team.group_sale_salesman")

grupos = [env.ref(g).id for g in GRUPOS]
usuario = env["res.users"].with_context(active_test=False).search([("login", "=", LOGIN)], limit=1)
vals = {"name": "Web Cotizaciones", "login": LOGIN, "active": True, "groups_id": [(6, 0, grupos)],
        "notification_type": "email"}
if usuario:
    usuario.write(vals)
    print(f"Usuario {LOGIN} actualizado (id {usuario.id}).")
else:
    usuario = env["res.users"].with_context(no_reset_password=True).create(vals)
    print(f"Usuario {LOGIN} creado (id {usuario.id}).")

# El usuario técnico no tiene correo: como seguidor, los mensajes del chatter fallan con «Invalid email address».
# Se le quita de las cotizaciones, leads y contactos que ya lo tenían como seguidor (idempotente).
for modelo in ("sale.order", "crm.lead", "res.partner"):
    if modelo in env:
        seguidores = env["mail.followers"].sudo().search(
            [("res_model", "=", modelo), ("partner_id", "=", usuario.partner_id.id)])
        print(f"Seguidores del usuario técnico quitados en {modelo}: {len(seguidores)}")
        seguidores.unlink()

if os.environ.get("GT_NUEVA_LLAVE") == "1" or not env["res.users.apikeys"].sudo().search([("user_id", "=", usuario.id)]):
    # Sin vencimiento (Odoo limita a 90 días a los usuarios internos): usuario con permisos mínimos; para rotarla, volver a
    # correr este script con GT_NUEVA_LLAVE=1 y actualizar el secreto ODOO_API_KEY en Cloudflare Pages.
    llave = env["res.users.apikeys"].with_user(usuario).sudo()._generate(None, "sitio-web", None)
    print("\nLLAVE API (cópiala ahora, no se vuelve a mostrar):\n" + llave + "\n")
else:
    print("Ya tiene llave API. Para generar una nueva: GT_NUEVA_LLAVE=1 ./scripts/setup_cotizaciones.sh")
env.cr.commit()
