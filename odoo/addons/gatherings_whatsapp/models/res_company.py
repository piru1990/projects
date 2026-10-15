from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    wa_business_number = fields.Char(
        "Número de WhatsApp de la tienda", default="+502 5541-2293",
        help="Solo informativo: aparece en los mensajes como {telefono_tienda}. El chat se abre "
             "desde la sesión de WhatsApp Web de quien hace clic.",
    )
    wa_country_code = fields.Char(
        "Código de país por defecto", default="502",
        help="Se antepone a los teléfonos de 8 dígitos sin código de país.",
    )
