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
1. Docker Desktop instalado. `cp .env.example .env` y completar contraseñas (el `.env` no se sube al repo).
2. `./scripts/init-db.sh` crea la base `gatherings` e instala los módulos.
3. `docker compose up -d` y abrir http://localhost:8069 (usuario `admin`, pone la contraseña en el primer ingreso).
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
Las pruebas del importador (`python3 -m pytest importer/tests`) usan un Odoo simulado y un Excel sintético. **No se ha corrido contra un Odoo real** (el entorno donde se escribió no tiene Docker en ejecución); la primera carga real en la Mac mini es la verificación. Los campos usados son los de Odoo 18 (`type=consu` + `is_storable`).

## Falta (siguientes pasos)
- Materias primas, proveedores y costos: llegan en el Excel de Andrea (importador análogo + listas de materiales).
- Parte C: formularios de captura para Andrea/el personal, y subdominios por producto (SKU).
