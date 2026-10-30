from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

from .. import catalogo


@tagged("post_install", "-at_install")
class TestWebQuote(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.email = "hola@gatheringsgt.com"
        cls.Order = cls.env["sale.order"]
        cls.manana = (fields.Date.today() + timedelta(days=3)).isoformat()

    def pedido(self, items, **extra):
        base = {"nombre": "Ana Pérez", "correo": "ana@example.com", "telefono": "5555-1234", "fecha": self.manana,
                "horario": "Durante la mañana", "dir": "Zona 10", "mensaje": "Feliz cumpleaños", "notas": "", "items": items}
        base.update(extra)
        return base

    def mensajes(self, orden):
        """Correos enviados al cliente: cada envío deja una nota «Correo «plantilla» enviado a ...» en el chatter."""
        return self.env["mail.message"].search([("model", "=", "sale.order"), ("res_id", "=", orden.id), ("body", "ilike", "Correo «")])

    def test_productos_oficiales(self):
        precios = {t.gt_web_id: t.list_price for t in self.env["product.template"].search([("gt_web_id", "!=", False)])}
        self.assertEqual(precios["single"], 150)
        self.assertEqual(precios["cozy"], 260)
        self.assertEqual(precios["homestyle"], 500)
        self.assertEqual(precios["gathering"], 800)
        self.assertEqual(precios["grazing-table"], 90)
        self.assertEqual(len(precios), len(catalogo.PRODUCTOS))

    def test_pedido_fijo_se_envia_solo(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 2}, {"id": "little-box", "qty": 5}]))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["estado"], "enviada")
        self.assertEqual(r["total"], 2 * 150 + 5 * 65)
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertEqual(orden.state, "sent")
        self.assertTrue(orden.gt_web)
        self.assertEqual(orden.partner_id.email, "ana@example.com")
        self.assertEqual(orden.validity_date, fields.Date.today() + timedelta(days=7))
        self.assertEqual(len(self.mensajes(orden)), 1)
        # pequeño contribuyente: el precio de Odoo es el total, sin impuesto aparte
        self.assertEqual(orden.amount_total, 625)
        self.assertEqual(orden.amount_tax, 0)

    def test_lead_creado(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "cozy", "qty": 1}]))
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertTrue(self.env["crm.lead"].search([("name", "ilike", orden.name)]))

    def test_producto_a_la_medida_queda_en_revision(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "tailored", "qty": 1}]))
        self.assertTrue(r["ok"])
        self.assertEqual(r["estado"], "revision")
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertEqual(orden.state, "draft")
        self.assertIn("The Tailored", orden.gt_revision)
        self.assertTrue(orden.activity_ids)
        # el cliente solo recibe el acuse, no la cotización
        self.assertEqual(len(self.mensajes(orden)), 1)
        self.assertIn("Pedido recibido", self.mensajes(orden).body)

    def test_acuse_dice_que_productos_requieren_revision(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "glass-dome", "qty": 10}, {"id": "the-break", "qty": 1}]))
        self.assertEqual(r["estado"], "revision")
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        cuerpo = self.env.ref("gatherings_cotizacion.mail_template_recibida")._render_field("body_html", orden.ids)[orden.id]
        self.assertIn("The Break", cuerpo)
        self.assertNotIn("The Glass Dome", cuerpo)
        # sin productos a la medida (p. ej. mínimo no cumplido) el acuse no inventa un motivo
        r2 = self.Order.gt_web_quote(self.pedido([{"id": "mini-dome", "qty": 3}]))
        orden2 = self.Order.search([("name", "=", r2["cotizacion"])])
        cuerpo2 = self.env.ref("gatherings_cotizacion.mail_template_recibida")._render_field("body_html", orden2.ids)[orden2.id]
        self.assertNotIn("se cotiza a la medida", cuerpo2)

    def test_menos_del_minimo_queda_en_revision(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "mini-dome", "qty": 3}]))
        self.assertEqual(r["estado"], "revision")
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertIn("mínimo de 10", orden.gt_revision)

    def test_grazing_y_experience_pasan_por_revision(self):
        for web_id, qty in (("grazing-table", 30), ("experience", 5)):
            r = self.Order.gt_web_quote(self.pedido([{"id": web_id, "qty": qty}]))
            self.assertEqual(r["estado"], "revision", web_id)

    def test_cliente_existente_se_reutiliza(self):
        self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}]))
        self.Order.gt_web_quote(self.pedido([{"id": "cozy", "qty": 1}], nombre="Ana P.", correo="ANA@example.com"))
        self.assertEqual(self.env["res.partner"].search_count([("email_normalized", "=", "ana@example.com")]), 1)

    def test_el_sitio_no_puede_poner_precios(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1, "price": 1}]))
        self.assertEqual(r["total"], 150)

    def test_cantidades_repetidas_se_suman(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}, {"id": "single", "qty": 2}]))
        self.assertEqual(r["total"], 450)

    def test_validaciones(self):
        malos = [
            self.pedido([]),
            self.pedido([{"id": "single", "qty": 0}]),
            self.pedido([{"id": "single", "qty": "x"}]),
            self.pedido([{"id": "no-existe", "qty": 1}]),
            self.pedido([{"id": "single", "qty": 1}], correo="no-es-correo"),
            self.pedido([{"id": "single", "qty": 1}], nombre=""),
            self.pedido([{"id": "single", "qty": 1}], telefono="12"),
            self.pedido([{"id": "single", "qty": 1}], fecha="2020-01-01"),
            self.pedido([{"id": "single", "qty": 1}], fecha="ayer"),
            "texto",
        ]
        antes = self.Order.search_count([])
        for p in malos:
            r = self.Order.gt_web_quote(p)
            self.assertFalse(r["ok"], p)
            self.assertTrue(r["error"])
        self.assertEqual(self.Order.search_count([]), antes)

    def test_html_del_cliente_se_escapa(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}], mensaje="<script>alert(1)</script>"))
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        cuerpos = " ".join(orden.message_ids.mapped("body"))
        self.assertNotIn("<script>", cuerpos)

    def test_pdf_html(self):
        r = self.Order.gt_web_quote(self.pedido([{"id": "cozy", "qty": 2}]))
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        html = self.env["ir.actions.report"]._render_qweb_html("gatherings_cotizacion.report_cotizacion", orden.ids)[0].decode()
        self.assertIn(orden.name, html)
        self.assertIn("Total", html)
        self.assertNotIn("IVA incluido", html)
        self.assertNotIn("incluyen IVA", html)
        self.assertIn("The Cozy", html)

    def test_texto_de_pago_editable(self):
        self.env.company.gt_pago_texto = "Anticipo del 50 %\nDepósito Banco X, cuenta 123"
        r = self.Order.gt_web_quote(self.pedido([{"id": "cozy", "qty": 1}]))
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        html = self.env["ir.actions.report"]._render_qweb_html("gatherings_cotizacion.report_cotizacion", orden.ids)[0].decode()
        self.assertIn("Anticipo del 50 %", html)
        self.assertIn("Depósito Banco X", html)
        cuerpo = self.env.ref("gatherings_cotizacion.mail_template_cotizacion")._render_field("body_html", orden.ids)[orden.id]
        self.assertIn("Depósito Banco X", cuerpo)

    def test_limite_por_correo(self):
        for _ in range(5):
            self.assertTrue(self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}]))["ok"])
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}]))
        self.assertFalse(r["ok"])
        self.assertIn("WhatsApp", r["error"])

    def test_saturacion_global_no_envia_correos(self):
        for i in range(30):
            self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}], correo=f"cliente{i}@example.com"))
        r = self.Order.gt_web_quote(self.pedido([{"id": "single", "qty": 1}], correo="otro@example.com"))
        self.assertEqual(r["estado"], "revision")
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertIn("Muchas solicitudes", orden.gt_revision)
        self.assertFalse(self.mensajes(orden))

    def test_con_el_usuario_tecnico_de_permisos_minimos(self):
        """El sitio entra con un usuario sin correo y con solo Ventas + contactos (scripts/setup_cotizaciones_shell.py)."""
        grupos = [self.env.ref("sales_team.group_sale_salesman_all_leads").id, self.env.ref("base.group_partner_manager").id]
        usuario = self.env["res.users"].with_context(no_reset_password=True).create(
            {"name": "Web Cotizaciones", "login": "web-test", "groups_id": [(6, 0, grupos)]})
        r = self.Order.with_user(usuario).gt_web_quote(self.pedido([{"id": "cozy", "qty": 1}], correo="tecnico@example.com"))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["estado"], "enviada")

    def _usuario_tecnico(self):
        grupos = [self.env.ref("sales_team.group_sale_salesman_all_leads").id, self.env.ref("base.group_partner_manager").id]
        return self.env["res.users"].with_context(no_reset_password=True).create(
            {"name": "Web Cotizaciones 2", "login": "web-test-2", "groups_id": [(6, 0, grupos)]})

    def test_revision_con_el_usuario_tecnico_sin_correo(self):
        """Un pedido a la medida llega a «revisión» aunque el usuario técnico no tenga correo (la actividad le avisa a otro usuario)."""
        r = self.Order.with_user(self._usuario_tecnico()).gt_web_quote(self.pedido([{"id": "tailored", "qty": 1}], correo="rev@example.com"))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["estado"], "revision")

    def test_falla_del_correo_deja_borrador_aunque_falten_remitentes(self):
        """Sin correo en la compañía no se puede enviar: la cotización queda en borrador y la API responde ok."""
        self.env.company.email = False
        r = self.Order.with_user(self._usuario_tecnico()).gt_web_quote(self.pedido([{"id": "single", "qty": 1}], correo="sin@example.com"))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["estado"], "revision")
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertEqual(orden.state, "draft")
        self.assertIn("No se pudo enviar", orden.gt_revision)

    def test_usuario_tecnico_no_queda_de_seguidor(self):
        """Sin correo propio, como seguidor haría fallar cada mensaje del chatter con «Invalid email address»."""
        usuario = self._usuario_tecnico()
        r = self.Order.with_user(usuario).gt_web_quote(self.pedido([{"id": "cozy", "qty": 1}], correo="seg@example.com"))
        orden = self.Order.search([("name", "=", r["cotizacion"])])
        self.assertNotIn(usuario.partner_id, orden.message_partner_ids)
        lead = self.env["crm.lead"].search([("name", "ilike", orden.name)])
        self.assertNotIn(usuario.partner_id, lead.message_partner_ids)
        self.assertNotIn(usuario.partner_id, orden.partner_id.message_partner_ids)
