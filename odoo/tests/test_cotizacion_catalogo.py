"""El catálogo oficial del addon de cotizaciones debe coincidir con el del sitio (shared.js) y con el del Worker (_worker.js)."""
import importlib.util
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "catalogo", RAIZ / "odoo" / "addons" / "gatherings_cotizacion" / "catalogo.py")
catalogo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalogo)


def _sitio():
    """{id: (precio|None, mínimo, unidad)} leído del arreglo PRODUCTS de assets/shared.js."""
    texto = (RAIZ / "gatheringsgt" / "assets" / "shared.js").read_text(encoding="utf-8")
    bloque = texto[texto.index("const PRODUCTS = ["):texto.index("/* ====", texto.index("const PRODUCTS = ["))]
    out = {}
    for m in re.finditer(r'\{id:"([a-z-]+)",\s*name:"[^"]+",.*?price:(null|\d+)(?:,\s*min:(\d+))?(?:,\s*unit:"(\w+)")?', bloque):
        out[m.group(1)] = (None if m.group(2) == "null" else int(m.group(2)), int(m.group(3) or 1), m.group(4) or "")
    return out


def test_sitio_y_catalogo_coinciden():
    sitio = _sitio()
    assert len(sitio) == 14
    oficial = {p["web_id"]: (p["precio"] or None, p["minimo"], p.get("unidad", "")) for p in catalogo.PRODUCTOS}
    assert oficial == sitio


def test_worker_y_catalogo_coinciden():
    texto = (RAIZ / "gatheringsgt" / "_worker.js").read_text(encoding="utf-8")
    worker = {}
    for m in re.finditer(r'"([a-z-]+)": \{name: "[^"]+", price: (null|\d+)(?:, min: (\d+))?', texto):
        worker[m.group(1)] = (None if m.group(2) == "null" else int(m.group(2)), int(m.group(3) or 1))
    oficial = {p["web_id"]: (p["precio"] or None, p["minimo"]) for p in catalogo.PRODUCTOS}
    assert oficial == worker


def test_skus_y_ids_unicos():
    assert len({p["sku"] for p in catalogo.PRODUCTOS}) == len(catalogo.PRODUCTOS)
    assert len({p["web_id"] for p in catalogo.PRODUCTOS}) == len(catalogo.PRODUCTOS)
