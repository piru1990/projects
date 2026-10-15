# Correo de Odoo: hola@gatheringsgt.com (JOBS-80)

Odoo envía y recibe correo como **hola@gatheringsgt.com** a través de Google Workspace
(SMTP `smtp.gmail.com:587` STARTTLS, IMAP `imap.gmail.com:993` SSL). Los registros MX/SPF/DKIM del
dominio ya están en Cloudflare y no se tocan.

## Una sola vez, en Google (lo hace una persona con acceso a la cuenta)
1. Admin de Google → Seguridad → Autenticación → Verificación en 2 pasos: permitirla para hola@.
2. Con la sesión de hola@: myaccount.google.com → Seguridad → Contraseñas de aplicaciones → crear «Odoo».
3. Poner la contraseña de 16 caracteres en el `.env` de la Mac mini (no se sube al repo):

```
MAIL_APP_PASSWORD=abcd efgh ijkl mnop
ODOO_ADMIN_PASSWORD=...        # usuario admin de Odoo
# opcionales: MAIL_USER=hola@gatheringsgt.com  ODOO_DB=gatherings  ODOO_ADMIN_LOGIN=admin  ODOO_URL=http://127.0.0.1:8069
```

## Aplicar en producción
```
cd ~/Repos/projects/odoo
./scripts/backup.sh                       # respaldo antes de tocar la base
set -a; . ./.env; set +a
python3 scripts/setup_email.py --dry-run  # revisar
python3 scripts/setup_email.py            # crea/actualiza y prueba SMTP e IMAP
```
El script es idempotente: se puede correr de nuevo (por ejemplo al rotar la contraseña de app).

## Qué configura
- **Saliente** (`ir.mail_server`): usuario hola@, `from_filter = hola@gatheringsgt.com`.
- **Entrante** (`fetchmail.server`): IMAP SSL; la tarea programada «Mail: Fetchmail Service» lo
  revisa cada 5 minutos. Las respuestas a hilos existentes se enlazan solas. Un correo nuevo crea
  una iniciativa en CRM si el módulo `crm` está instalado; si no, no crea registros.
- **Parámetros**: dominio de alias `gatheringsgt.com`, alias `hola` (las respuestas vuelven a
  hola@) y remitente por defecto hola@gatheringsgt.com.

## Prueba manual
Enviar: Ajustes → Técnico → Servidores de correo saliente → «Probar conexión», y mandar un
correo desde el chatter de un cliente a tu correo personal. Recibir: escribir a hola@ y esperar
hasta 5 minutos (o Ajustes → Técnico → Servidores de correo entrante → «Obtener ahora»).
