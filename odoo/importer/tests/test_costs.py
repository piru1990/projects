import openpyxl
import pytest

import import_costs


def _hoja(ws, titulo, comida, empaque, mano, total, fila_total):
    ws.cell(1, 6).value = titulo
    ws.cell(3, 1).value = "ALIMENTOS"
    fila = 4
    for nombre, costo_pack, cant_pack, unidad, q, h in comida:
        ws.cell(fila, 1).value, ws.cell(fila, 2).value, ws.cell(fila, 3).value, ws.cell(fila, 4).value = nombre, costo_pack, cant_pack, unidad
        ws.cell(fila, 5).value, ws.cell(fila, 6).value, ws.cell(fila, 8).value = costo_pack / cant_pack, q, h
        fila += 1
    ws.cell(fila, 1).value, ws.cell(fila, 8).value = "COSTO DE ALIMENTOS", sum(c[5] for c in comida)
    ws.cell(fila + 1, 2).value = "EMPAQUES Y ENVÍO"
    fila += 2
    for nombre, costo, q, desc, h in empaque:
        ws.cell(fila, 1).value, ws.cell(fila, 2).value, ws.cell(fila, 3).value, ws.cell(fila, 4).value = nombre, costo, 1, "unidad"
        ws.cell(fila, 5).value, ws.cell(fila, 6).value, ws.cell(fila, 7).value, ws.cell(fila, 8).value = costo, q, desc, h
        fila += 1
    ws.cell(fila, 1).value, ws.cell(fila, 8).value = "COSTO DE EMPAQUES Y ENVÍO", sum(e[4] for e in empaque)
    ws.cell(fila + 2, 1).value, ws.cell(fila + 2, 8).value = "MANO DE OBRA", mano
    ws.cell(fila + 3, 1).value, ws.cell(fila + 3, 8).value = "COSTO TOTAL", total
    ws.cell(fila + 4, 1).value, ws.cell(fila + 4, 8).value = "MARGEN", 0.3        # no es una línea de la receta
    ws.cell(fila + 5, 1).value, ws.cell(fila + 5, 8).value = "PRECIO FINAL", 150


def _libro():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOARDS"
    _hoja(ws, "THE SINGLE (1 PERSONA)",
          [("Queso cheddar", 68.0, 1000.0, "gramos", 40.0, 2.72), ("Dátiles", 100.0, 200.0, "unidades", 2.0, 1.0)],
          [("Tabla de madera teca", 16.0, 1.0, "bamboo de 15*20 cm", 16.0), ("Sticker QR", 2.0, 0.0, "unidad", 1.0)],
          10.0, 30.72, 0)
    ws2 = wb.create_sheet("OTHERS")
    _hoja(ws2, "THE GOAT",
          [("Queso cheddar", 68.0, 1000.0, "gramos", 100.0, 6.8)],
          [("Tabla de madera teca", 16.0, 1.0, "20*30 cm", 33.0)],
          5.0, 44.8, 0)
    return wb


@pytest.fixture
def excel(tmp_path):
    ruta = tmp_path / "Costos.xlsx"
    _libro().save(ruta)
    return str(ruta)


@pytest.fixture
def excel_proveedor(tmp_path):
    """Como la hoja nueva de Andrea: encabezados en la fila 2 y PROVEEDOR insertada en la columna B."""
    wb = _libro()
    quien = {"Queso cheddar": "Pricesmart", "Dátiles": "Pricesmart", "Tabla de madera teca": "Raul Altamirano",
             "Sticker QR": "Gatherings"}
    for i, ws in enumerate(wb.worksheets):
        for col, t in enumerate(["PRODUCTO", "COSTO POR EMPAQUE", "CANTIDAD POR EMPAQUE", "UNIDAD DE MEDIDA"], 1):
            ws.cell(2, col).value = t
        ws.insert_cols(2)
        ws.cell(2, 2).value = "PROVEEDOR" if i == 0 else None    # en la hoja de Andrea, DOMES y OTHERS no tienen el título
        for fila in range(4, ws.max_row + 1):
            n = ws.cell(fila, 1).value
            if n in quien:
                ws.cell(fila, 2).value = quien[n].lower() if (i == 1 and n == "Queso cheddar") else quien[n]
    ruta = tmp_path / "Costos2.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_lee_recetas_y_costos(excel):
    r = {x.nombre: x for x in import_costs.leer_recetas(excel)}
    assert r["The Single"].sku == "GT-SINGLE" and r["The GOAT"].sku == "GT-GOAT"
    assert r["The Single"].costo() == pytest.approx(30.72) and r["The GOAT"].costo() == pytest.approx(44.8)
    assert r["The Single"].precio_hoja == 150 and not any("MARGEN" in c.nombre for c, _, _ in r["The Single"].lineas)


def test_gramos_se_guardan_en_kg_y_variantes_de_empaque_separadas(excel):
    r = {x.nombre: x for x in import_costs.leer_recetas(excel)}
    queso = next(c for c, q, u in r["The Single"].lineas if c.nombre == "Queso cheddar")
    assert queso.medida == "kg" and queso.costo == pytest.approx(68.0) and queso.codigo == "MP-QUESO-CHEDDAR"
    tablas = {c.nombre: c.costo for x in r.values() for c, _, _ in x.lineas if c.nombre.startswith("Tabla")}
    assert tablas == {"Tabla de madera teca (bamboo de 15*20 cm)": 16.0, "Tabla de madera teca (20*30 cm)": 33.0}


def test_cantidad_cero_con_costo_solo_si_cuadra_con_la_hoja(excel):
    r = {x.nombre: x for x in import_costs.leer_recetas(excel)}
    assert any(c.nombre == "Sticker QR" for c, _, _ in r["The Single"].lineas)
    assert any("se cuenta como 1" in a for a in r["The Single"].avisos)


class FakeOdoo:
    """Odoo en memoria con lo que usa import_costs."""

    def __init__(self):
        self.t, self.n, self.llamadas = {}, 0, []
        self.t["product.template"] = [{"id": 900, "default_code": "GT-SINGLE", "standard_price": 0}]
        self.t["product.product"] = [{"id": 9000, "product_tmpl_id": 900}]
        self.t["decimal.precision"] = [{"id": 1, "name": "Product Price", "digits": 2}]
        self.n = 1000

    def search(self, model, domain, limit=None):
        ids = [r["id"] for r in self.t.get(model, []) if all(r.get(c) == v for c, _, v in domain)]
        return ids[:limit] if limit else ids

    def create(self, model, vals):
        self.n += 1
        fila = dict(vals, id=self.n)
        if model == "product.template":
            self.t.setdefault("product.product", []).append({"id": self.n + 5000, "product_tmpl_id": self.n})
        self.t.setdefault(model, []).append(fila)
        return self.n

    def write(self, model, ids, vals):
        for r in self.t.get(model, []):
            if r["id"] in ids:
                r.update(vals)
        return True

    def call(self, model, method, *args, **kw):
        if method == "search_read" and model == "ir.model.data":
            return [{"name": "product_uom_kgm", "res_id": 1}, {"name": "product_uom_gram", "res_id": 2},
                    {"name": "product_uom_unit", "res_id": 3}]
        if method == "read":
            ids = args[0]
            return [dict(r) for r in self.t[model] if r["id"] in ids]
        if method == "fields_get":
            return {"gt_web_id": {}}
        raise AssertionError((model, method))


def test_carga_dry_run_no_escribe(excel):
    odoo = FakeOdoo()
    antes = {k: len(v) for k, v in odoo.t.items()}
    c = import_costs.Cargador(odoo, aplicar=False).correr(import_costs.leer_recetas(excel))
    assert {k: len(v) for k, v in odoo.t.items()} == antes and c["componentes"] > 0
    assert c["productos"] == len(import_costs._catalogo().PRODUCTOS) - 1   # todo el catálogo menos GT-SINGLE, que ya existe


def test_carga_real_idempotente_y_costo_igual_a_la_hoja(excel):
    odoo, recetas = FakeOdoo(), import_costs.leer_recetas(excel)
    c = import_costs.Cargador(odoo, aplicar=True)
    c.correr(recetas)
    assert odoo.t["decimal.precision"][0]["digits"] == 4
    assert [r["code"] for r in odoo.t["mrp.bom"]] == ["GT-COSTOS", "GT-COSTOS"]
    single = next(t for t in odoo.t["product.template"] if t["default_code"] == "GT-SINGLE")
    assert single["standard_price"] == pytest.approx(30.72)
    goat = next(t for t in odoo.t["product.template"] if t["default_code"] == "GT-GOAT")  # creado desde el catálogo
    assert goat["list_price"] == 65 and goat["gt_web_id"] == "the-goat" and goat["gt_quote_mode"] == "fixed"
    brk = next(t for t in odoo.t["product.template"] if t["default_code"] == "GT-BREAK")  # sin receta, pero el sitio lo vende
    assert brk["gt_quote_mode"] == "review" and brk["gt_web_id"] == "the-break"
    assert c.verificar(recetas) == []
    n_comp, n_bom = len(odoo.t["product.template"]), len(odoo.t["mrp.bom"])
    import_costs.Cargador(odoo, aplicar=True).correr(recetas)
    assert len(odoo.t["product.template"]) == n_comp and len(odoo.t["mrp.bom"]) == n_bom


def test_columna_proveedor_nueva_no_cambia_costos_ni_unidades(excel, excel_proveedor):
    viejo = {r.nombre: r for r in import_costs.leer_recetas(excel)}
    nuevo = {r.nombre: r for r in import_costs.leer_recetas(excel_proveedor)}
    for n, r in nuevo.items():
        assert r.costo() == pytest.approx(viejo[n].costo())
        assert [(c.codigo, c.medida, q, u) for c, q, u in r.lineas] == [(c.codigo, c.medida, q, u) for c, q, u in viejo[n].lineas]
    prov = {c.nombre: c.proveedor for r in nuevo.values() for c, _, _ in r.lineas if c.proveedor}
    assert prov["Queso cheddar"] == "Pricesmart"      # «pricesmart» escrito en minúscula en otra hoja = el mismo proveedor
    assert prov["Dátiles"] == "Pricesmart" and prov["Sticker QR"] == "Gatherings"
    assert not any("proveedor distinto" in a for r in nuevo.values() for a in r.avisos)


def test_proveedores_se_crean_y_enlazan_sin_duplicar(excel_proveedor):
    odoo, recetas = FakeOdoo(), import_costs.leer_recetas(excel_proveedor)
    antes = {k: len(v) for k, v in odoo.t.items()}
    c = import_costs.Cargador(odoo, aplicar=False).correr(recetas)
    assert c["proveedores"] == 2 and c["vinculos"] == 4     # Pricesmart y Raúl; Gatherings es costo propio
    assert {k: len(v) for k, v in odoo.t.items() if k in antes} == antes and "res.partner" not in odoo.t
    cargador = import_costs.Cargador(odoo, aplicar=True)
    cargador.correr(recetas)
    assert sorted(p["name"] for p in odoo.t["res.partner"]) == ["Pricesmart", "Raul Altamirano"]
    assert all(p["is_company"] and p["supplier_rank"] == 1 for p in odoo.t["res.partner"])
    info = odoo.t["product.supplierinfo"]
    queso = next(t["id"] for t in odoo.t["product.template"] if t["default_code"] == "MP-QUESO-CHEDDAR")
    assert next(i for i in info if i["product_tmpl_id"] == queso)["price"] == pytest.approx(68.0)   # por kg, como el componente
    assert len(info) == 4 and cargador.verificar(recetas) == []
    c2 = import_costs.Cargador(odoo, aplicar=True).correr(recetas)
    assert c2["proveedores"] == 0 and c2["vinculos"] == 0 and len(odoo.t["product.supplierinfo"]) == 4
    assert len(odoo.t["res.partner"]) == 2


def test_proveedor_faltante_hace_fallar_la_verificacion(excel_proveedor):
    odoo, recetas = FakeOdoo(), import_costs.leer_recetas(excel_proveedor)
    cargador = import_costs.Cargador(odoo, aplicar=True)
    cargador.correr(recetas)
    odoo.t["product.supplierinfo"].clear()
    assert any("sin proveedor" in f for f in cargador.verificar(recetas))
