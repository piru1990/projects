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
