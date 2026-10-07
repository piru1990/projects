"""linkedin_triage: deterministic scoring of the list against perfil.md, without opening any job."""

import json
import shutil
from pathlib import Path

import pytest

import config
import server
import triage
from test_prepare_fill import env  # noqa: F401

REAL_RULES = config.triage_json()
REAL_PERFIL = Path.home() / ".claude" / "skills" / "llenar-formulario-postulacion" / "references" / "perfil.md"
needs_real = pytest.mark.skipif(not (REAL_RULES.exists() and REAL_PERFIL.exists()), reason="faltan triage.json o perfil.md")


@pytest.fixture(scope="module")
def real():
    data = json.loads(REAL_RULES.read_text(encoding="utf-8"))
    rules, skipped = triage.load_rules(data, REAL_PERFIL.read_text(encoding="utf-8"))
    return rules, skipped, data


def card(title, company="X", location="Guatemala", **flags):
    return {"job_id": str(4_400_000_000 + sum(map(ord, title + company))), "title": title, "company": company,
            "location": location, **flags}


def row(rules, title, company="X", desc=None, **flags):
    c = card(title, company, **flags)
    cache = {c["job_id"]: {"data": {"description": desc}}} if desc else {}
    return triage.triage([c], rules, cache)[0]


# --- the real rules against the real profile ---

@needs_real
def test_every_positive_criterion_quotes_what_allan_did(real):
    rules, skipped, data = real
    allowed = triage.evidence_text(REAL_PERFIL.read_text(encoding="utf-8"), data["evidence_sections"])
    for g in data["positive"]:
        assert g["evidence"] in allowed, g["id"]
    assert skipped == []


@needs_real
def test_quotes_from_the_integrity_rules_do_not_count(real):
    _, _, data = real
    bad = {**data, "positive": [{"id": "x", "label": "Telco", "weight": 3, "evidence": "telco", "terms": ["noc"]}]}
    rules, skipped = triage.load_rules(bad, REAL_PERFIL.read_text(encoding="utf-8"))
    assert rules["positive"] == [] and skipped == ["x"]


@needs_real
def test_real_titles(real):
    r = real[0]
    assert row(r, "IT Operations Manager", "IntouchCX")["puntaje"] == row(r, "Gerente de Operaciones de TI")["puntaje"]
    assert row(r, "Gerente de Tecnología")["encaje"] == "medio"
    assert row(r, "Jefe(a) de Proyectos de TI")["puntaje"] == row(r, "Jefe de Proyectos de TI")["puntaje"] >= 3
    assert row(r, "Coordinador/a de Proyectos")["puntaje"] >= 3
    assert row(r, "Encargado (a) IT", "People Evolution")["puntaje"] >= 3
    assert any("Telco" in f for f in row(r, "Technical Supervisor", "Millicom (Tigo)")["banderas"])
    assert any("eléctrica" in f for f in row(r, "Supervisor eléctrico", "PROLECSA")["banderas"])
    assert any("Banca" in f for f in row(r, "JEFE DE OMNICANALIDAD", "BAC")["banderas"])
    assert any("programador" in f for f in row(r, "Engineering Manager / Core Systems & Architecture")["banderas"])
    assert not row(r, "Business Developer")["banderas"]


@needs_real
def test_no_unsupported_experience_is_scored(real):
    r = real[0]
    for title in ("Community Manager - Redes Sociales", "Jefe de Seguridad SOC", "Microsoft Dynamics 365 Consultant",
                  "Customer Service Manager", "Lead Generation Specialist", "Supervisor de Monitoreo"):
        got = row(r, title)
        assert got["encaje"] == "bajo", (title, got["motivos"])
    assert any("ERP distinto" in f for f in row(r, "Microsoft Dynamics 365 Consultant")["banderas"])


@needs_real
def test_a_wordy_description_cannot_inflate_the_fit(real):
    r = real[0]
    desc = ("Buscamos capacidad analitica, ambiente agil y dinamico, relacion con proveedores, monitoreo de "
            "indicadores de ventas, SAP deseable, Power BI, scrum, ciberseguridad, gestion de proyectos.")
    got = row(r, "Supervisor de Operaciones", desc=desc)
    assert got["puntaje"] <= 1 + triage.DESC_CAP and got["encaje"] != "alto"
    assert got["basis"] == "descripcion" and not got["encaje_provisional"]


@needs_real
def test_common_words_in_a_description_do_not_cap_or_flag_wrongly(real):
    r = real[0]
    title = "Gerente de TI y Proyectos SAP"
    for desc in ("Trabajo presencial en nuestras instalaciones de zona 10.", "Debe tener claro el enfoque al cliente.",
                 "Pago por deposito en cuenta de banco.", "Ability to react quickly.", "Construccion de dashboards.",
                 "Team dynamics and net income."):
        got = row(r, title, desc=desc)
        assert got["encaje"] == "alto" and not got["banderas"], (desc, got["banderas"])
    flagged = row(r, title, desc="Experiencia en el sector bancario y cartera de creditos.")
    assert flagged["banderas"] and flagged["encaje"] == "alto"  # shown, but a description flag doesn't cap


# --- pure logic with inline rules ---

RULES = {"positive": [
    {"id": "gerencia_ti", "label": "TI", "weight": 3, "evidence": "Gerente", "terms": ["gerente de ti"]},
    {"id": "erp", "label": "ERP", "weight": 2, "evidence": "SAP", "terms": ["sap"], "desc_terms": ["sap"]},
    {"id": "liderazgo", "label": "Líder", "weight": 1, "evidence": "directos", "terms": ["gerente"]}],
    "flags": [{"id": "banca", "label": "Banca", "terms": ["banco"], "desc_terms": ["sector bancario"]}],
    "thresholds": {"alto": 5, "medio": 2}}


def test_cache_states_and_ordering():
    cards = [card("Gerente de TI y SAP", "A"), card("Gerente de TI y SAP", "B"), card("Gerente de TI", "C", applied=True),
             card("Gerente de TI y SAP", "Banco D")]
    cache = {cards[0]["job_id"]: {"data": {"apply_type": "closed"}},
             cards[1]["job_id"]: {"data": {"apply_type": "unknown", "chips": ["Híbrido"]}}}
    cards[1]["easy_apply"] = True
    rows = triage.triage(cards, RULES, cache)
    assert [x["company"] for x in rows] == ["B", "Banco D", "A", "C"]
    b = rows[0]
    assert b["tipo"] == "easy_apply" and b["tipo_segun"] == "tarjeta" and b["modalidad"] == "Híbrido"
    assert rows[1]["encaje"] == "medio" and rows[1]["banderas"]  # alto by score, capped by the company flag
    assert rows[2]["estado"] == "cerrada" and rows[3]["estado"] == "ya solicitada"


def test_leadership_is_implied_by_an_it_management_title():
    got = triage.score_job(card("Gerente de TI"), RULES)
    assert got["puntaje"] == 3 and [m.split(" (")[0] for m in got["motivos"]] == ["TI"]


def test_malformed_rules_are_skipped_not_fatal():
    data = {"positive": [{"id": "ok", "label": "OK", "weight": 1, "evidence": "Gerente", "terms": ["x"]},
                         {"id": "bad", "weight": "tres", "evidence": "Gerente"}, "nope"],
            "flags": [{"label": "sin id"}], "evidence_sections": ["Experiencia"]}
    rules, skipped = triage.load_rules(data, "## Experiencia\nGerente de TI\n")
    assert [g["id"] for g in rules["positive"]] == ["ok"] and len(skipped) == 3
    assert triage.load_rules(["no es objeto"], "")[1] == ["(triage.json no es un objeto)"]


def test_the_tool_uses_the_cache_and_opens_no_job(env, monkeypatch, tmp_path):
    if not REAL_PERFIL.exists():
        pytest.skip("falta perfil.md")
    shutil.copy(REAL_PERFIL, tmp_path / "perfil.md")
    monkeypatch.setenv("LINKEDIN_MCP_PERFIL", str(tmp_path / "perfil.md"))
    a, b = card("Líder de tecnología", "Sapiens Guatemala"), card("Supervisor eléctrico", "PROLECSA", easy_apply=True)
    server.jobs.put(a["job_id"], {"job_id": a["job_id"], "title": a["title"], "apply_type": "external",
                                  "description": "Gestión de SAP S/4HANA e integraciones con SAP."})
    monkeypatch.setattr(server, "_tab", lambda tab_id: ((370, 8), None))
    actions = []

    def js(win, idx, action, arg=None, select=False):
        actions.append(action)
        if action == "list_jobs":
            return {"count": 2, "jobs": [dict(a), dict(b)], "page": 1, "total_results": "2"}
        return {"url": "https://www.linkedin.com/jobs/search-results/", "headings": [], "alerts": []}

    monkeypatch.setattr(server, "_js", js)
    monkeypatch.setattr(server.sb, "navigate", lambda *x: (_ for _ in ()).throw(AssertionError("navigated")))
    out = server.linkedin_triage("370:8")
    first = out["jobs"][0]
    assert first["title"] == "Líder de tecnología" and first["basis"] == "descripcion" and first["tipo_segun"] == "vacante"
    assert set(actions) <= {"list_jobs", "page_state"} and env["guard"].counters()["job_views"] == 0
