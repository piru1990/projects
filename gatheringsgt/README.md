# gatheringsgt.com (JOBS-76, parte A)

Sitio estático sin dependencias, alojado en Cloudflare Pages (proyecto `gatheringsgt`).

- `index.html`: versión de escritorio. En teléfono redirige a `/m/`.
- `m/index.html`: versión móvil ligera (una columna, sin hero ni navegación). En pantalla ancha redirige a `/`.
- `assets/shared.js`: productos (`PRODUCTS`), carrito y envío por WhatsApp, compartidos por ambas versiones.

La persona puede forzar una versión con el link «Ver versión móvil / de escritorio» (queda guardada en el navegador).

## Links
- Producto directo: `/?p=cozy` (o `/m/?p=cozy`); resalta el producto. Cada tarjeta tiene «Copiar link».
- Pedido guardado: `/?pedido=cozy.2,single.1`; restaura el carrito en cualquier dispositivo. El carrito y el borrador del formulario también se guardan en el navegador.

## Cómo editar y redesplegar
- Productos, precios y fotos: constante `PRODUCTS` en `assets/shared.js` (`photo` es una ruta desde la raíz, p. ej. `fotos/cozy.jpg`).
- Desplegar: Cloudflare → Workers & Pages → gatheringsgt → Create deployment → subir un zip con **toda esta carpeta** (`index.html`, `m/`, `assets/` y las fotos) como Production.

## Línea gráfica (JOBS-156)
Recursos de marca en `assets/brand/` (optimizados a partir de la carpeta «Fotos Webpage» / Gatherings Visual Identity):
- Paleta: azul `#031666`, verde claro `#AFDCBF`, verde `#4EB969`, gris `#EBEBEB` (variables CSS al inicio de cada página).
- Tipografías de marca: Rossten (títulos) y Gotham Narrow (apoyo). Son fuentes con licencia que no están en el repo: las páginas las piden por nombre y, si no están instaladas, usan Georgia y la fuente del sistema. Para activarlas, agregar los archivos `.woff2` en `assets/fonts/` y declarar `@font-face`.
- `logo-blanco.png`: logo sobre azul (encabezado y portada). `the-azul.png`: isotipo THE (recuadro de «Foto próximamente»). `romero-azul.png`: ramita de romero (pie). `icon-the.png` y `favicon.png`: ícono. `og.jpg`: imagen al compartir el link.
- Fondos: `fondo-the-azul.webp` (portada y pedido), `fondo-romero-verde.webp` (menú), `fondo-romero-gris.webp` (cómo pedir y fondo móvil).
- Identidades visuales como encabezados: `the-board-*` (menú), `the-moment-*` (cómo pedir, y pedido en móvil), `the-sharing-*` (pedido en escritorio).
- «Artisan Charcuterie Boards» ya no se usa en el sitio.
