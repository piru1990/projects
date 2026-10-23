import base64
import logging

from odoo.tools import file_open

from . import catalogo

_logger = logging.getLogger(__name__)

PIE = "WhatsApp +502 5541-2293 · hola@gatheringsgt.com · gatheringsgt.com"


def _iva(env):
    Tax = env["account.tax"]
    tax = Tax.search([("name", "=", catalogo.IVA["nombre"]), ("type_tax_use", "=", "sale")], limit=1)
    if not tax:
        # Odoo 18 usa price_include_override ('tax_included'); versiones anteriores, price_include (bool)
        incluido = {"price_include_override": "tax_included"} if "price_include_override" in Tax._fields else {"price_include": True}
        tax = Tax.create({"name": catalogo.IVA["nombre"], "amount": catalogo.IVA["porcentaje"], "amount_type": "percent",
                          "type_tax_use": "sale", **incluido})
    return tax


def _productos(env):
    """Crea o actualiza los productos del catálogo oficial (por SKU). No toca pedidos ya hechos: sus líneas guardan su precio."""
    Template = env["product.template"]
    iva = _iva(env)
    for p in catalogo.PRODUCTOS:
        vals = {
            "list_price": p["precio"],
            "gt_web_id": p["web_id"],
            "gt_min_qty": p["minimo"],
            "gt_unit_label": p.get("unidad", ""),
            "gt_quote_mode": "review" if p.get("revision") else "fixed",
        }
        tmpl = Template.search([("default_code", "=", p["sku"])], limit=1)
        if tmpl:
            tmpl.write(vals)
        else:
            nuevo = {**vals, "name": p["nombre"], "default_code": p["sku"], "type": "consu", "sale_ok": True,
                     "purchase_ok": "purchase_ok" in Template._fields, "taxes_id": [(6, 0, iva.ids)]}
            if "is_storable" in Template._fields:  # Odoo 18 con Inventario: producto almacenable, como el importador
                nuevo["is_storable"] = True
            Template.create(nuevo)
    _logger.info("Gatherings cotizaciones: %s productos al día", len(catalogo.PRODUCTOS))


def _marca(env):
    """Logo, colores y pie de los documentos de la compañía. Se aplica al instalar; el cambio manual posterior se respeta."""
    company = env.company
    with file_open("gatherings_cotizacion/static/img/logo-azul.png", "rb") as f:
        logo = base64.b64encode(f.read())
    company.write({
        "logo": logo,
        "primary_color": "#031666",
        "secondary_color": "#4EB969",
        "report_footer": PIE,
        **({} if company.email else {"email": "hola@gatheringsgt.com"}),   # remitente de los correos y destino de los avisos
        **({} if company.company_details else {"company_details": "<p>Gatherings GT<br/>hola@gatheringsgt.com</p>"}),
        "layout_background": "Blank",
        "external_report_layout_id": env.ref("web.external_layout_standard").id,
    })


def _url_pdf(env):
    """wkhtmltopdf baja el CSS, las fuentes y el logo de web.base.url (https://erp.gatheringsgt.com), que está detrás de
    Cloudflare Access y le devolvería la pantalla de login: el PDF saldría sin estilos. report.url hace que lo pida
    al propio Odoo, dentro del contenedor."""
    params = env["ir.config_parameter"].sudo()
    if not params.get_param("report.url"):
        params.set_param("report.url", "http://localhost:8069")


def _moneda(env):
    """Quetzal con el símbolo antes del monto (Q1,345.00), como en el sitio."""
    gtq = env["res.currency"].with_context(active_test=False).search([("name", "=", "GTQ")], limit=1)
    if gtq:
        gtq.write({"symbol": "Q", "position": "before"})


def post_init_hook(env):
    _productos(env)
    _marca(env)
    _url_pdf(env)
    _moneda(env)
