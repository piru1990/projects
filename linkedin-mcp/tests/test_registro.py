"""The application record: enriched jsonl entries and insert-only, idempotent rows in both Markdown logs."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import config
import registro
import server
from test_prepare_fill import CV, ITSM as ITSM_LABEL, JOB, SALARY, STANDARD, FakeForm, env, key_of  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
REAL_POSTULACIONES = Path.home() / "Documents" / "CV" / "Postulaciones-LinkedIn.md"
REAL_PERFIL = Path.home() / ".claude" / "skills" / "llenar-formulario-postulacion" / "references" / "perfil.md"
REAL_LOG = Path.home() / ".cache" / "linkedin-mcp" / "applications.jsonl"


def test_tests_never_point_at_the_real_logs():
    assert config.postulaciones_md() != REAL_POSTULACIONES and config.perfil_md() != REAL_PERFIL
    assert "linkedin-mcp-tests-" in str(config.postulaciones_md())


@pytest.fixture
def copies(tmp_path):
    """Copies of the real Markdown logs (skipped if this machine doesn't have them)."""
    if not (REAL_POSTULACIONES.exists() and REAL_PERFIL.exists()):
        pytest.skip("no están los registros reales para copiar")
    p, q = tmp_path / "Postulaciones-LinkedIn.md", tmp_path / "perfil.md"
    shutil.copy(REAL_POSTULACIONES, p)
    shutil.copy(REAL_PERFIL, q)
    return p, q


ENTRY = {"ts": "2026-10-07T09:15:00", "job_id": "4474644406", "title": "Tech Lead", "company": "TPP eMarketing",
         "url": "https://www.linkedin.com/jobs/view/4474644406/", "confirmed": True, "follow_company": False,
         "answers": {"¿Tienes disponibilidad para trabajar de manera presencial?": "Yes",
                     "¿Cuál es tu pretensión salarial?": "Q25,000 | negociable"},
         "resume": {"name": CV, "date": "6/10/2026", "sha256": "37b42fc0" + "0" * 49 + "413b64b",
                    "sha256_source": "registro de CV subidos"}}


def test_the_real_logs_already_have_every_logged_job(copies):
    if not REAL_LOG.exists():
        pytest.skip("no está applications.jsonl")
    rows = [json.loads(line) for line in REAL_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    before = [c.read_text(encoding="utf-8") for c in copies]
    r = registro.sync(rows, *copies)
    assert r["added"] == {"Postulaciones-LinkedIn.md": [], "perfil.md": []} and r["diff"] == ""
    assert [c.read_text(encoding="utf-8") for c in copies] == before


def test_a_new_job_is_added_once_at_the_end_of_each_table(copies):
    p, q = copies
    first = registro.sync([ENTRY], p, q)
    assert first["added"] == {"Postulaciones-LinkedIn.md": ["4474644406"], "perfil.md": ["4474644406"]}
    again = registro.sync([ENTRY], p, q)
    assert again["added"] == {"Postulaciones-LinkedIn.md": [], "perfil.md": []}
    lines = q.read_text(encoding="utf-8").splitlines()
    i = next(n for n, line in enumerate(lines) if "(LinkedIn 4474644406)" in line)
    assert lines[i - 1].startswith("|") and (i + 1 == len(lines) or not lines[i + 1].startswith("|"))
    row = next(line for line in p.read_text(encoding="utf-8").splitlines() if "4474644406" in line)
    assert row.count(" | ") == 7 and "Q25,000 / negociable" in row  # a | inside an answer can't break the table
    assert "`37b42fc0…413b64b`" in row and "No sigue a la empresa" in row


def test_the_job_id_is_found_anywhere_in_a_row(tmp_path):
    p = tmp_path / "p.md"
    p.write_text(f"{registro.POSTULACIONES_HEADER}\n|---|\n| 2026-10-07 09:15 | y | z | otra | ver 4474644406 | | | |\n",
                 encoding="utf-8")
    q = tmp_path / "q.md"
    q.write_text(f"{registro.PERFIL_HEADER}\n|---|---|---|\n| TPP (LinkedIn 4474644406) | Enviada | 07/10/2026 09:15 |\n",
                 encoding="utf-8")
    assert registro.sync([ENTRY], p, q)["added"] == {"p.md": [], "q.md": []}


def test_dry_run_writes_nothing(copies):
    before = [c.read_text(encoding="utf-8") for c in copies]
    r = registro.sync([ENTRY], *copies, dry_run=True)
    assert "+| 2026-10-07 09:15 | TPP eMarketing" in r["diff"]
    assert [c.read_text(encoding="utf-8") for c in copies] == before


@pytest.mark.parametrize("extra,word", [
    ({"confirmed": False}, "sin confirmar"),
    ({"unexpected": True, "confirmed": True}, "sin el \"sí\" de Allan"),
    ({"manual": True, "via": "ats_continue"}, "Enviada por Allan a mano"),
])
def test_status_words(extra, word):
    e = {**ENTRY, **extra}
    assert word in registro.postulaciones_row(e) or word.replace("\"", "") in registro.perfil_row(e)


def test_answers_by_label_skips_the_cv_and_keeps_repeats():
    filled = {"1|email|0": {"label": "Email", "type": "select", "value": "a@b.c"},
              "2|curriculum|0": {"label": "Currículum", "type": "resume", "value": {"name": CV}},
              "3|comentarios|0": {"label": "Comentarios", "type": "text", "value": "uno"},
              "3|comentarios|1": {"label": "Comentarios", "type": "text", "value": "dos"}}
    assert registro.answers_by_label(filled) == {"Email": "a@b.c", "Comentarios": "uno", "Comentarios (2)": "dos"}


def _logs():
    return [Path(config.postulaciones_md()).read_text(encoding="utf-8"),
            Path(config.perfil_md()).read_text(encoding="utf-8")]


def test_a_submit_logs_answers_cv_and_rows(env):
    form = env["use"](FakeForm(STANDARD))
    form.allow_submit = True
    r = server.linkedin_apply_prepare(JOB)
    server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    sent = server.linkedin_apply_submit(JOB, confirm=True)
    assert sent["confirmed"] and sent["registro"] == {"Postulaciones-LinkedIn.md": [JOB], "perfil.md": [JOB]}
    e = env["guard"].applications()[0]
    assert e["answers"][SALARY] == "3000" and e["answers"]["Mobile phone number"] == "57030067"
    assert e["resume"]["name"] == CV and e["resume"]["sha256_source"] == "registro de CV subidos"
    assert e["apply_type"] == "easy_apply" and "Currículum: " in e["review_text"]
    postulaciones, perfil = _logs()
    assert JOB in postulaciones and f"(LinkedIn {JOB})" in perfil


def test_a_broken_markdown_log_never_undoes_the_send(env, monkeypatch, tmp_path):
    broken = tmp_path / "sin-tabla.md"
    broken.write_text("# sin tabla\n", encoding="utf-8")
    monkeypatch.setenv("LINKEDIN_MCP_PERFIL", str(broken))
    form = env["use"](FakeForm(STANDARD))
    form.allow_submit = True
    r = server.linkedin_apply_prepare(JOB)
    server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    sent = server.linkedin_apply_submit(JOB, confirm=True)
    assert sent["submitted"] and "registro-sync" in sent["registro_error"]
    assert len(env["guard"].applications()) == 1


def test_an_unexpected_send_gets_rows_too(env):
    form = env["use"](FakeForm(STANDARD))
    form.submit_on_next = 0
    out = server.linkedin_apply_prepare(JOB)
    assert out["status"] == "unexpected_submit" and out["registro"]["perfil.md"] == [JOB]
    assert "sin el" in _logs()[1]


class Applied(FakeForm):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.applied = True

    def js(self, win, idx, action, arg=None, select=False):
        out = super().js(win, idx, action, arg, select)
        if action == "job_detail":
            out["applied_status"] = "Solicitud enviada hace 1 minuto"
        return out


def _navigable(env):
    mp = env["monkeypatch"]
    mp.setattr(server.sb, "navigate", lambda win, idx, url: {"out": ""})
    mp.setattr(server.sb, "wait_for_load", lambda win, idx, timeout=30: {})


def test_record_manual(env):
    _navigable(env)
    env["use"](FakeForm(STANDARD))
    assert server.linkedin_record_manual(JOB)["status"] == "not_applied"
    env["use"](Applied(STANDARD))
    env["clock"].t += 10
    server.jobs.put(JOB, {"job_id": JOB, "title": "x", "apply_type": "ats_continue"})  # read before Allan pressed
    out = server.linkedin_record_manual(JOB, via="ats_continue", notes="pulsó Continuar en SmartRecruiters")
    assert out["recorded"] and out["entry"]["manual"] is True and out["entry"]["via"] == "ats_continue"
    assert server.jobs.get(JOB)["data"]["apply_type"] == "applied"  # the cache no longer says ats_continue
    assert out["registro"]["Postulaciones-LinkedIn.md"] == [JOB]
    assert env["guard"].counters()["applications"] == 1
    assert server.linkedin_record_manual(JOB)["status"] == "already_in_log"
    assert server.linkedin_record_manual("4382109958", via="Bad Via!")["status"] == "bad_via"


def test_record_manual_is_not_blocked_by_a_full_cap(env):
    _navigable(env)
    env["use"](Applied(STANDARD))
    for i in range(10):
        env["guard"].record_submit({"job_id": str(4_000_000_000 + i)})
    env["clock"].t += 10
    assert server.linkedin_record_manual(JOB)["recorded"] is True
    assert env["guard"].counters()["applications"] == 11


def test_cli_registro_sync_dry_run_and_write():
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "cli.py"), *a],  # noqa: E731
                                    capture_output=True, text=True, timeout=60, cwd=ROOT)
    r = run("registro-sync", "--dry-run", "--full")
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "dry_run"
    assert run("registro-sync", "{}").returncode == 2  # no arguments



# --- review of tanda 5 ---

def test_a_re_send_after_an_unconfirmed_attempt_gets_its_own_row(copies):
    p, q = copies
    first = {**ENTRY, "confirmed": False, "unexpected": True, "via": "fill_all"}
    registro.sync([first], p, q)
    later = {**ENTRY, "ts": "2026-10-07T10:02:00"}
    assert registro.sync([first, later], p, q)["added"] == {"Postulaciones-LinkedIn.md": ["4474644406"],
                                                             "perfil.md": ["4474644406"]}
    assert sum("4474644406" in line for line in p.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.parametrize("via,confirmed,postulaciones,perfil", [
    ("submit", True, "con el \"sí\" de Allan; el clic en Enviar no se pudo comprobar", "**Enviada** ("),
    ("submit", False, "sin confirmar: comprobar en LinkedIn", "**Posible envío, sin confirmar**"),
    ("close", True, "LinkedIn mostró la confirmación al cerrar", "**Enviada desde Safari**"),
    ("fill_all", True, "sin el \"sí\" de Allan (LinkedIn la marca enviada)", "**Enviada sin el sí de Allan**"),
    ("fill_all", False, "sin el \"sí\" de Allan (sin confirmar", "**Posible envío sin el sí de Allan, sin confirmar**"),
])
def test_unexpected_sends_are_worded_by_how_they_happened(via, confirmed, postulaciones, perfil):
    e = {**ENTRY, "unexpected": True, "via": via, "confirmed": confirmed}
    assert postulaciones in registro.postulaciones_row(e)
    assert perfil in registro.perfil_row(e)


def test_a_pipe_in_the_cv_name_cannot_break_the_perfil_table():
    e = {**ENTRY, "resume": {**ENTRY["resume"], "name": "CV | 2026.pdf"}}
    assert registro.perfil_row(e).count(" | ") == 2


def test_record_manual_refuses_jobs_in_the_markdown_logs_or_another_page(env):
    env["use"](Applied(STANDARD))
    Path(config.perfil_md()).write_text(Path(config.perfil_md()).read_text(encoding="utf-8").replace(
        "|---|---|---|\n", f"|---|---|---|\n| cbc (LinkedIn {JOB}) | Enviada por Allan | 06/10/2026 13:53 |\n"),
        encoding="utf-8")
    assert server.linkedin_record_manual(JOB)["status"] == "already_in_markdown"
    assert env["guard"].counters()["job_views"] == 0


def test_record_manual_reads_the_work_tab_without_a_new_view(env):
    form = env["use"](Applied(STANDARD))
    out = server.linkedin_record_manual(JOB)
    assert out["recorded"] and env["guard"].counters()["job_views"] == 0
    assert out["entry"]["applied_status"].startswith("Solicitud enviada")
    other = env["use"](Applied(STANDARD))
    real = other.js
    other.js = lambda win, idx, action, arg=None, select=False: (
        {**real(win, idx, action, arg, select), "job_id": "4382109958"} if action == "job_detail" else
        real(win, idx, action, arg, select))
    env["monkeypatch"].setattr(server, "_js", other.js)
    env["guard"].set("work_tab", {"id": "7:2", "window_id": 7, "job_id": "4476101386"})
    _navigable(env)
    assert server.linkedin_record_manual("4476101386")["status"] == "job_not_shown"


def test_the_step_by_step_flow_logs_its_answers_too(env):
    form = env["use"](FakeForm(STANDARD))
    form.allow_submit = True
    server.linkedin_apply_start(JOB)
    server.linkedin_apply_next()
    server.linkedin_apply_next()
    server.linkedin_apply_fill({ITSM_LABEL: "5", "What is your level of proficiency in English?": "Professional",
                                SALARY: "3000"})
    server.linkedin_apply_next()
    sent = server.linkedin_apply_submit(JOB, confirm=True)
    assert sent["confirmed"]
    answers = env["guard"].applications()[0]["answers"]
    assert answers[SALARY] == "3000" and answers["Mobile phone number"] == "57030067"
