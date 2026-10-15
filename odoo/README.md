# Odoo Community para Gatherings GT (JOBS-76, parte B)

Odoo 18 Community + PostgreSQL en la Mac mini (Docker), expuesto por Cloudflare Tunnel, e importador del Excel de ventas.

## Módulos (de la tabla del ticket)
| Necesidad | Módulo Odoo Community |
|---|---|
| Productos (SKU), producto final | `product` (viene con Ventas/Inventario) |
| Clientes | `contacts` + `crm` |
| Inventario de materiales, materias primas | `stock` |
| Compras, proveedores | `purchase` |
| Pedidos | `sale_management` |
| Materias primas -> producto terminado (para los costos de Andrea) | `mrp` (lista de materiales). Es adición mía: no estaba en la tabla, se puede quitar de `scripts/init-db.sh`. |

«Temporalidad por eventos» se resuelve con las fechas de cada pedido (`date_order`, `commitment_date`) y los movimientos de inventario/compras: todo es transaccional con fecha.

## Instalar (en la Mac mini)
1. Docker instalado (Docker Desktop, o Colima: `brew install colima docker docker-compose` + `colima start --cpu 2 --memory 3`; con Homebrew hay que añadir `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` a `~/.docker/config.json` para que exista `docker compose`). `cp .env.example .env` y completar contraseñas (el `.env` no se sube al repo; `chmod 600`).
2. `./scripts/init-db.sh` genera `odoo.conf` (contraseña maestra; ignorado por git), crea la base `gatherings` e instala los módulos.
3. `docker compose up -d` y abrir http://localhost:8069. El usuario `admin` nace con contraseña `admin`: cambiarla de inmediato (guardada en `.env` como `ODOO_ADMIN_USER_PASSWORD`; el importador la usa como `ODOO_PASSWORD`).
4. Respaldo diario: `./scripts/backup.sh` desde cron/launchd.

## Cloudflare Tunnel
Con `CLOUDFLARE_TUNNEL_TOKEN` en `.env`: `docker compose --profile tunnel up -d`. En Cloudflare Zero Trust, el túnel debe tener un hostname público que apunte al servicio `http://odoo:8069`.
**Pendiente de decidir:** el hostname necesita una zona DNS administrada por Cloudflare. `gatheringsgt.com` hoy está en Squarespace (con el correo de Google Workspace), así que hay que (a) pasar esa zona a Cloudflare copiando antes MX/SPF/DKIM, o (b) usar otro dominio ya en Cloudflare. Recomiendo además proteger el hostname con Cloudflare Access (login por correo) antes del login de Odoo.

## Importar el Excel de ventas
El Excel tiene datos de clientes: va en `odoo/data/` (ignorado por git), nunca al repo.
```
cd importer
python3 import_sales.py check ../data/Reporte_de_Ventas.xlsx           # lee y reporta, no toca Odoo
export ODOO_URL=http://localhost:8069 ODOO_DB=gatherings ODOO_USER=admin ODOO_PASSWORD=...
python3 import_sales.py load  ../data/Reporte_de_Ventas.xlsx           # simula
python3 import_sales.py load  ../data/Reporte_de_Ventas.xlsx --apply   # crea
```
Sin dependencias para cargar (XML-RPC estándar); `openpyxl` para leer el Excel. Es idempotente: se puede repetir.

Qué hace con el Excel real (111 pedidos, 27 nov 2025 a 14 oct 2026, Q73,930, igual al total de la hoja):
- Corrige las fechas que Excel leyó con día y mes invertidos (las 46 fechas reales) y valida contra la columna MES. Corrige años mal tecleados (pedido 46, entregas de 7 pedidos de mayo con 2025) y avisa de la entrega anterior al pedido (pedido 106).
- `SUBTOTAL` es el precio unitario; si el TOTAL de la hoja no cuadra (pedido 41), manda el TOTAL de la hoja.
- Crea el catálogo (`catalog.json`: SKU `GT-SINGLE`, `GT-COZY`, ...), clientes (79, unidos por nombre sin acentos ni mayúsculas) y pedidos `GT-0001`...
- 16 pedidos tienen producto en texto libre (combos, cajas, vino, «Little Dome»...): entran como línea «Otros productos (histórico)» con el texto original y la nota «Revisar:». Hay que decidir con Andrea si algunos pasan al catálogo.
- Pedidos históricos entran confirmados sin generar entregas, para no mover el inventario. Pago, entrega, dirección y facturación quedan en la nota del pedido.

## Estado de la verificación
Corrido contra un Odoo 18 real en la Mac mini (Colima) el 2026-10-14/15: 7 productos, 79 clientes y 111 pedidos `GT-0001`..`GT-0111`, suma Q73,930.00; la segunda corrida omite los 111 (idempotente). La primera carga reveló dos cosas que las pruebas con Odoo simulado no podían ver, ya corregidas en el importador:
- **Moneda:** Odoo crea la base en USD y los pedidos heredan esa moneda. El importador (`moneda()`) deja la compañía y las listas de precios en GTQ antes de crear pedidos.
- **Impuestos:** Odoo agrega un impuesto de venta por defecto (15 %) a cada línea, lo que sube el total a Q85,019.50. Las líneas importadas llevan `tax_id` vacío: los pedidos históricos van netos y el TOTAL de la hoja manda. El IVA del negocio (y el plan contable) se decide aparte con Andrea/contador.
Los campos usados son los de Odoo 18 (`type=consu` + `is_storable`). Pruebas: `python3 -m pytest importer/tests` (Odoo simulado y Excel sintético).

## Falta (siguientes pasos)
- Materias primas, proveedores y costos: llegan en el Excel de Andrea (importador análogo + listas de materiales).
- Parte C: formularios de captura para Andrea/el personal, y subdominios por producto (SKU).
