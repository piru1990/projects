import datetime as dt

import openpyxl
import pytest

import import_sales
import normalize

CAB = ["NÚMERO DE PEDIDO", "MES", "FECHA DEL PEDIDO", "FECHA DE ENTREGA", "HORARIO DE ENTREGA", "NOMBRE DEL CLIENTE",
       "NOMBRE DE EMPRESA", "TIPO DE CLIENTE", "CELULAR / WHATSAPP", "IG / FB / EMAIL", "CANTIDAD", "PRODUCTO",
       "SUBTOTAL", "DIRECCIÓN DE ENTREGA", "OBSERVACIONES INTERNAS / PERSONALIZACIÓN", "PRECIO DE ENVÍO", "TOTAL",
       "MÉTODO DE PAGO", "ESTADO DEL PAGO", "FECHA DE PAGO", "ESTADO DEL PEDIDO", "FACTURACIÓN"]


def fila(n, mes, f_ped, f_ent, cli, cant, prod, sub, envio, total=None, **extra):
    d = dict(zip(CAB, [n, mes, f_ped, f_ent, "Mañana", cli, None, None, None, None, cant, prod, sub, "Zona 10",
                       "Ninguna", envio, total, "Transferencia", "Pagado", None, "Entregado", None]))
    d.update(extra)
    return [d[c] for c in CAB]


@pytest.fixture
def excel(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Consolidado"
    ws.append(CAB)
    ws.append(fila(1, "NOVIEMBRE", "27/11/2025", "27/11/2025", "Ana Pérez", 1, "Cozy", 250, 35, "=(K2*M2)+P2"))
    # Excel leyó 3/12/2025 como 12 de marzo: mes y día invertidos
    ws.append(fila(2, "DICIEMBRE", dt.datetime(2025, 3, 12), dt.datetime(2025, 4, 12), "ana perez", 3, "The Tailored", "=125+75", 0, "=(K3*M3)+P3"))
    ws.append(fila(3, "ENERO", "05/01/2026", None, "No registrado", 1, "Cozy y Single", 750, None, "=(K4*M4)+P4",
                   **{"FECHA DE PAGO": "13/02/202", "ESTADO DEL PAGO": "Pendiente", "MÉTODO DE PAGO": "Pendiente"}))
    ws.append(fila(4, "ENERO", "06/01/2026", "06/01/2026", "Luis", 2, "Tailored", 200, 0, 200,
                   **{"CELULAR / WHATSAPP": 59781113.0, "NOMBRE DE EMPRESA": "Lumen Studio", "TIPO DE CLIENTE": "Corporativo"}))
    ws.append(fila(5, "ENERO", "07/01/2026", "07/01/2026", "Marta", 1, "Cozy + Single", 280, 0, 280))  # combo con descuento
    ws.append(fila(6, "ENERO", "08/01/2026", "08/01/2026", "Marta", 2, "The Cozy Box", 250, 0, 500))  # alias de catálogo
    ws.append([None] * 16 + ["=SUM(Q2:Q7)"])
    ruta = tmp_path / "ventas.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_fechas_texto_y_invertidas(excel):
    p = {x.numero: x for x in normalize.leer_pedidos(excel)}
    assert p[1].fecha_pedido == dt.date(2025, 11, 27)
    assert p[2].fecha_pedido == dt.date(2025, 12, 3) and p[2].fecha_entrega == dt.date(2025, 12, 4)
    assert not any("MES" in a for x in p.values() for a in x.avisos)


def test_fila_de_totales_se_ignora_y_cuenta(excel):
    assert [x.numero for x in normalize.leer_pedidos(excel)] == [1, 2, 3, 4, 5, 6]


def test_formula_en_subtotal(excel):
    p = {x.numero: x for x in normalize.leer_pedidos(excel)}
    assert p[2].precio_unitario == 200 and p[2].sku == "GT-TAILORED"


def test_producto_fuera_de_catalogo_y_cliente_no_registrado(excel):
    p3 = {x.numero: x for x in normalize.leer_pedidos(excel)}[3]
    assert p3.sku is None and p3.cliente == normalize.SIN_CLIENTE
    assert any("fuera del catálogo" in a for a in p3.avisos) and any("sin fecha de entrega" in a for a in p3.avisos)
    assert not p3.pagado and p3.metodo_pago is None and p3.fecha_pago == dt.date(2026, 2, 13)


def test_total_del_excel_manda_cuando_difiere(excel):
    p4 = {x.numero: x for x in normalize.leer_pedidos(excel)}[4]
    assert p4.total == 200 and p4.precio_unitario == 100 and any("TOTAL del Excel" in a for a in p4.avisos)
    assert p4.telefono == "+502 59781113" and p4.empresa == "Lumen Studio" and p4.tipo_cliente == "Corporativo"


def test_totales_coinciden_con_excel(excel):
    assert sum(x.total for x in normalize.leer_pedidos(excel)) == 285 + 600 + 750 + 200 + 280 + 500


def test_aritmetica_rechaza_codigo():
    av = []
    assert normalize._numero("__import__('os')", av, "X") == 0.0 and av
    assert normalize._numero("=125+75", [], "X") == 200


class FakeOdoo:
    """Odoo en memoria: solo los dominios [(campo, '=', valor)] que usa el importador."""

    def __init__(self, moneda_empresa=1):
        self.t, self.n, self.llamadas, self.moneda_empresa = {}, 0, [], moneda_empresa

    def search(self, model, domain, limit=None):
        filas = self.t.get(model, [])
        ids = [r["id"] for r in filas if all(r.get(c) == v for c, _, v in domain)]
        return ids[:limit] if limit else ids

    def call(self, model, method, *args, **kw):
        """Solo lo que usa Cargador.moneda(); `moneda_empresa` es el id de la moneda de la compañía simulada."""
        self.llamadas.append((model, method, args))
        if (model, method) == ("res.currency", "search"):
            return [1]  # GTQ
        if (model, method) == ("res.company", "search_read"):
            return [{"id": 1, "currency_id": [self.moneda_empresa, "X"]}]
        if method == "fields_get":
            return {"price_include_override": {}, "account_sale_tax_id": {}}
        if (model, method) == ("res.company", "search"):
            return [1]
        return [7] if method == "search" else True

    def write(self, model, ids, vals):
        self.llamadas.append((model, "write", (ids, vals)))
        for r in self.t.get(model, []):
            if r["id"] in ids:
                r.update(vals)
        return True

    def create(self, model, vals):
        self.n += 1
        vals = dict(vals, id=self.n)
        if model == "product.template":
            self.t.setdefault("product.product", []).append({"id": 1000 + self.n, "product_tmpl_id": self.n})
        self.t.setdefault(model, []).append(vals)
        return self.n


def test_carga_dry_run_no_crea(excel):
    odoo = FakeOdoo()
    c = import_sales.Cargador(odoo, aplicar=False).correr(normalize.leer_pedidos(excel))
    assert odoo.t == {} and c["pedidos"] == 6 and c["clientes"] == 4  # Ana (2 pedidos), Cliente no registrado, Luis, Marta


def test_carga_real_e_idempotente(excel):
    odoo, pedidos = FakeOdoo(), normalize.leer_pedidos(excel)
    c1 = import_sales.Cargador(odoo, aplicar=True).correr(pedidos)
    assert c1["pedidos"] == 6 and len(odoo.t["sale.order"]) == 6 and len(odoo.t["res.partner"]) == 4
    o1 = next(o for o in odoo.t["sale.order"] if o["name"] == "GT-0001")
    assert o1["state"] == "sale" and o1["date_order"] == "2025-11-27 18:00:00" and len(o1["order_line"]) == 2  # producto + envío
    assert "account.tax" not in odoo.t  # pequeño contribuyente: no se crea ningún impuesto
    assert all(l[2]["tax_id"] == [(6, 0, [])] for o in odoo.t["sale.order"] for l in o["order_line"])  # sin el 15 % por defecto
    o3 = next(o for o in odoo.t["sale.order"] if o["name"] == "GT-0003")
    assert o3["order_line"][0][2]["name"] == "Cozy y Single" and "Revisar:" in o3["note"]
    assert o3["order_line"][0][2]["product_id"] == odoo_sku(odoo, "GT-OTROS")
    c2 = import_sales.Cargador(odoo, aplicar=True).correr(pedidos)
    assert c2["pedidos"] == 0 and c2["omitidos"] == 6 and len(odoo.t["sale.order"]) == 6 and len(odoo.t["product.template"]) == 11


def test_moneda_se_corrige_a_gtq_solo_al_aplicar(excel):
    pedidos = normalize.leer_pedidos(excel)
    ya_gtq = FakeOdoo(moneda_empresa=1)
    assert import_sales.Cargador(ya_gtq, aplicar=True).correr(pedidos)["moneda"] == 0
    assert not [c for c in ya_gtq.llamadas if c[1] == "write" and "currency_id" in c[2][-1]]
    en_usd = FakeOdoo(moneda_empresa=2)  # la base nace en USD
    assert import_sales.Cargador(en_usd, aplicar=False).correr(pedidos)["moneda"] == 1
    assert not [c for c in en_usd.llamadas if c[1] == "write"]  # simulación: no escribe
    en_usd = FakeOdoo(moneda_empresa=2)
    assert import_sales.Cargador(en_usd, aplicar=True).correr(pedidos)["moneda"] == 1
    escritos = [(c[0], c[2][1]) for c in en_usd.llamadas if c[1] == "write"]
    assert ("res.company", {"currency_id": 1}) in escritos and ("product.pricelist", {"currency_id": 1}) in escritos


def test_coherencia_de_anios():
    av = []
    assert normalize._coherencia_fechas(dt.date(2025, 2, 5), dt.date(2026, 2, 13), av) == (dt.date(2026, 2, 5), dt.date(2026, 2, 13))
    assert normalize._coherencia_fechas(dt.date(2026, 5, 6), dt.date(2025, 5, 10), av) == (dt.date(2026, 5, 6), dt.date(2026, 5, 10))
    assert len(av) == 2
    av = []  # entrega anterior sin arreglo posible: solo avisa
    assert normalize._coherencia_fechas(dt.date(2026, 9, 24), dt.date(2026, 9, 14), av) == (dt.date(2026, 9, 24), dt.date(2026, 9, 14))
    assert "anterior" in av[0]


def odoo_sku(odoo, sku):
    tmpl = next(t["id"] for t in odoo.t["product.template"] if t["default_code"] == sku)
    return next(p["id"] for p in odoo.t["product.product"] if p["product_tmpl_id"] == tmpl)


def test_combo_se_parte_en_catalogo_con_descuento(excel):
    p5 = {x.numero: x for x in normalize.leer_pedidos(excel)}[5]
    assert p5.desglose == [("GT-COZY", 250.0), ("GT-SINGLE", 50.0), ("GT-DESCUENTO", -20.0)]
    assert any("con descuento" in a for a in p5.avisos)
    odoo = FakeOdoo()
    import_sales.Cargador(odoo, aplicar=True).correr(normalize.leer_pedidos(excel))
    o5 = next(o for o in odoo.t["sale.order"] if o["name"] == "GT-0005")
    assert [l[2]["price_unit"] for l in o5["order_line"]] == [250.0, 50.0, -20.0]
    assert sum(l[2]["price_unit"] * l[2].get("product_uom_qty", 1) for l in o5["order_line"]) == 280


def test_combo_con_extra_queda_como_texto_libre(excel):
    p3 = {x.numero: x for x in normalize.leer_pedidos(excel)}[3]  # «Cozy y Single» por 750 > lista 300
    assert p3.desglose is None and p3.sku is None


def test_alias_de_catalogo(excel):
    p6 = {x.numero: x for x in normalize.leer_pedidos(excel)}[6]
    assert p6.sku == "GT-COZYBOX" and p6.desglose is None


def test_refresh_reescribe_lineas_de_pedidos_existentes(excel):
    odoo, pedidos = FakeOdoo(), normalize.leer_pedidos(excel)
    import_sales.Cargador(odoo, aplicar=True).correr(pedidos)
    c = import_sales.Cargador(odoo, aplicar=True, refrescar=True).correr(pedidos)
    assert c["actualizados"] == 6 and c["pedidos"] == 0 and len(odoo.t["sale.order"]) == 6
    assert all(o["state"] == "sale" for o in odoo.t["sale.order"])
    sim = import_sales.Cargador(odoo, aplicar=False, refrescar=True).correr(pedidos)
    assert sim["actualizados"] == 6
