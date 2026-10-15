from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _wa_phone(self):
        """Teléfono a usar para WhatsApp: móvil si el campo existe (cambia entre versiones), si no el teléfono."""
        self.ensure_one()
        return (("mobile" in self._fields and self.mobile) or self.phone or "")

    def action_open_whatsapp(self):
        self.ensure_one()
        return self.env["gt.wa.compose"].open_for(self._name, self.id)
