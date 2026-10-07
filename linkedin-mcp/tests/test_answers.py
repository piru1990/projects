import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import answers  # noqa: E402
import config  # noqa: E402

BANK_PATH = config.bank_json()
pytestmark = pytest.mark.skipif(not BANK_PATH.exists(), reason=f"no existe {BANK_PATH}")


@pytest.fixture(scope="module")
def bank():
    return answers.load(BANK_PATH)


def f(label, type_="text", value="", options=None, required=True):
    field = {"label": label, "type": type_, "value": value, "required": required}
    if options is not None:
        field["options"] = options
    return field


def test_real_bank_is_valid(bank):
    assert answers.validate(bank.data) == []
    statuses = {e["id"]: e["status"] for e in bank.entries}
    for always_ask in ("salario", "fecha_inicio", "presencial", "hibrido_remoto", "reubicacion",
                       "autorizacion_trabajo", "patrocinio_visa"):
        assert statuses[always_ask] == "preguntar"
    assert statuses["licencia_conducir"] == "aprobado"  # Allan, 06/10/2026 (Novex)
    for no_evidence in ("banca", "telco", "programador_principal", "aws_arquitecto", "diseno_electrico"):
        assert statuses[no_evidence] == "confirmar"


# --- labels from the two real applications (06/10/2026) ---

def test_itsm_label_takes_itsm_not_total_experience(bank):
    p = answers.propose(f("How many years of work experience do you have with IT Service Management?", "number"), bank)
    assert (p["decision"], p["value"], p["entry"]) == ("proposed", "5", "itsm")


def test_total_experience_only_without_a_subject(bank):
    assert answers.propose(f("How many years of work experience do you have?", "number"), bank)["value"] == "14"
    for label in ("How many years of work experience do you have with Salesforce?",
                  "¿Cuántos años de experiencia tienes en ventas?",
                  "Years of experience in retail"):
        p = answers.propose(f(label, "number"), bank)
        assert p["decision"] == "ask" and p["entry"] is None, label


def test_english_level_picks_the_approved_option(bank):
    p = answers.propose(f("What is your level of proficiency in English?", "radio", None,
                          ["None", "Conversational", "Professional", "Native or bilingual"]), bank)
    assert (p["decision"], p["value"]) == ("proposed", "Professional")
    p = answers.propose(f("Nivel de inglés", "select", "Selecciona una opción",
                          ["Selecciona una opción", "Básico", "Intermedio", "Avanzado", "Nativo"]), bank)
    assert (p["decision"], p["value"], p["current"]) == ("proposed", "Avanzado", "")


def test_prefilled_salary_is_always_asked_in_chat(bank):
    p = answers.propose(f("Cual es su expectativa salarial mensual en USD$ ?", value="3000"), bank)
    assert (p["decision"], p["entry"], p["current"], p["ask_via"]) == ("ask", "salario", "3000", "chat")
    p = answers.propose(f("Expected salary", value="3000", required=False), bank)
    assert p["decision"] == "ask"


def test_contact_prefills_are_ok_only_when_equal(bank):
    ok = answers.propose(f("Email address", "select", "rosales.allan@gmail.com",
                           ["Selecciona una opción", "rosales.allan@gmail.com"]), bank)
    assert ok["decision"] == "prefilled_ok"
    assert answers.propose(f("Mobile phone number", value="57030067"), bank)["decision"] == "prefilled_ok"
    assert answers.propose(f("Código del país", "select", "Guatemala (+502)",
                             ["Selecciona una opción", "Guatemala (+502)", "México (+52)"]), bank)["decision"] == "prefilled_ok"
    wrong = answers.propose(f("Mobile phone number", value="55555555"), bank)
    assert (wrong["decision"], wrong["value"], wrong["replaces"]) == ("proposed", "57030067", "55555555")


# --- matching rules ---

def test_contact_patterns_are_exact(bank):
    p = answers.propose(f("Ciudad a la que estarías dispuesto a reubicarte"), bank)
    assert (p["decision"], p["entry"]) == ("ask", "reubicacion")


def test_nested_term_belongs_to_the_longer_entry(bank):
    p = answers.propose(f("¿Cuántos años de experiencia tienes con Jira Service Management?", "number"), bank)
    assert (p["decision"], p["entry"], p["suggested"]) == ("confirm", "jira", "4")


def test_two_entries_means_ask(bank):
    p = answers.propose(f("How many years of experience do you have with ERP systems such as SAP?", "number"), bank)
    assert p["decision"] == "ask" and "varias entradas" in p["reason"]


def test_degree_with_another_field_is_asked(bank):
    yn = ["Yes", "No"]
    assert answers.propose(f("Bachelor's degree in Computer Science?", "radio", None, yn), bank)["decision"] == "ask"
    ok = answers.propose(f("Have you completed the following level of education: Bachelor's Degree?", "radio", None, yn), bank)
    assert (ok["decision"], ok["value"]) == ("proposed", "Yes")
    es = answers.propose(f("¿Tienes licenciatura en Ingeniería Industrial o afín?", "radio", None, ["Sí", "No"]), bank)
    assert (es["decision"], es["value"]) == ("proposed", "Sí")


def test_yes_no_from_years_uses_the_threshold(bank):
    yn = ["Yes", "No"]
    assert answers.propose(f("Do you have at least 5 years of experience with IT Service Management?", "radio", None, yn),
                           bank)["value"] == "Yes"
    assert answers.propose(f("Do you have more than 5 years of experience with IT Service Management?", "radio", None, yn),
                           bank)["value"] == "No"
    p = answers.propose(f("Do you have 3+ years of experience in banking?", "radio", None, yn), bank)
    assert (p["decision"], p["suggested"]) == ("confirm", "No")


def test_no_evidence_is_confirmed_never_filled(bank):
    for label in ("How many years of experience do you have in banking?",
                  "¿Cuántos años de experiencia tienes en un NOC de telecomunicaciones?",
                  "Years of experience with AWS"):
        p = answers.propose(f(label, "number"), bank)
        assert (p["decision"], p["suggested"], p["ask_via"]) == ("confirm", "0", "chat"), label


def test_options_need_one_exact_match(bank):
    p = answers.propose(f("¿Título universitario?", "select", "", ["Sí, en curso", "Sí, completo", "No"]), bank)
    assert p["decision"] == "ask"
    ranges = ["0-2 años", "3-5 años", "6-10 años", "Más de 10 años"]
    assert answers.propose(f("How many years of work experience do you have?", "select", "", ranges), bank)["value"] == "Más de 10 años"
    overlap = answers.propose(f("How many years of work experience do you have?", "select", "", ["1-14", "14-20"]), bank)
    assert overlap["decision"] == "ask"


def test_unknown_fields(bank):
    assert answers.propose(f("Portfolio URL", required=False), bank)["decision"] == "leave_empty"
    assert answers.propose(f("Portfolio URL", value="https://x"), bank)["decision"] == "ask"
    assert answers.propose(f("Headline"), bank)["decision"] == "ask"
    assert answers.propose({"label": "Currículum", "type": "resume", "value": "a.pdf"}, bank)["decision"] == "resume"


def test_typeahead_and_checkbox_groups_are_not_guessed(bank):
    p = answers.propose(f("City", "typeahead", ""), bank)
    assert p["decision"] == "ask" and p["suggested"] == "Guatemala"
    assert answers.propose(f("City", "typeahead", "Guatemala"), bank)["decision"] == "prefilled_ok"
    grp = answers.propose(f("¿Tienes experiencia en banca?", "checkbox", [], ["Créditos", "Tarjetas"]), bank)
    assert grp["decision"] == "confirm" and grp["suggested"] is None


def test_ask_via(bank):
    four = answers.propose(f("¿Disponibilidad para trabajo presencial?", "select", "",
                             ["Selecciona una opción", "Sí", "No", "Parcial", "Depende"]), bank)
    assert four["ask_via"] == "choice"
    five = answers.propose(f("¿Disponibilidad para trabajo presencial?", "select", "", ["a", "b", "c", "d", "e"]), bank)
    assert five["ask_via"] == "chat"
    one = answers.propose(f("Acepto los términos", "checkbox", [], ["Acepto"]), bank)
    assert one["ask_via"] == "chat"
    multi = answers.propose(f("Herramientas que dominas", "checkbox", [], ["Jira", "Odoo", "SAP"]), bank)
    assert multi["ask_via"] == "choice_multi"


def test_parse_range():
    assert answers.parse_range("Menos de 1 año")[:2] == (0, 1)
    assert answers.parse_range("1 - 3 years")[:2] == (1, 3)
    assert answers.parse_range("10+ años")[:2] == (10, float("inf"))
    assert answers.parse_range("Más de 10 años")[:3] == (10, float("inf"), False)
    assert answers.parse_range("5") == (5, 5, True, True)
    assert answers.parse_range("Profesional") is None


# --- markdown and saving ---

def test_render_md_lists_every_entry(bank):
    md = answers.render_md(bank.data)
    assert "Generado desde `respuestas.json`" in md and "nunca por la opción \"Other\"" in md
    for e in bank.entries:
        assert e["question"] in md, e["id"]
    assert "| 06/10/2026 | How many years of work experience do you have with IT Service Management? | 5 |" in md


def test_save_rejects_always_ask_and_verified(bank):
    for item in ({"question": "Salario", "patterns": {"es": ["pretension salarial"]}, "answer": {"text": "Q20,000"}},
                 {"question": "Inicio", "patterns": {"en": ["start date"]}, "answer": {"text": "inmediata"}},
                 {"id": "salario", "answer": {"text": "3000"}},
                 {"id": "experiencia_total", "answer": {"number": 20}}):
        new, _, errors = answers.save_entries(bank.data, [item], "2026-10-07")
        assert errors, item
    assert bank.get("salario")["status"] == "preguntar"  # the original is untouched


def test_save_approves_and_adds(bank):
    new, diff, errors = answers.save_entries(bank.data, [
        {"id": "jira", "answer": {"number": 4}},
        {"question": "Años con Salesforce", "patterns": {"es": ["salesforce"], "en": ["salesforce"]},
         "applies": "years", "answer": {"number": 2}},
    ], "2026-10-07")
    assert errors == []
    nb = answers.Bank(new)
    assert (nb.get("jira")["status"], nb.get("jira")["approved_on"]) == ("aprobado", "2026-10-07")
    p = answers.propose(f("How many years of work experience do you have with Salesforce?", "number"), nb)
    assert (p["decision"], p["value"]) == ("proposed", "2")
    assert '"status": "aprobado"' in diff and new["approvals"][-1]["entry"] == "anos_con_salesforce"
    assert bank.get("jira")["status"] == "confirmar"


def test_proposals_carry_their_basis(bank):
    p = answers.propose(f("¿Cuántos años de experiencia tienes con Jira Service Management?", "number"), bank)
    assert p["decision"] == "confirm" and p["basis"] == "cbc dic. 2021 – oct. 2025"
    assert answers.propose(f("Portfolio URL", required=False), bank)["basis"] is None


def test_dumps_round_trips_and_stays_compact(bank):
    import json
    text = answers.dumps(bank.data)
    assert json.loads(text) == bank.data
    assert text.count("\n") < 20 * len(bank.entries)


@pytest.mark.skipif(not config.bank_md().exists(), reason="no existe respuestas-linkedin.md")
def test_the_markdown_view_is_up_to_date(bank):
    """respuestas-linkedin.md is generated: after changing respuestas.json run `cli.py bank-md`."""
    assert config.bank_md().read_text(encoding="utf-8") == answers.render_md(bank.data)
