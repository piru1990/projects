from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .. import wa_utils


class GtWaCompose(models.TransientModel):
    _name = "gt.wa.compose"
    _description = "Redactar mensaje de WhatsApp"

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    template_id = fields.Many2one(
        "gt.wa.template", string="Plantilla",
        domain="[('model', '=', res_model)]",
    )
    phone = fields.Char("Teléfono", help="Con o sin código de país; se normaliza al abrir WhatsApp.")
    body = fields.Text("Mensaje")

    @api.model
    def open_for(self, res_model, res_id):
        """Crea el asistente para un cliente o pedido y lo devuelve como acción de ventana."""
        record = self.env[res_model].browse(res_id)
        partner = record if res_model == "res.partner" else record.partner_id
        wizard = self.create({
            "res_model": res_model,
            "res_id": res_id,
            "partner_id": partner.id,
            "phone": partner._wa_phone() if partner else "",
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Enviar por WhatsApp"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _record(self):
        self.ensure_one()
        return self.env[self.res_model].browse(self.res_id)

    def _template_values(self):
        self.ensure_one()
        record = self._record()
        company = self.env.company
        order = record if self.res_model == "sale.order" else None
        total = ""
        entrega = ""
        if order:
            total = "%s%s" % (order.currency_id.symbol or "", "{:,.2f}".format(order.amount_total))
            if order.commitment_date:
                entrega = fields.Datetime.context_timestamp(self, order.commitment_date).strftime("%d/%m/%Y")
        return {
            "nombre": self.partner_id.name or "",
            "pedido": order.name if order else "",
            "total": total,
            "entrega": entrega,
            "tienda": company.name or "",
            "telefono_tienda": company.wa_business_number or "",
        }

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id:
            self.body = wa_utils.render(self.template_id.body, self._template_values())

    def action_open_whatsapp(self):
        self.ensure_one()
        phone = wa_utils.normalize_phone(
            self.phone, self.env.company.wa_country_code or wa_utils.DEFAULT_COUNTRY_CODE
        )
        if not phone:
            raise UserError(_("El teléfono «%s» no es válido para WhatsApp. Revisalo o escribilo con código de país.") % (self.phone or ""))
        text = (self.body or "").strip()
        record = self._record()
        record.message_post(
            body=Markup("<b>WhatsApp</b> a +%s:<br/>%s") % (phone, Markup("<br/>").join(text.splitlines()) if text else _("(sin mensaje)")),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        return {
            "type": "ir.actions.act_url",
            "url": wa_utils.build_url(phone, text),
            "target": "new",
        }
