from odoo import fields, models

PAGO_POR_DEFECTO = ("Para confirmar tu pedido se requiere un anticipo. Respóndenos a este correo o escríbenos por WhatsApp "
                    "y te indicamos cómo realizarlo.")


class ResCompany(models.Model):
    _inherit = "res.company"

    gt_pago_texto = fields.Text(
        "Anticipo y forma de pago (cotizaciones)", default=PAGO_POR_DEFECTO,
        help="Texto que aparece al final del PDF y del correo de cada cotización: anticipo, cuentas o formas de pago. "
             "Cada línea se respeta tal cual.")
