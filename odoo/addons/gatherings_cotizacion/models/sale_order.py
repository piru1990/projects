import logging
import re
from datetime import date, datetime, timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models, tools

from .. import catalogo

_logger = logging.getLogger(__name__)

MAX_LINEAS = 20
MAX_CANTIDAD = 999
MAX_TEXTO = 1000


class SaleOrder(models.Model):
    _inherit = "sale.order"

    gt_web = fields.Boolean("Cotización del sitio web", readonly=True, copy=False)
    gt_revision = fields.Text("Motivo de revisión", readonly=True, copy=False)
    gt_fecha_entrega = fields.Date("Fecha del evento o entrega", copy=False)
    gt_horario = fields.Char("Horario de entrega", copy=False)
    gt_direccion = fields.Text("Zona y dirección", copy=False)

    # ---- validación -----------------------------------------------------------------------------------------------

    @api.model
    def _gt_limpiar(self, payload):
        """Valida lo que manda el sitio. Devuelve (datos, None) o (None, mensaje para el cliente). Nunca confía en precios."""
        if not isinstance(payload, dict):
            return None, "Solicitud inválida."
        texto = lambda k, n=MAX_TEXTO: str(payload.get(k) or "").strip()[:n]  # noqa: E731
        nombre, correo, telefono = texto("nombre", 120), texto("correo", 254).lower(), texto("telefono", 40)
        if len(nombre) < 2:
            return None, "Escribe tu nombre y apellido."
        if not tools.email_normalize(correo) or " " in correo:
            return None, "Escribe un correo válido para enviarte la cotización."
        digitos = re.sub(r"\D", "", telefono)
        if telefono and not 7 <= len(digitos) <= 15:
            return None, "Revisa tu número de teléfono."
        fecha = None
        if texto("fecha"):
            try:
                fecha = date.fromisoformat(texto("fecha", 10))
            except ValueError:
                return None, "Revisa la fecha del evento o entrega."
            if fecha < fields.Date.context_today(self):
                return None, "La fecha del evento o entrega ya pasó."
        horario = texto("horario", 40)
        if horario and horario not in catalogo.HORARIOS:
            horario = ""
        items = payload.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_LINEAS:
            return None, "Agrega al menos un producto a tu pedido."
        cantidades = {}
        for it in items:
            try:
                web_id, qty = str(it["id"]), int(it["qty"])
            except (TypeError, ValueError, KeyError):
                return None, "Revisa los productos de tu pedido."
            if not 1 <= qty <= MAX_CANTIDAD:
                return None, "Revisa las cantidades de tu pedido."
            cantidades[web_id] = min(MAX_CANTIDAD, cantidades.get(web_id, 0) + qty)
        productos = self.env["product.template"].search([("gt_web_id", "in", list(cantidades)), ("sale_ok", "=", True)])
        por_id = {p.gt_web_id: p for p in productos}
        if len(por_id) != len(cantidades):
            return None, "Uno de los productos ya no está disponible. Actualiza la página e inténtalo de nuevo."
        return {
            "nombre": nombre, "correo": correo, "telefono": telefono, "fecha": fecha, "horario": horario,
            "direccion": texto("dir"), "mensaje": texto("mensaje"), "notas": texto("notas"),
            "lineas": [(por_id[i], q) for i, q in cantidades.items()],
        }, None

    @api.model
    def _gt_motivos_revision(self, lineas):
        motivos = []
        for prod, qty in lineas:
            unidad = prod.gt_unit_label and f"{prod.gt_unit_label}s" or "unidades"
            if prod.gt_quote_mode == "review":
                motivos.append(f"«{prod.name}» se cotiza a la medida o con precio por confirmar.")
            if qty < (prod.gt_min_qty or 1):
                motivos.append(f"«{prod.name}»: {qty} {unidad}, menos del mínimo de {prod.gt_min_qty}.")
        return motivos

    # ---- punto de entrada para el sitio ----------------------------------------------------------------------------

    @api.model
    def gt_web_quote(self, payload):
        """Crea la cotización de un pedido del sitio. Lo llama la función de Cloudflare por JSON-RPC.

        Devuelve {"ok": True, "cotizacion", "estado": "enviada"|"revision", "total"} o {"ok": False, "error"} si el pedido
        es inválido (el mensaje es apto para mostrarlo al cliente)."""
        datos, error = self._gt_limpiar(payload)
        if error:
            return {"ok": False, "error": error}

        ahora = datetime.now()
        previas = self.search_count([("gt_web", "=", True), ("create_date", ">=", ahora - timedelta(days=1)),
                                     ("partner_id.email_normalized", "=", tools.email_normalize(datos["correo"]))])
        if previas >= catalogo.LIMITE_POR_CORREO_DIA:
            return {"ok": False, "error": "Ya recibimos varias solicitudes con este correo hoy. Escríbenos por WhatsApp y te atendemos."}
        saturado = self.search_count([("gt_web", "=", True), ("create_date", ">=", ahora - timedelta(hours=1))]) >= catalogo.LIMITE_GLOBAL_HORA

        partner = self._gt_cliente(datos)
        motivos = self._gt_motivos_revision(datos["lineas"])
        if saturado:
            motivos.append("Muchas solicitudes seguidas del sitio web: no se envió nada al cliente, revisa que sea legítima.")
        lineas = [(0, 0, {"product_id": prod.product_variant_id.id, "product_uom_qty": qty}) for prod, qty in datos["lineas"]]
        lineas.append((0, 0, {"display_type": "line_note", "name": catalogo.ENVIO_NOTA}))
        # mail_create_nosubscribe: el usuario técnico del sitio no tiene correo; como seguidor, cada mensaje del chatter
        # le intentaría enviar un correo y fallaría («Invalid email address»).
        orden = self.with_context(mail_create_nosubscribe=True).create({
            "partner_id": partner.id,
            "origin": "Sitio web",
            "validity_date": fields.Date.context_today(self) + timedelta(days=catalogo.VALIDEZ_DIAS),
            "gt_web": True,
            "gt_fecha_entrega": datos["fecha"],
            "gt_horario": datos["horario"],
            "gt_direccion": datos["direccion"],
            "order_line": lineas,
        })
        orden._gt_nota(self._gt_detalle_html(datos))
        self._gt_lead(orden, datos)

        estado = "revision"
        if saturado:
            pass   # sin correos automáticos hasta que una persona la revise
        elif not motivos:
            try:
                with self.env.cr.savepoint():
                    orden._gt_enviar("gatherings_cotizacion.mail_template_cotizacion", con_copia=True)
                orden.state = "sent"
                estado = "enviada"
            except Exception:  # el pedido no se pierde: queda en borrador para que Andrea lo envíe
                _logger.exception("No se pudo enviar la cotización %s", orden.name)
                motivos.append("No se pudo enviar el correo automático: envíala desde Odoo.")
        else:
            try:
                with self.env.cr.savepoint():
                    orden._gt_enviar("gatherings_cotizacion.mail_template_recibida")
            except Exception:
                _logger.exception("No se pudo enviar el acuse de la cotización %s", orden.name)
        if estado == "revision":
            orden.gt_revision = "\n".join(motivos)
            orden._gt_avisar_revision()
        return {"ok": True, "cotizacion": orden.name, "estado": estado, "total": orden.amount_total}

    # ---- piezas ---------------------------------------------------------------------------------------------------

    @api.model
    def _gt_cliente(self, datos):
        Partner = self.env["res.partner"]
        partner = Partner.search([("email_normalized", "=", tools.email_normalize(datos["correo"]))], limit=1)
        if partner:
            if datos["telefono"] and not partner.phone:
                partner.phone = datos["telefono"]
            return partner
        return Partner.with_context(mail_create_nosubscribe=True).create({
            "name": datos["nombre"], "email": datos["correo"], "phone": datos["telefono"] or False,
            "comment": "Creado desde el sitio web.",
        })

    @api.model
    def _gt_detalle_html(self, d):
        fila = lambda k, v: Markup("<li><b>{}:</b> {}</li>").format(k, v or "-")  # noqa: E731
        return Markup("<p><b>Pedido recibido desde el sitio web</b></p><ul>{}</ul>").format(Markup("").join([
            fila("Nombre", d["nombre"]), fila("Correo", d["correo"]), fila("Teléfono", d["telefono"]),
            fila("Fecha", d["fecha"] and d["fecha"].isoformat()), fila("Horario", d["horario"]),
            fila("Dirección", d["direccion"]), fila("Mensaje personalizado", d["mensaje"]), fila("Notas", d["notas"]),
        ]))

    @api.model
    def _gt_lead(self, orden, datos):
        if "crm.lead" not in self.env:
            return
        lead = self.env["crm.lead"].with_context(mail_create_nosubscribe=True).create({
            "name": f"Cotización web {orden.name}",
            "partner_id": orden.partner_id.id,
            "email_from": datos["correo"],
            "phone": datos["telefono"] or False,
            "description": f"Pedido del sitio web: {orden.name}. Mensaje: {datos['mensaje'] or '-'}. Notas: {datos['notas'] or '-'}.",
        })
        if "opportunity_id" in orden._fields:
            orden.opportunity_id = lead

    def _gt_nota(self, cuerpo):
        """Nota interna firmada por la compañía: el usuario técnico del sitio no tiene correo y Odoo exige uno para publicar."""
        self.ensure_one()
        company = self.company_id
        self.message_post(body=cuerpo, subtype_xmlid="mail.mt_note", author_id=company.partner_id.id,
                          email_from=company.email or "hola@gatheringsgt.com")

    def _gt_enviar(self, xmlid, con_copia=False):
        """Envía el correo de la plantilla al cliente (sin enlaces al portal: Odoo está detrás de Cloudflare Access)."""
        self.ensure_one()
        plantilla = self.env.ref(xmlid)
        valores = {"email_cc": self.company_id.email} if con_copia and self.company_id.email else {}
        plantilla.send_mail(self.id, force_send=True, raise_exception=True, email_values=valores)
        self._gt_nota(f"Correo «{plantilla.name}» enviado a {self.partner_id.email}.")

    def _gt_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        return f"{base}/odoo/action-sale.action_quotations_with_onboarding/{self.id}"

    def _gt_avisar_revision(self):
        """Actividad para el responsable y correo a la dirección de la compañía: la cotización espera revisión.
        Los avisos nunca deben tumbar la solicitud (la cotización ya existe): cada uno falla por separado y queda en el log."""
        self.ensure_one()
        usuario = self.env.ref("base.user_admin", raise_if_not_found=False)
        if usuario:
            try:
                with self.env.cr.savepoint():
                    # mail_activity_quick_update: sin el correo «te asignaron una actividad», que Odoo no puede firmar con el
                    # usuario técnico (no tiene correo); el aviso por correo va aparte, a la dirección de la compañía.
                    self.with_context(mail_activity_quick_update=True).activity_schedule(
                        "mail.mail_activity_data_todo", summary="Revisar y enviar cotización del sitio web",
                        note=escape(self.gt_revision or ""), user_id=usuario.id)
            except Exception:
                _logger.exception("No se pudo crear la actividad de revisión de %s", self.name)
        destino = self.company_id.email
        if destino:
            try:
                with self.env.cr.savepoint():
                    cuerpo = Markup("<p>Hay una cotización del sitio web por revisar: <b>{}</b> ({}).</p><p>{}</p><p><a href=\"{}\">Abrir en Odoo</a></p>").format(
                        self.name, self.partner_id.name, (self.gt_revision or "").replace("\n", " "), self._gt_url())
                    self.env["mail.mail"].sudo().create({
                        "subject": f"Cotización web por revisar: {self.name}", "body_html": cuerpo, "email_to": destino,
                        "email_from": destino, "auto_delete": True,
                    }).send(raise_exception=False)
            except Exception:
                _logger.exception("No se pudo avisar por correo de la revisión de %s", self.name)
