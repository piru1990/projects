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
    ws.append([None] * 16 + ["=SUM(Q2:Q5)"])
    ruta = tmp_path / "ventas.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_fechas_texto_y_invertidas(excel):
    p = {x.numero: x for x in normalize.leer_pedidos(excel)}
    assert p[1].fecha_pedido == dt.date(2025, 11, 27)
    assert p[2].fecha_pedido == dt.date(2025, 12, 3) and p[2].fecha_entrega == dt.date(2025, 12, 4)
    assert not any("MES" in a for x in p.values() for a in x.avisos)


def test_fila_de_totales_se_ignora_y_cuenta(excel):
    assert [x.numero for x in normalize.leer_pedidos(excel)] == [1, 2, 3, 4]


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
    assert sum(x.total for x in normalize.leer_pedidos(excel)) == 285 + 600 + 750 + 200


def test_aritmetica_rechaza_codigo():
    av = []
    assert normalize._numero("__import__('os')", av, "X") == 0.0 and av
    assert normalize._numero("=125+75", [], "X") == 200


class FakeOdoo:
    """Odoo en memoria: solo los dominios [(campo, '=', valor)] que usa el importador."""

    def __init__(self):
        self.t, self.n = {}, 0

    def search(self, model, domain, limit=None):
        filas = self.t.get(model, [])
        ids = [r["id"] for r in filas if all(r.get(c) == v for c, _, v in domain)]
        return ids[:limit] if limit else ids

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
    assert odoo.t == {} and c["pedidos"] == 4 and c["clientes"] == 3  # Ana (2 pedidos), Cliente no registrado, Luis


def test_carga_real_e_idempotente(excel):
    odoo, pedidos = FakeOdoo(), normalize.leer_pedidos(excel)
    c1 = import_sales.Cargador(odoo, aplicar=True).correr(pedidos)
    assert c1["pedidos"] == 4 and len(odoo.t["sale.order"]) == 4 and len(odoo.t["res.partner"]) == 3
    o1 = next(o for o in odoo.t["sale.order"] if o["name"] == "GT-0001")
    assert o1["state"] == "sale" and o1["date_order"] == "2025-11-27 18:00:00" and len(o1["order_line"]) == 2  # producto + envío
    o3 = next(o for o in odoo.t["sale.order"] if o["name"] == "GT-0003")
    assert o3["order_line"][0][2]["name"] == "Cozy y Single" and "Revisar:" in o3["note"]
    c2 = import_sales.Cargador(odoo, aplicar=True).correr(pedidos)
    assert c2["pedidos"] == 0 and c2["omitidos"] == 4 and len(odoo.t["sale.order"]) == 4 and len(odoo.t["product.template"]) == 7


def test_coherencia_de_anios():
    av = []
    assert normalize._coherencia_fechas(dt.date(2025, 2, 5), dt.date(2026, 2, 13), av) == (dt.date(2026, 2, 5), dt.date(2026, 2, 13))
    assert normalize._coherencia_fechas(dt.date(2026, 5, 6), dt.date(2025, 5, 10), av) == (dt.date(2026, 5, 6), dt.date(2026, 5, 10))
    assert len(av) == 2
    av = []  # entrega anterior sin arreglo posible: solo avisa
    assert normalize._coherencia_fechas(dt.date(2026, 9, 24), dt.date(2026, 9, 14), av) == (dt.date(2026, 9, 24), dt.date(2026, 9, 14))
    assert "anterior" in av[0]
