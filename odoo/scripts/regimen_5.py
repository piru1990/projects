#!/usr/bin/env python3
"""Pasa Odoo del IVA 12 % incluido al régimen de pequeño contribuyente (5 %): precios finales, sin impuesto en las líneas.

  python3 scripts/regimen_5.py            # simula: cuenta lo que cambiaría
  python3 scripts/regimen_5.py --apply    # aplica (haga antes scripts/backup.sh)

Conexión por variables de entorno: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD. Es idempotente.
Qué hace: quita «IVA 12% (incluido)» de las líneas de pedidos y cotizaciones, de los productos y del impuesto de venta por
defecto de la compañía, y archiva el impuesto (no se borra). Los precios no cambian: con el IVA incluido el total de cada
línea ya era el precio, así que la suma de los pedidos debe quedar igual; si no, el script termina con error.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importer"))
from rpc import OdooRPC  # noqa: E402

IMPUESTO = "IVA 12% (incluido)"


def total_pedidos(rpc: OdooRPC) -> float:
    return round(sum(o["amount_total"] for o in rpc.call("sale.order", "search_read", [], fields=["amount_total"])), 2)


def correr(rpc: OdooRPC, aplicar: bool) -> dict:
    ids = rpc.search("account.tax", [("name", "=", IMPUESTO), ("type_tax_use", "=", "sale"), ("active", "in", [True, False])])
    resumen = {"impuestos": len(ids), "lineas": 0, "productos": 0, "compania": 0, "archivado": 0}
    if not ids:
        return resumen
    total_antes = total_pedidos(rpc)
    lineas = rpc.search("sale.order.line", [("tax_id", "in", ids)])
    productos = rpc.search("product.template", [("taxes_id", "in", ids), ("active", "in", [True, False])])
    empresas = rpc.search("res.company", [("account_sale_tax_id", "in", ids)])
    resumen.update(lineas=len(lineas), productos=len(productos), compania=len(empresas),
                   archivado=len(rpc.search("account.tax", [("id", "in", ids), ("active", "=", True)])))
    if not aplicar:
        return resumen
    for i in range(0, len(lineas), 100):
        rpc.write("sale.order.line", lineas[i:i + 100], {"tax_id": [(3, t) for t in ids]})
    if productos:
        rpc.write("product.template", productos, {"taxes_id": [(3, t) for t in ids]})
    if empresas:
        rpc.write("res.company", empresas, {"account_sale_tax_id": False})
    rpc.write("account.tax", ids, {"active": False})
    total_despues = total_pedidos(rpc)
    impuesto = round(sum(o["amount_tax"] for o in rpc.call("sale.order", "search_read", [], fields=["amount_tax"])), 2)
    print(f"Suma de pedidos: antes Q{total_antes:,.2f}, después Q{total_despues:,.2f}; impuesto restante Q{impuesto:,.2f}")
    if total_antes != total_despues or impuesto != 0:
        raise SystemExit("FALLÓ: el total cambió o quedó impuesto en algún pedido. Restaure el respaldo y avise.")
    return resumen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="aplicar de verdad (sin esto, solo simula)")
    a = ap.parse_args(argv)
    try:
        rpc = OdooRPC(os.environ["ODOO_URL"], os.environ["ODOO_DB"], os.environ["ODOO_USER"], os.environ["ODOO_PASSWORD"])
    except KeyError as e:
        print(f"Falta la variable de entorno {e}", file=sys.stderr)
        return 2
    r = correr(rpc, a.apply)
    print(("HECHO" if a.apply else "SIMULACIÓN (usá --apply para cambiar)") + f": {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
