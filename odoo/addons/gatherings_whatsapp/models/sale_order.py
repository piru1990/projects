from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_whatsapp(self):
        self.ensure_one()
        return self.env["gt.wa.compose"].open_for(self._name, self.id)
