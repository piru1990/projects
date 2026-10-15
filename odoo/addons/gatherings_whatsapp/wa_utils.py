"""Lógica pura (sin Odoo) del módulo: teléfonos, enlaces wa.me y plantillas. Se prueba aparte."""
import re
from urllib.parse import quote

DEFAULT_COUNTRY_CODE = "502"  # Guatemala


def normalize_phone(raw, country_code=DEFAULT_COUNTRY_CODE):
    """Deja solo dígitos con código de país, como pide wa.me. Devuelve '' si no hay número usable.

    «5541-2293» -> «50255412293»; «+502 5541 2293» y «00502 55412293» -> «50255412293».
    Un número de 8 dígitos se toma como local y se le antepone el código de país; uno que ya
    empieza con «+» o «00» se respeta.
    """
    if not raw:
        return ""
    s = str(raw).strip()
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    international = s.startswith("+") or digits.startswith("00")
    if digits.startswith("00"):
        digits = digits[2:]
    if not international and len(digits) <= 8:
        digits = (re.sub(r"\D", "", country_code or "") or DEFAULT_COUNTRY_CODE) + digits
    # largo E.164 razonable (código + número)
    return digits if 8 <= len(digits) <= 15 else ""


def build_url(phone, text=""):
    """Enlace de WhatsApp (abre WhatsApp Web en escritorio o la app en el móvil)."""
    if not phone:
        return ""
    url = "https://wa.me/" + phone
    if text:
        url += "?text=" + quote(text, safe="")
    return url


def render(body, values):
    """Sustituye {campo} del texto por los valores. Un campo desconocido queda tal cual."""
    if not body:
        return ""
    return re.sub(
        r"\{(\w+)\}",
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
        body,
    )
