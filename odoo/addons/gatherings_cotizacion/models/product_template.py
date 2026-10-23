from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    gt_web_id = fields.Char("Id en el sitio web", index=True, copy=False,
                            help="Id del producto en gatheringsgt.com (por ejemplo «single»). Vacío = no se vende desde el sitio.")
    gt_min_qty = fields.Integer("Pedido mínimo", default=1, help="Unidades mínimas por pedido en el sitio.")
    gt_unit_label = fields.Char("Unidad", help="Vacío = «c/u»; por ejemplo «persona» para The Grazing Table.")
    gt_quote_mode = fields.Selection(
        [("fixed", "Precio fijo: se envía solo"), ("review", "Requiere revisión de Andrea")],
        "Cotización web", default="fixed", required=True,
        help="«Requiere revisión»: la cotización queda en borrador y Andrea recibe aviso antes de enviarla al cliente.")
