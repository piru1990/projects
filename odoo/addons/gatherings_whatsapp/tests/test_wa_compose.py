from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWaCompose(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Ana Pérez", "phone": "5541-2293"})
        cls.product = cls.env["product.product"].create({"name": "Cozy Box", "list_price": 150.0})
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "order_line": [(0, 0, {"product_id": cls.product.id, "product_uom_qty": 1})],
        })

    def _wizard(self, record, template_xmlid=None):
        action = record.action_open_whatsapp()
        wizard = self.env["gt.wa.compose"].browse(action["res_id"])
        if template_xmlid:
            wizard.template_id = self.env.ref(template_xmlid)
            wizard._onchange_template_id()
        return wizard

    def test_order_template_fills_values(self):
        wizard = self._wizard(self.order, "gatherings_whatsapp.wa_template_order_confirmed")
        self.assertIn("Ana Pérez", wizard.body)
        self.assertIn(self.order.name, wizard.body)
        self.assertNotIn("{", wizard.body)

    def test_open_url_and_chatter(self):
        wizard = self._wizard(self.partner, "gatherings_whatsapp.wa_template_partner_hello")
        before = len(self.partner.message_ids)
        action = wizard.action_open_whatsapp()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertTrue(action["url"].startswith("https://wa.me/50255412293?text="))
        self.assertGreater(len(self.partner.message_ids), before)

    def test_invalid_phone_is_rejected(self):
        wizard = self._wizard(self.partner)
        wizard.phone = "abc"
        with self.assertRaises(UserError):
            wizard.action_open_whatsapp()
