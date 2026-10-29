import importlib.util
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "importer"))
_spec = importlib.util.spec_from_file_location("pedidos_historicos", RAIZ / "scripts" / "pedidos_historicos.py")
ph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ph)

SKUS = ["GT-OTROS", "GT-COZY", "GT-SINGLE", "GT-TAILORED", "GT-MINIDOME", "GT-HOMESTYLE", "GT-CELEBRATIONBOX", "GT-ENVIO"]


class FakeOdoo:
    """Odoo en memoria: pedidos GT-0008... con una línea de texto libre y una de envío."""

    def __init__(self, sin=()):
        self.prod = {s: 100 + i for i, s in enumerate(SKUS)}
        self.pedidos, self.lineas, self.n, self.estados = {}, {}, 1000, []
        for num, (texto, nuevas) in ph.CORRECCIONES.items():
            if num in sin:
                continue
            oid = 500 + num
            self.pedidos[oid] = {"id": oid, "name": f"GT-{num:04d}", "state": "sale"}
            total = sum(q * p for _, q, p, _ in nuevas)
            self._linea(oid, "GT-OTROS", texto, nuevas[0][1], total / nuevas[0][1])
            self._linea(oid, "GT-ENVIO", "Envío", 1, 35)

    def _linea(self, oid, sku, nombre, q, p):
        self.n += 1
        self.lineas[self.n] = {"id": self.n, "order_id": oid, "name": nombre, "product_id": [self.prod[sku], sku],
                               "product_uom_qty": q, "price_unit": p}

    def _total(self, oid):
        return round(sum(l["product_uom_qty"] * l["price_unit"] for l in self.lineas.values() if l["order_id"] == oid), 2)

    def search(self, model, domain, limit=None):
        if model == "product.product":
            return [v for k, v in self.prod.items() if k == domain[0][2]]
        return [o["id"] for o in self.pedidos.values() if o["name"] == domain[0][2]][:limit]

    def call(self, model, method, *args, **kw):
        if model == "sale.order.line":
            return [dict(l) for l in self.lineas.values() if l["order_id"] == args[0][0][2]]
        if model == "sale.order" and method == "search_read":
            return [{"amount_total": self._total(o)} for o in self.pedidos]
        if model == "sale.order" and method == "read":
            return [{"amount_total": self._total(args[0][0])}]
        raise AssertionError((model, method))

    def write(self, model, ids, vals):
        oid = ids[0]
        if "state" in vals:
            self.pedidos[oid]["state"] = vals["state"]
            self.estados.append(vals["state"])
        for cmd in vals.get("order_line", []):
            if cmd[0] == 2:
                del self.lineas[cmd[1]]
            elif cmd[0] == 0:
                assert self.pedidos[oid]["state"] == "draft"      # Odoo solo deja cambiar líneas en borrador
                self.n += 1
                v = cmd[2]
                nombre = v.get("name") or next(s for s, i in self.prod.items() if i == v["product_id"])
                self.lineas[self.n] = {"id": self.n, "order_id": oid, "name": nombre, "tax_id": v["tax_id"],
                                       "product_id": [v["product_id"], nombre], "product_uom_qty": v["product_uom_qty"],
                                       "price_unit": v["price_unit"]}
        return True


def test_cada_correccion_conserva_su_total():
    for num, (_, nuevas) in ph.CORRECCIONES.items():
        assert sum(q * p for _, q, p, _ in nuevas) > 0, num
    assert sorted(ph.CORRECCIONES) == [8, 11, 43, 70, 71, 90, 100, 106, 109]


def test_simulacion_no_escribe():
    odoo = FakeOdoo()
    antes = {k: dict(v) for k, v in odoo.lineas.items()}
    r = ph.correr(odoo, aplicar=False)
    assert r == {"corregidos": 9, "ya_corregidos": 0, "sin_pedido": 0}
    assert odoo.lineas == antes and odoo.estados == []


def test_aplica_cambia_productos_y_conserva_totales_e_idempotente():
    odoo = FakeOdoo()
    totales = {o: odoo._total(o) for o in odoo.pedidos}
    assert ph.correr(odoo, aplicar=True)["corregidos"] == 9
    assert {o: odoo._total(o) for o in odoo.pedidos} == totales
    assert all(p["state"] == "sale" for p in odoo.pedidos.values())
    de_8 = [(l["name"], l["product_uom_qty"], l["price_unit"]) for l in odoo.lineas.values() if l["order_id"] == 508]
    assert ("Extras (vinos y otros)", 3, 340) in de_8 and ("Envío", 1, 35) in de_8 and len(de_8) == 4
    assert not any(l["name"] == "Cozy y Single" for l in odoo.lineas.values())
    assert all(l["tax_id"] == [(6, 0, [])] for l in odoo.lineas.values() if "tax_id" in l)
    assert ph.correr(odoo, aplicar=True) == {"corregidos": 0, "ya_corregidos": 9, "sin_pedido": 0}


def test_pedido_que_no_existe_se_reporta_y_total_distinto_aborta():
    assert ph.correr(FakeOdoo(sin=(8,)), aplicar=False)["sin_pedido"] == 1
    odoo = FakeOdoo()
    next(l for l in odoo.lineas.values() if l["name"] == "Cozy y Tailored")["price_unit"] = 1
    with pytest.raises(SystemExit, match="cambiaría"):
        ph.correr(odoo, aplicar=True)
