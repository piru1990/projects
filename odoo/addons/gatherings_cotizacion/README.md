# Gatherings · Cotizaciones web

Pedido en gatheringsgt.com → cotización en Odoo con los precios oficiales → PDF de marca por correo al cliente.

```
Formulario (index.html / m/index.html)
   └─ POST /api/cotizar  (gatheringsgt/_worker.js, Cloudflare Pages)
        └─ JSON-RPC a erp.gatheringsgt.com  (Service Token de Cloudflare Access + llave API del usuario «web-cotizaciones»)
             └─ sale.order.gt_web_quote()  (este addon)
                  ├─ crea/reutiliza el cliente (por correo), la cotización (7 días de validez) y un lead en CRM
                  ├─ precios oficiales IVA incluido: los pone Odoo, el sitio solo manda producto + cantidad
                  ├─ envío automático (correo + PDF adjunto, copia a hola@) si todo es de precio fijo y cumple el mínimo
                  └─ si no (The Tailored, The Experience, The Grazing Table, menos del mínimo, mucho tráfico o falla el correo):
                       queda en borrador, el cliente recibe un acuse y Andrea una actividad + correo para revisarla
```

Si Odoo no responde, el sitio muestra un enlace a WhatsApp con el pedido (el cliente nunca se queda sin respuesta).

## Qué instala
- Campos en producto: `gt_web_id` (id en el sitio), `gt_min_qty`, `gt_unit_label`, `gt_quote_mode` («Precio fijo» o «Requiere revisión»), y en la cotización los datos de entrega.
- Al instalar (`post_init_hook`): productos oficiales por SKU (precios, mínimos y modo; crea los que falten: Little Box, Celebration Box, Mini Dome, Big Dome, Glass Dome, Grazing Table), IVA 12 % incluido, logo/colores/pie de la compañía, `report.url = http://localhost:8069` (ver abajo) y el quetzal con el símbolo adelante. **Los pedidos ya hechos no cambian**: sus líneas guardan su precio.
- Informe «Cotización Gatherings» (PDF, texto fijo en español, Rossten + Barlow Semi Condensed, azul/menta/verde) y dos correos: «Cotización del sitio web» y «Pedido recibido, en revisión». Los correos no llevan enlaces al portal de Odoo (está detrás de Cloudflare Access) y cargan el logo desde gatheringsgt.com.
- Catálogo oficial en `catalogo.py`. Un test (`odoo/tests/test_cotizacion_catalogo.py`) falla si difiere de `assets/shared.js` o de `_worker.js`.

`report.url`: wkhtmltopdf baja CSS, fuentes y logo de `web.base.url` (https://erp…), que Cloudflare Access bloquea; con `report.url` los pide al propio Odoo y el PDF sale con marca. También arregla los PDF de Ventas que salgan sin estilos.

## Instalar en la Mac mini
1. Traer el código (`git pull` de `main`) y hacer respaldo: `odoo/scripts/backup.sh`.
2. Desde `odoo/`: `docker compose run --rm odoo odoo -d gatherings -i gatherings_cotizacion --stop-after-init` y `docker compose restart odoo`.
3. `./scripts/setup_cotizaciones.sh` crea el usuario técnico `web-cotizaciones` (Ventas + crear contactos, sin acceso a Ajustes) y muestra su llave API **una vez**. Es el secreto `ODOO_API_KEY` de Cloudflare Pages; no se sube al repo ni se pega en chats.
4. Revisar en Odoo: Ajustes → Compañías (logo y **Correo = hola@gatheringsgt.com**: es el remitente de las cotizaciones y el destino de los avisos de revisión; sin él los correos no salen y las cotizaciones quedan en borrador), un producto (pestaña «Sitio web y cotizaciones»), y que `hola@` siga enviando.

## Cloudflare
- **Access** (Zero Trust → Access → Service credentials): crear un Service Token «sitio-cotizaciones» y agregar a la aplicación de erp.gatheringsgt.com una política **Service Auth** que lo incluya (la política «Solo Allan y Andrea» no cambia).
- **Pages** (proyecto gatheringsgt → Settings → Variables and Secrets, Production): `ODOO_URL=https://erp.gatheringsgt.com`, `ODOO_DB=gatherings`, `ODOO_USER=web-cotizaciones`, y secretos `ODOO_API_KEY`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`. Opcional pero recomendado: Turnstile (`TURNSTILE_SECRET` como secreto y la clave pública en `TURNSTILE_KEY` de `assets/shared.js`).

## Pruebas
- `python3 -m pytest odoo/tests` y `node --test tests/site/cotizar.test.mjs` (no necesitan Odoo).
- Addon (necesita un Odoo 18 con `sale_management` y `crm`): `odoo -d PRUEBA -i gatherings_cotizacion --test-tags /gatherings_cotizacion --stop-after-init`.

## Operación
- «Ventas → Cotizaciones → filtro *Por revisar (sitio web)*»: lo que espera a Andrea; el motivo está en la pestaña de la cotización y en la actividad.
- Anticipo y formas de pago: Ajustes → Compañías → campo «Anticipo y forma de pago (cotizaciones)»; el texto (cada línea tal cual) va al final del PDF y del correo. Se edita sin tocar código.
- Para cambiar un precio o mínimo: editar el producto en Odoo **y** `catalogo.py`, `assets/shared.js` y `_worker.js` (el test avisa si quedan distintos). Que un producto pase por revisión se cambia en el producto («Cotización web»).
- Límites contra abuso: 5 solicitudes por correo al día; más de 30 por hora en total quedan en borrador sin correos al cliente (`catalogo.py`).
- Gotham Narrow original: reemplazar solo `static/fonts/gotham-narrow-*.ttf`.
