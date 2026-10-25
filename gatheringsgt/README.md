# gatheringsgt.com (JOBS-76, parte A)

Sitio estático sin dependencias, alojado en Cloudflare Pages (proyecto `gatheringsgt`).

- `index.html`: versión de escritorio. En teléfono redirige a `/m/`.
- `m/index.html`: versión móvil ligera (una columna, sin hero ni navegación). En pantalla ancha redirige a `/`.
- `assets/shared.js`: productos (`PRODUCTS`), carrito, detalle de producto y envío por WhatsApp, compartidos por ambas versiones.
- `assets/detail.css`: estilos de la ventana de detalle de producto.
- `fotos/<producto>/`: fotos oficiales (JOBS-159). `card.jpg` es la de la tarjeta (4:3) y `1.jpg`, `2.jpg`… la galería del detalle.

La persona puede forzar una versión con el link «Ver versión móvil / de escritorio» (queda guardada en el navegador).

## Links
- Producto directo: `/?p=cozy` (o `/m/?p=cozy`); abre el detalle del producto con su galería. Cada tarjeta y cada detalle tienen «Copiar link».
- Tocar la foto, el nombre o «Ver detalle y fotos» de una tarjeta abre el detalle (el botón Atrás o Esc lo cierra).
- Pedido guardado: `/?pedido=cozy.2,single.1`; restaura el carrito en cualquier dispositivo. El carrito y el borrador del formulario también se guardan en el navegador.

## Cómo editar y redesplegar
- Productos, precios, descripciones y fotos: constante `PRODUCTS` en `assets/shared.js` (el orden de la lista es el del menú). `photo` es la foto de la tarjeta, `gallery` las fotos del detalle (`pics("cozy",5)` = `fotos/cozy/1.jpg`…`5.jpg`) e `incl` la lista de «Qué incluye» (vacía = «lo confirmamos por WhatsApp»).
- Cada producto lleva además `info` (líneas «Tamaño», «Porciones» o «Presentación»), `unit` (unidad del precio cuando no es «c/u»; The Grazing Table se pide por persona) y `note` (texto final del detalle). `incl` es un texto o una lista de viñetas.
- Fotos de boxes y domes: las que se ajustaron (zoom sin el corte del fondo azul, sin la tapa de las cajas) están ya recortadas en 4:3 (1200 × 900), porque la galería muestra las fotos en 4:3 y recorta al centro lo que sobra.
- Vista previa al compartir: `_worker.js` (Cloudflare Pages, modo avanzado) cambia las etiquetas `og:*` de `/?p=<id>` y `/m/?p=<id>` por las del producto (nombre, precio y foto de su tarjeta). WhatsApp y Facebook no ejecutan JavaScript, por eso se hace en el servidor. La lista `PRODUCTS` de `_worker.js` hay que mantenerla igual que la de `assets/shared.js` (nombre, precio, mínimo). Para refrescar una vista previa ya guardada: Facebook Sharing Debugger, o probar el link con un parámetro extra (`&x=1`).
- Desplegar: cada merge a `main` que cambie `gatheringsgt/` se publica solo en Cloudflare Pages como Production (`.github/workflows/desplegar-sitio.yml`: corre `node --test tests/site/cotizar.test.mjs` y luego `wrangler pages deploy`). El avance se ve en GitHub → Actions. Necesita los secretos de GitHub `CLOUDFLARE_API_TOKEN` (token con permiso Account → Cloudflare Pages → Edit) y `CLOUDFLARE_ACCOUNT_ID`. También se puede lanzar a mano desde Actions → Desplegar sitio → Run workflow.
- Plan B (a mano): Cloudflare → Workers & Pages → gatheringsgt → Create deployment → subir un zip con **toda esta carpeta** (`index.html`, `m/`, `assets/` y las fotos) como Production. Las variables y secretos del proyecto no cambian con ninguno de los dos métodos.

## Cotización por correo (Odoo)
- El formulario tiene dos botones: «Recibir cotización por correo» (usa `POST /api/cotizar`, en `_worker.js`) y «Finalizar pedido» (envía el pedido por chat; el botón de la barra inferior hace lo mismo). Nombre, teléfono, fecha, horario y dirección son obligatorios. El Worker manda a Odoo solo producto y cantidad más los datos del formulario; Odoo pone precios y mínimos, crea la cotización y se la envía al cliente. Si Odoo no responde, se ofrece el enlace a WhatsApp con el pedido.
- Variables, secretos de Pages, Service Token de Access y Turnstile (`TURNSTILE_KEY` en `assets/shared.js`): ver `odoo/addons/gatherings_cotizacion/README.md`. Pruebas: `node --test tests/site/cotizar.test.mjs`.
- Si cambias un precio, mínimo o producto, actualiza también `odoo/addons/gatherings_cotizacion/catalogo.py` (el test `odoo/tests/test_cotizacion_catalogo.py` avisa si quedan distintos).

## Estadísticas (Google Analytics 4)
- `assets/analytics.js` carga GA4 en ambas versiones. Usa el ID de medición `G-CMDLKTR9FJ` (constante `GA_ID`); si se deja vacío, queda apagado.
- Sin señales de publicidad. La primera visita muestra un aviso breve; «No permitir» desactiva la medición en ese navegador (se guarda en `localStorage`, clave `gt_analytics`).
- Departamento/ciudad: GA4 → Informes → Usuarios → Detalles demográficos → Región / Ciudad. La IP en Guatemala es imprecisa (datos móviles suelen salir como Ciudad de Guatemala).

## Línea gráfica (JOBS-156)
Recursos de marca en `assets/brand/` (optimizados a partir de la carpeta «Fotos Webpage» / Gatherings Visual Identity):
- Paleta: azul `#031666`, verde claro `#AFDCBF`, verde `#4EB969`, gris `#EBEBEB` (variables CSS al inicio de cada página).
- Tipografías de marca: Rossten (títulos, `assets/fonts/rossten.woff2`, convertida del .otf que pasó Allan) y Gotham Narrow (texto de apoyo). Gotham Narrow es de pago; mientras tanto el sitio usa **Barlow Semi Condensed** (licencia OFL, `assets/fonts/LICENSE-Barlow-OFL.txt`) declarada con el nombre «Gotham Narrow» en el `@font-face` de cada página: para usar la original basta reemplazar los tres `gotham-narrow-*.woff2` (400, 600 y 700). El archivo «Gotham Narrow XLight» de OnlineWebFonts es cursiva (−12°) y delgadísimo, por eso no se usó (además exige crédito CC BY 4.0).
- `logo-blanco.png`: logo sobre azul (encabezado y portada). `the-azul.png`: isotipo THE (recuadro de «Foto próximamente»). `romero-azul.png`: ramita de romero (pie). `icon-the.png` y `favicon.png`: ícono. `og.jpg`: imagen al compartir el link.
- Fondos: `fondo-the-azul.webp` (pedido; la portada y el menú van en color sólido), `fondo-romero-gris.webp` (cómo pedir y fondo móvil).
- Identidades visuales como encabezados: `the-board-*` (menú), `the-moment-*` (cómo pedir, y pedido en móvil), `the-sharing-*` (pedido en escritorio).
- «Artisan Charcuterie Boards» ya no se usa en el sitio.
