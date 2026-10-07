import json
import subprocess
import sys
from pathlib import Path

import pytest

JS = (Path(__file__).resolve().parents[1] / "linkedin.js").read_text(encoding="utf-8")

# JXA (JavaScriptCore, no DOM) compiles linkedin.js the way Safari will, so a syntax error shows up
# here instead of as js_error on every tool call. The source goes through argv, not stdin, to keep
# its non-ASCII regex ranges intact.
_RUNNER = "function run(argv) { var f = eval('(' + argv[0] + ')'); return f(argv[1], JSON.parse(argv[2])); }"


def _run(action, arg=None):
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _RUNNER, JS, action, json.dumps(arg)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
def test_linkedin_js_compiles_and_rejects_unknown_actions():
    r = _run("nope")
    assert r["status"] == "js_error" and "unknown action nope" in r["message"]


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
@pytest.mark.parametrize("label,kind", [
    ("Enviar solicitud", "submit"), ("Enviar", "submit"), ("Submit application", "submit"), ("Submit", "submit"),
    ("Continuar", "continue"), ("Continue", "continue"), ("  continuar ", "continue"),
    ("Siguiente", "next"), ("Next", "next"), ("Revisar", "next"), ("Review", "next"),
    ("Listo", "done"), ("Done", "done"), ("Atrás", "back"), ("Volver", "back"), ("Editar", "other"),
    ("Descartar", "other"),
])
def test_button_kind_never_calls_a_submit_or_continue_next(label, kind):
    assert _run("button_kind", label)["kind"] == kind


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
@pytest.mark.parametrize("label", ["Enviar solicitud", "Submit application", "Continuar", "Siguiente", "Guardar", ""])
def test_modal_click_refuses_anything_but_done(label):
    # Refused before touching the page (JXA has no DOM, so reaching it would be a js_error).
    assert _run("modal_click", label) == {"status": "label_not_allowed", "label": label}


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
def test_review_text_drops_the_resume_list():
    resumes = [f"CV-{i:02d}.pdf" for i in range(60)]
    text = "\n".join(["Aplicar a empresa", "Contact info", "Email*", "Código del país*", "Phone*", "Resume",
                      "Selecciona o carga un currículum en formato DOC, DOCX o PDF con un tamaño inferior a 2 MB."]
                     + [x for name in resumes for x in ("PDF", name, "6/10/2026")]
                     + ["Cargar currículum", "Enviar solicitud"])
    fields = [{"label": "Email", "type": "select", "value": "rosales.allan@gmail.com"},
              {"label": "Código del país", "type": "select", "value": "Guatemala (+502)"},
              {"label": "Phone", "type": "text", "value": ""},
              {"label": "Currículum", "type": "resume", "value": "CV-07.pdf",
               "resumes": [{"index": i, "name": n, "date": "6/10/2026", "selected": i == 7} for i, n in enumerate(resumes)]}]
    out = _run("compact_review", {"text": text, "fields": fields})["text"]
    assert "Currículum: CV-07.pdf (6/10/2026) [lista de 60 CV omitida]" in out
    assert "CV-08.pdf" not in out and out.count(".pdf") == 1 and len(out) < 600
    assert "Email: rosales.allan@gmail.com" in out and "Phone: (vacío)" in out


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
def test_multistep_review_keeps_its_answers():
    text = "\n".join(["Aplicar a Empresa Confidencial", "4/4 páginas", "Revisa tu solicitud", "Resume", "Editar",
                      "PDF", "CV-Allan-Rosales-Tecnologia-ERP.pdf", "6/10/2026", "Additional Questions",
                      "Cual es su expectativa salarial mensual en USD$ ?", "3000", "Enviar solicitud"])
    out = _run("compact_review", {"text": text, "fields": []})["text"]
    assert "Currículum: CV-Allan-Rosales-Tecnologia-ERP.pdf (6/10/2026)" in out
    assert "expectativa salarial mensual en USD$ ?\n3000" in out and "Valores en el formulario" not in out


@pytest.mark.skipif(sys.platform != "darwin", reason="needs osascript (macOS)")
def test_review_text_keeps_cover_letters_and_answers_that_end_in_pdf():
    text = "\n".join(["Aplicar a X", "Currículum", "Editar", "PDF", "CV-Allan-Rosales-Tecnologia-ERP.pdf", "6/10/2026",
                      "Carta de presentación", "PDF", "Carta-EmpresaX.pdf", "6/10/2026",
                      "Enlace a tu portafolio", "https://example.com/portafolio.pdf", "Enviar solicitud"])
    out = _run("compact_review", {"text": text, "fields": []})["text"]
    assert "Currículum: CV-Allan-Rosales-Tecnologia-ERP.pdf (6/10/2026)" in out and "omitida" not in out
    assert "Carta-EmpresaX.pdf" in out and "https://example.com/portafolio.pdf" in out
