import importlib.util
import pathlib

# Se carga por ruta: el módulo no depende de Odoo, así que se prueba sin instalarlo.
_spec = importlib.util.spec_from_file_location(
    "wa_utils", pathlib.Path(__file__).resolve().parent.parent / "addons" / "gatherings_whatsapp" / "wa_utils.py"
)
wa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wa)


def test_normalize_local_number():
    assert wa.normalize_phone("5541-2293") == "50255412293"
    assert wa.normalize_phone("55412293") == "50255412293"


def test_normalize_international_forms():
    assert wa.normalize_phone("+502 5541 2293") == "50255412293"
    assert wa.normalize_phone("00502 55412293") == "50255412293"
    assert wa.normalize_phone("+1 (305) 555-0100") == "13055550100"


def test_normalize_does_not_double_country_code():
    assert wa.normalize_phone("502 5541-2293") == "50255412293"


def test_normalize_other_default_country():
    assert wa.normalize_phone("5541-2293", country_code="+503") == "50355412293"


def test_normalize_rejects_garbage():
    for bad in (None, "", "   ", "abc", "123", "+" + "9" * 20):
        assert wa.normalize_phone(bad) == ""


def test_build_url_encodes_text():
    url = wa.build_url("50255412293", "Hola Ana & María: pedido #12 (Q150)")
    assert url == "https://wa.me/50255412293?text=Hola%20Ana%20%26%20Mar%C3%ADa%3A%20pedido%20%2312%20%28Q150%29"


def test_build_url_without_phone_or_text():
    assert wa.build_url("", "x") == ""
    assert wa.build_url("50255412293") == "https://wa.me/50255412293"


def test_render_fills_known_and_keeps_unknown():
    out = wa.render("Hola {nombre}, tu pedido {pedido} {otro}", {"nombre": "Ana", "pedido": "GT-0001"})
    assert out == "Hola Ana, tu pedido GT-0001 {otro}"


def test_render_is_not_a_format_string():
    # Sin acceso a atributos ni formato: solo {palabra}.
    assert wa.render("{nombre.__class__} {0} {{x}}", {"nombre": "Ana"}) == "{nombre.__class__} {0} {{x}}"
    assert wa.render("", {"a": 1}) == ""
