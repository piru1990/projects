from odoo import fields, models


class GtWaTemplate(models.Model):
    _name = "gt.wa.template"
    _description = "Plantilla de mensaje de WhatsApp"
    _order = "sequence, name"

    name = fields.Char("Nombre", required=True, translate=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model = fields.Selection(
        [("res.partner", "Cliente"), ("sale.order", "Pedido")],
        string="Se usa en", required=True, default="sale.order",
    )
    body = fields.Text(
        "Mensaje", required=True,
        help="Campos disponibles: {nombre}, {pedido}, {total}, {entrega}, {tienda}, {telefono_tienda}. "
             "Los que no apliquen (por ejemplo {pedido} en un cliente) quedan vacíos.",
    )
