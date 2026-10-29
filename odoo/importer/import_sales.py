#!/usr/bin/env python3
"""Importa el Excel de ventas a Odoo 18 Community (Ventas, Contactos, Inventario).

  python3 import_sales.py check  RUTA.xlsx            # solo lee y reporta (no toca Odoo)
  python3 import_sales.py load   RUTA.xlsx            # simula (dry-run) contra Odoo
  python3 import_sales.py load   RUTA.xlsx --apply    # crea catálogo, clientes y pedidos
  python3 import_sales.py load   RUTA.xlsx --apply --refresh   # además reescribe líneas de pedidos ya cargados

Conexión por variables de entorno: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD.
Es idempotente: pedidos (GT-0001...), productos (default_code) y clientes (nombre exacto) que ya existen se omiten
(con --refresh, los pedidos existentes se reescriben: líneas, producto, impuesto y nota).
Régimen de pequeño contribuyente (5 %): los precios son finales y las líneas no llevan impuesto, así el TOTAL no cambia.
Los pedidos históricos se crean ya confirmados (state=sale) sin pasar por action_confirm, así que no generan
entregas ni mueven inventario; el cobro y la entrega quedan en la nota del pedido.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from normalize import Pedido, clave_cliente, leer_pedidos, producto_exacto, resumen

CATALOGO_JSON = Path(__file__).resolve().parent.parent / "catalog.json"


def nombre_pedido(p: Pedido) -> str:
    return f"GT-{p.numero:04d}"


def _fecha_hora(d) -> str:
    return f"{d.isoformat()} 18:00:00"  # 12:00 en Guatemala (UTC-6): la fecha no se corre


def nota(p: Pedido) -> str:
    partes = []
    if p.horario:
        partes.append(f"Horario de entrega: {p.horario}")
    if p.direccion:
        partes.append(f"Dirección: {p.direccion}")
    if p.observaciones:
        partes.append(f"Observaciones: {p.observaciones}")
    pago = "Pagado" if p.pagado else "Pago pendiente"
    if p.metodo_pago:
        pago += f" ({p.metodo_pago})"
    if p.fecha_pago:
        pago += f" el {p.fecha_pago.isoformat()}"
    partes.append(pago)
    partes.append("Entregado" if p.entregado else "Entrega pendiente")
    if p.facturacion:
        partes.append(f"Facturación: {p.facturacion}")
    if p.avisos:
        partes.append("Revisar: " + "; ".join(p.avisos))
    return "\n".join(partes)


class Cargador:
    def __init__(self, rpc, aplicar: bool, refrescar: bool = False):
        self.rpc, self.aplicar, self.refrescar = rpc, aplicar, refrescar
        self.productos: dict[str, int] = {}   # sku -> product.product id
        self.clientes: dict[str, int] = {}    # clave -> res.partner id
        self.etiquetas: dict[str, int] = {}
        self.contador = {"productos": 0, "clientes": 0, "pedidos": 0, "omitidos": 0, "moneda": 0,
                         "actualizados": 0}

    def _buscar_o_crear(self, modelo: str, dominio: list, vals: dict, clave: str) -> int | None:
        ids = self.rpc.search(modelo, dominio, limit=1)
        if ids:
            return ids[0]
        self.contador[clave] += 1
        if not self.aplicar:
            return None
        return self.rpc.create(modelo, vals)

    def _impuesto(self) -> dict:
        # pequeño contribuyente (5 %): el precio es final y las líneas no llevan impuesto. Sin esto Odoo pone el 15 % genérico.
        return {"tax_id": [(6, 0, [])]}

    def catalogo(self) -> None:
        cat = json.loads(CATALOGO_JSON.read_text(encoding="utf-8"))
        items = [(p["sku"], p["nombre"], p["precio"], "consu") for p in cat["productos"]]
        items += [(s["sku"], s["nombre"], 0, "service") for s in cat["servicios"]]
        items.append((cat["historico"]["sku"], cat["historico"]["nombre"], 0, "service"))
        for sku, nombre, precio, tipo in items:
            vals = {"name": nombre, "default_code": sku, "list_price": precio, "type": tipo,
                    "sale_ok": True, "purchase_ok": tipo == "consu",
                    "taxes_id": [(6, 0, [])]}
            if tipo == "consu":
                vals["is_storable"] = True  # Odoo 18: producto almacenable (Inventario)
            tmpl = self._buscar_o_crear("product.template", [("default_code", "=", sku)], vals, "productos")
            if tmpl:
                self.productos[sku] = self.rpc.search("product.product", [("product_tmpl_id", "=", tmpl)], limit=1)[0]

    def etiqueta(self, nombre: str) -> int | None:
        if nombre not in self.etiquetas:
            ids = self.rpc.search("res.partner.category", [("name", "=", nombre)], limit=1)
            if ids:
                self.etiquetas[nombre] = ids[0]
            else:
                self.etiquetas[nombre] = self.rpc.create("res.partner.category", {"name": nombre}) if self.aplicar else None
        return self.etiquetas[nombre]

    def cliente(self, p: Pedido) -> int | None:
        k = clave_cliente(p.cliente)
        if k in self.clientes:
            return self.clientes[k]
        vals = {"name": p.cliente, "customer_rank": 1}
        if p.telefono:
            vals["phone"] = p.telefono
        if p.contacto:
            vals["comment"] = f"Contacto: {p.contacto}"
        if p.tipo_cliente:
            tag = self.etiqueta(p.tipo_cliente)
            if tag:
                vals["category_id"] = [(6, 0, [tag])]
        if p.empresa:
            vals["function"] = p.empresa
        cid = self._buscar_o_crear("res.partner", [("name", "=", p.cliente)], vals, "clientes")
        self.clientes[k] = cid
        return cid

    def moneda(self) -> None:
        """Odoo crea la base en USD y esa moneda manda en la compañía y en las listas de precios (y, por ellas, en
        cada pedido). Los montos del Excel son quetzales: se deja GTQ antes de crear pedidos."""
        gtq = self.rpc.call("res.currency", "search", [("name", "=", "GTQ"), ("active", "in", [True, False])], limit=1)
        if not gtq:
            raise RuntimeError("Odoo no tiene la moneda GTQ")
        empresa = self.rpc.call("res.company", "search_read", [], fields=["currency_id"], limit=1)[0]
        if empresa["currency_id"][0] == gtq[0]:
            return
        self.contador["moneda"] = 1
        if not self.aplicar:
            return
        self.rpc.call("res.currency", "write", gtq, {"active": True})
        self.rpc.call("res.company", "write", [empresa["id"]], {"currency_id": gtq[0]})
        listas = self.rpc.call("product.pricelist", "search", [("currency_id", "!=", gtq[0])])
        if listas:
            self.rpc.call("product.pricelist", "write", listas, {"currency_id": gtq[0]})

    def _linea(self, sku: str, cantidad: float, precio: float, nombre: str | None = None) -> tuple:
        vals = {"product_id": self.productos.get(sku), "product_uom_qty": cantidad, "price_unit": precio,
                **self._impuesto()}
        if nombre:
            vals["name"] = nombre
        return (0, 0, vals)

    def lineas(self, p: Pedido) -> list:
        if p.desglose:  # combo partido en productos de catálogo (+ línea de descuento)
            ls = [self._linea(sku, 1, precio) for sku, precio in p.desglose]
        elif p.sku is None:  # texto libre: línea histórica con el texto original
            ls = [self._linea("GT-OTROS", p.cantidad, p.precio_unitario, p.producto_texto)]
        else:  # «Cozy Box + Vino» entra como Cozy Box con el texto original en la descripción
            ls = [self._linea(p.sku, p.cantidad, p.precio_unitario,
                              None if producto_exacto(p.producto_texto) else p.producto_texto)]
        if p.envio:
            ls.append(self._linea("GT-ENVIO", 1, p.envio))
        return ls

    def pedido(self, p: Pedido) -> None:
        nombre = nombre_pedido(p)
        existente = self.rpc.search("sale.order", [("name", "=", nombre)], limit=1)
        if existente and not self.refrescar:
            self.contador["omitidos"] += 1
            return
        if existente:
            self.contador["actualizados"] += 1
            if self.aplicar:
                # Odoo no deja borrar líneas de un pedido confirmado: se baja a borrador, se reescriben y se vuelve a «sale»
                self.rpc.write("sale.order", existente, {"state": "draft"})
                self.rpc.write("sale.order", existente, {"note": nota(p), "order_line": [(5, 0, 0)] + self.lineas(p)})
                self.rpc.write("sale.order", existente, {"state": "sale"})
            return
        self.contador["pedidos"] += 1
        cliente = self.cliente(p)
        if not self.aplicar:
            return
        vals = {"name": nombre, "partner_id": cliente, "date_order": _fecha_hora(p.fecha_pedido),
                "state": "sale", "note": nota(p), "order_line": self.lineas(p)}
        if p.fecha_entrega:
            vals["commitment_date"] = _fecha_hora(p.fecha_entrega)
        self.rpc.create("sale.order", vals)

    def correr(self, pedidos: list[Pedido]) -> dict:
        self.moneda()
        self.catalogo()
        for p in pedidos:
            self.pedido(p)
        return self.contador


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["check", "load"])
    ap.add_argument("excel")
    ap.add_argument("--apply", action="store_true", help="crear de verdad en Odoo (sin esto, solo simula)")
    ap.add_argument("--refresh", action="store_true", help="reescribir líneas e impuesto de pedidos ya cargados")
    a = ap.parse_args(argv)
    pedidos = leer_pedidos(a.excel)
    print(resumen(pedidos))
    if a.modo == "check":
        return 0
    from rpc import OdooRPC
    try:
        rpc = OdooRPC(os.environ["ODOO_URL"], os.environ["ODOO_DB"], os.environ["ODOO_USER"], os.environ["ODOO_PASSWORD"])
    except KeyError as e:
        print(f"Falta la variable de entorno {e}", file=sys.stderr)
        return 2
    c = Cargador(rpc, a.apply, a.refresh).correr(pedidos)
    print(("CREADO" if a.apply else "SIMULACIÓN (usá --apply para crear)") + f": {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
