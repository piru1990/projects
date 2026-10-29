#!/usr/bin/env python3
"""Corrige 9 pedidos históricos que entraron como texto libre (GT-OTROS) pasándolos a productos del catálogo.

  python3 scripts/pedidos_historicos.py            # simula: muestra las líneas nuevas de cada pedido
  python3 scripts/pedidos_historicos.py --apply    # aplica (haga antes scripts/backup.sh)

Conexión por variables de entorno: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD. Es idempotente.
Cada pedido conserva su total: lo que no es producto de catálogo (vinos, extras, descuento) va en una línea «Extras»
o «Descuento» (GT-OTROS) y el texto original queda en la descripción. Si el total de algún pedido o la suma de todos
cambia, el script termina con error.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importer"))
from rpc import OdooRPC  # noqa: E402

OTROS = "GT-OTROS"

# número de pedido: (texto original, [(sku, cantidad, precio unitario, descripción o None)])
CORRECCIONES = {
    8: ("Cozy y Single", [("GT-COZY", 3, 260, None), ("GT-SINGLE", 3, 150, None),
                          (OTROS, 3, 340, "Extras (vinos y otros)")]),
    11: ("Cozy y Tailored", [("GT-COZY", 1, 260, None), ("GT-TAILORED", 1, 1050, None)]),
    43: ("Single y Gathering", [("GT-MINIDOME", 14, 30, "The Mini Dome (pedido original: Single y Gathering)")]),
    70: ("Single + vino", [("GT-SINGLE", 2, 125, "The Single (Single + vino)")]),
    71: ("1 The Single y 2 The Cozy (2 mini vinos)", [("GT-SINGLE", 1, 150, None), ("GT-COZY", 2, 260, None),
                                                    (OTROS, 1, -45, "Descuento (2 mini vinos)")]),
    90: ("Box del día del padre + homestyle", [("GT-HOMESTYLE", 1, 500, None),
                                              (OTROS, 1, 180, "Extras (box del día del padre)")]),
    100: ("Mini Box", [("GT-COZY", 1, 250, "The Cozy (pedido original: Mini Box)")]),
    106: ("Box + vino", [("GT-CELEBRATIONBOX", 61, 175, None), (OTROS, 61, 10, "Extras (vino)")]),
    109: ("Meriendas", [("GT-MINIDOME", 16, 30, "The Mini Dome (pedido original: Meriendas)"),
                        (OTROS, 16, 10, "Extras")]),
}


def total_pedidos(rpc) -> float:
    return round(sum(o["amount_total"] for o in rpc.call("sale.order", "search_read", [], fields=["amount_total"])), 2)


def correr(rpc, aplicar: bool) -> dict:
    resumen = {"corregidos": 0, "ya_corregidos": 0, "sin_pedido": 0}
    total_antes = total_pedidos(rpc)
    productos: dict[str, int] = {}

    def producto(sku: str) -> int:
        if sku not in productos:
            ids = rpc.search("product.product", [("default_code", "=", sku)], limit=1)
            if not ids:
                raise SystemExit(f"FALLÓ: no existe el producto {sku} en Odoo")
            productos[sku] = ids[0]
        return productos[sku]

    for numero, (texto, nuevas) in sorted(CORRECCIONES.items()):
        nombre = f"GT-{numero:04d}"
        pedido = rpc.search("sale.order", [("name", "=", nombre)], limit=1)
        if not pedido:
            print(f"  {nombre}: no existe")
            resumen["sin_pedido"] += 1
            continue
        lineas = rpc.call("sale.order.line", "search_read", [("order_id", "=", pedido[0])],
                          fields=["name", "product_id", "product_uom_qty", "price_unit"])
        otros = producto(OTROS)
        viejas = [l for l in lineas if l["product_id"] and l["product_id"][0] == otros and (l["name"] or "").strip().casefold() == texto.casefold()]
        if not viejas:
            print(f"  {nombre}: sin línea de texto libre «{texto}» (ya corregido)")
            resumen["ya_corregidos"] += 1
            continue
        quitar = sum(l["product_uom_qty"] * l["price_unit"] for l in viejas)
        poner = sum(q * p for _, q, p, _ in nuevas)
        if abs(quitar - poner) > 0.005:
            raise SystemExit(f"FALLÓ: {nombre} cambiaría de Q{quitar:,.2f} a Q{poner:,.2f}; no se toca nada")
        print(f"  {nombre}: «{texto}» (Q{quitar:,.2f}) -> " + "; ".join(
            f"{q:g} x {sku} a Q{p:g}" for sku, q, p, _ in nuevas))
        resumen["corregidos"] += 1
        if not aplicar:
            continue
        total_pedido = rpc.call("sale.order", "read", pedido, ["amount_total"])[0]["amount_total"]
        lineas_nuevas = []
        for sku, q, p, desc in nuevas:
            vals = {"product_id": producto(sku), "product_uom_qty": q, "price_unit": p, "tax_id": [(6, 0, [])]}
            if desc:
                vals["name"] = desc
            lineas_nuevas.append((0, 0, vals))
        # Odoo no deja cambiar líneas de un pedido confirmado: se baja a borrador y se vuelve a «sale» (como import_sales)
        rpc.write("sale.order", pedido, {"state": "draft"})
        rpc.write("sale.order", pedido, {"order_line": [(2, l["id"]) for l in viejas] + lineas_nuevas})
        rpc.write("sale.order", pedido, {"state": "sale"})
        despues = rpc.call("sale.order", "read", pedido, ["amount_total"])[0]["amount_total"]
        if abs(despues - total_pedido) > 0.005:
            raise SystemExit(f"FALLÓ: el total de {nombre} cambió de Q{total_pedido:,.2f} a Q{despues:,.2f}. "
                             "Restaure el respaldo y avise.")
    if aplicar:
        total_despues = total_pedidos(rpc)
        print(f"Suma de pedidos: antes Q{total_antes:,.2f}, después Q{total_despues:,.2f}")
        if total_antes != total_despues:
            raise SystemExit("FALLÓ: la suma de pedidos cambió. Restaure el respaldo y avise.")
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
