# gatherings_whatsapp (JOBS-79)

Odoo Community no trae WhatsApp (el módulo nativo es Enterprise). Este addon usa enlaces `wa.me`: abre WhatsApp Web con el mensaje listo y quien hace clic lo envía. No usa la API de WhatsApp ni vincula el número por QR, así que no hay riesgo de bloqueo ni costo.

- Botón **WhatsApp** en la ficha del cliente y en el pedido. Abre una ventana con teléfono, plantilla y mensaje editable; **Abrir en WhatsApp** deja el mensaje en el chatter y abre el chat en una pestaña nueva.
- Plantillas editables en Ventas > Configuración > Plantillas de WhatsApp. Campos: `{nombre}`, `{pedido}`, `{total}`, `{entrega}`, `{tienda}`, `{telefono_tienda}`. Vienen cuatro de ejemplo (confirmación, listo para entrega, recordatorio de pago, saludo).
- Ajustes > Compañías > WhatsApp: número de la tienda (+502 5541-2293, solo informativo, sale en `{telefono_tienda}`) y código de país por defecto (502) para teléfonos de 8 dígitos.
- El chat se abre desde la sesión de WhatsApp Web de quien hace clic: para que salga del +502 5541-2293, esa persona debe tener ese número vinculado en WhatsApp Web.
- No recibe mensajes en Odoo. Si más adelante hace falta, se puede subir a la API oficial de Meta sin cambiar las plantillas.

## Instalar (Mac mini)
Con la carpeta `odoo/addons` ya montada en el contenedor: reiniciar Odoo y, en modo desarrollador, Aplicaciones > Actualizar lista de aplicaciones > instalar «Gatherings WhatsApp». O por línea de comandos, desde `odoo/`:
```
docker compose run --rm odoo odoo -d gatherings -i gatherings_whatsapp --stop-after-init
docker compose restart odoo
```
Haga un respaldo antes (`scripts/backup.sh`).

## Pruebas
- Lógica pura (teléfonos, enlace, plantillas): `python3 -m pytest odoo/tests`.
- Con Odoo: `odoo -d BASE_DE_PRUEBA -i gatherings_whatsapp --test-tags /gatherings_whatsapp --stop-after-init` (usar una base desechable, no `gatherings`).
