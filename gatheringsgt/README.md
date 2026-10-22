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
- Productos, precios, descripciones y fotos: constante `PRODUCTS` en `assets/shared.js`. `photo` es la foto de la tarjeta, `gallery` las fotos del detalle (`pics("cozy",5)` = `fotos/cozy/1.jpg`…`5.jpg`) e `incl` la lista de «Qué incluye» (vacía = «lo confirmamos por WhatsApp»).
- Pendiente (JOBS-159): precio, descripción y «Qué incluye» de The Little Box, The Celebration Box, The Mini Dome, The Big Dome y The Glass Dome; hoy se cotizan por WhatsApp. Las fotos se prepararon a 1200 px y menos de ~150 KB desde la carpeta «Photos gatherings.com».
- Desplegar: Cloudflare → Workers & Pages → gatheringsgt → Create deployment → subir un zip con **toda esta carpeta** (`index.html`, `m/`, `assets/` y las fotos) como Production.

## Estadísticas (Google Analytics 4)
- `assets/analytics.js` carga GA4 en ambas versiones. Está apagado mientras `GA_ID` esté vacío: pega el ID de medición (`G-XXXXXXXXXX`) y redespliega.
- Sin señales de publicidad. La primera visita muestra un aviso breve; «No permitir» desactiva la medición en ese navegador (se guarda en `localStorage`, clave `gt_analytics`).
- Departamento/ciudad: GA4 → Informes → Usuarios → Detalles demográficos → Región / Ciudad. La IP en Guatemala es imprecisa (datos móviles suelen salir como Ciudad de Guatemala).

## Línea gráfica (JOBS-156)
Recursos de marca en `assets/brand/` (optimizados a partir de la carpeta «Fotos Webpage» / Gatherings Visual Identity):
- Paleta: azul `#031666`, verde claro `#AFDCBF`, verde `#4EB969`, gris `#EBEBEB` (variables CSS al inicio de cada página).
- Tipografías de marca: Rossten (títulos) y Gotham Narrow (apoyo). Son fuentes con licencia que no están en el repo: las páginas las piden por nombre y, si no están instaladas, usan Georgia y la fuente del sistema. Para activarlas, agregar los archivos `.woff2` en `assets/fonts/` y declarar `@font-face`.
- `logo-blanco.png`: logo sobre azul (encabezado y portada). `the-azul.png`: isotipo THE (recuadro de «Foto próximamente»). `romero-azul.png`: ramita de romero (pie). `icon-the.png` y `favicon.png`: ícono. `og.jpg`: imagen al compartir el link.
- Fondos: `fondo-the-azul.webp` (portada y pedido), `fondo-romero-verde.webp` (menú), `fondo-romero-gris.webp` (cómo pedir y fondo móvil).
- Identidades visuales como encabezados: `the-board-*` (menú), `the-moment-*` (cómo pedir, y pedido en móvil), `the-sharing-*` (pedido en escritorio).
- «Artisan Charcuterie Boards» ya no se usa en el sitio.
