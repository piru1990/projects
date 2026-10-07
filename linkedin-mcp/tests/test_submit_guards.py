"""Safeguards around the Easy Apply dialog, with Safari replaced by a fake page (nothing reaches the browser)."""

import ast
import json
from pathlib import Path

import pytest

import server
from guard import Guard, load_limits
from jobcache import JobCache
from resumes import ResumeLedger

ROOT = Path(__file__).resolve().parents[1]
JOB = "4468912423"


class Clock:
    def __init__(self, t=1_791_300_000.0):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakePage:
    """The work tab: a job page with an Easy Apply dialog on its review step."""

    def __init__(self):
        self.job_id = JOB
        self.apply_type = "easy_apply"
        self.open = True
        self.company = "Empresa Confidencial"
        self.fields = []
        self.review_text = "Revisa tu solicitud\nCurrículum: CV-Allan-Rosales-Tecnologia-ERP.pdf (6/10/2026)"
        self.after_submit = "sent"  # "sent" | "errors"
        self.calls = []

    def js(self, win, idx, action, arg=None, select=False):
        self.calls.append(action)
        if action == "job_detail":
            return {"job_id": self.job_id, "title": "Service Manager", "apply_type": self.apply_type}
        if action == "modal_read":
            if not self.open:
                return {"open": False, "save_prompt": False, "success": False}
            return {"open": True, "company": self.company, "is_review": True, "fields": self.fields,
                    "errors": self.errors if self.after_submit == "errors" and "click_submit" in self.calls else [],
                    "review_text": self.review_text, "buttons": ["Enviar solicitud"]}
        if action == "set_follow":
            return {"status": "ok", "checked": bool(arg)}
        if action == "click_submit":
            if self.after_submit == "sent":
                self.open, self.apply_type = False, "applied"
            return {"status": "clicked", "label": "Enviar solicitud"}
        return {"status": "ok"}

    errors = ["Phone: Este campo es obligatorio"]


@pytest.fixture
def page(tmp_path, monkeypatch):
    clock = Clock()
    g = Guard(state_dir=tmp_path, limits=load_limits({}), now=clock.now, sleep=clock.sleep)
    p = FakePage()
    monkeypatch.setattr(server, "guard", g)
    monkeypatch.setattr(server, "jobs", JobCache(tmp_path, now=clock.now))
    monkeypatch.setattr(server, "resume_ledger", ResumeLedger(tmp_path))
    monkeypatch.setattr(server, "_work_tab", lambda: ((7, 2), None))
    monkeypatch.setattr(server, "_checkpoint", lambda win, idx: None)
    monkeypatch.setattr(server, "_js", p.js)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def poll(fn, ok, timeout, step=0.8):
        last = {}
        for _ in range(3):
            last = fn()
            if not last.get("_error") and ok(last):
                break
        return last

    monkeypatch.setattr(server, "_poll", poll)
    g.set("work_tab", {"id": "7:2", "window_id": 7, "job_id": JOB})
    g.set("current_application", {"job_id": JOB, "title": "Service Manager", "company": "Empresa Confidencial",
                                  "url": f"https://www.linkedin.com/jobs/view/{JOB}/",
                                  "resume": {"name": "CV-Allan-Rosales-Tecnologia-ERP.pdf", "date": "6/10/2026"}})
    p.guard = g
    return p


def submit():
    return server.linkedin_apply_submit(JOB, confirm=True)


def test_happy_path_records_once_and_marks_the_cache(page):
    server.jobs.put(JOB, {"job_id": JOB, "apply_type": "easy_apply"})
    r = submit()
    assert r["submitted"] and r["confirmed"] and r["cache_error"] is None
    assert [a["job_id"] for a in page.guard.applications()] == [JOB]
    assert page.guard.get("current_application") is None
    assert server.jobs.get(JOB)["data"]["apply_type"] == "applied"


def test_without_confirm_nothing_is_clicked(page):
    assert server.linkedin_apply_submit(JOB)["status"] == "confirmation_required"
    assert "click_submit" not in page.calls


@pytest.mark.parametrize("setup,status", [
    (lambda p: setattr(p, "job_id", "4382109958"), "job_mismatch"),
    (lambda p: setattr(p, "company", "Otra Empresa S.A."), "company_mismatch"),
    (lambda p: setattr(p, "fields", [{"label": "Código del país", "type": "select", "required": True,
                                      "value": "Selecciona una opción"}]), "form_incomplete"),
    (lambda p: setattr(p, "review_text", "Currículum: CV-Allan Rosales.pdf (6/10/2026)"), "resume_mismatch"),
    (lambda p: setattr(p, "fields", [{"label": "Currículum", "type": "resume", "required": True,
                                      "value": "CV-Allan-Rosales-Tecnologia-ERP.pdf",
                                      "resumes": [{"index": 0, "name": "CV-Allan-Rosales-Tecnologia-ERP.pdf",
                                                   "date": "1/10/2026", "selected": True}]}]), "resume_mismatch"),
])
def test_checks_before_the_click(page, setup, status):
    setup(page)
    r = submit()
    assert r["status"] == status
    assert "click_submit" not in page.calls and page.guard.applications() == []


def test_errors_after_the_click_mean_nothing_was_sent(page):
    page.after_submit = "errors"
    r = submit()
    assert r["status"] == "form_has_errors" and r["submitted"] is False
    assert page.guard.applications() == [] and page.guard.counters()["applications"] == 0
    assert page.guard.get("current_application")["job_id"] == JOB


def test_open_application_must_match_the_work_tab(page):
    page.guard.set("work_tab", {"id": "7:2", "window_id": 7, "job_id": "4382109958"})
    for call in (submit, server.linkedin_apply_next, server.linkedin_apply_read,
                 lambda: server.linkedin_apply_fill({"Phone": "57030067"})):
        assert call()["status"] == "work_tab_mismatch"
    assert "click_submit" not in page.calls and "modal_fill" not in page.calls
    closed = server.linkedin_apply_close()
    assert closed["status"] == "forgotten" and page.guard.get("current_application") is None


def test_get_job_never_navigates_away_from_an_open_application(page, monkeypatch):
    navigated = []
    monkeypatch.setattr(server.sb, "navigate", lambda *a: navigated.append(a) or {"out": ""})
    r = server.linkedin_get_job("4382109958")
    assert r["status"] == "application_in_progress" and navigated == []
    assert server.linkedin_get_job(JOB, refresh=True)["status"] == "application_in_progress"
    server.jobs.put("4382109958", {"job_id": "4382109958", "title": "x", "apply_type": "easy_apply"})
    cached = server.linkedin_get_job("4382109958")  # reading the cache is still fine
    assert cached["from_cache"] is True and cached["application_in_progress"]["job_id"] == JOB


def _upload_page(monkeypatch, lists):
    """modal_read returns the resume lists in order (before upload_begin, then each poll)."""
    reads = iter(lists)
    last = {"v": lists[-1]}

    def js(win, idx, action, arg=None, select=False):
        if action == "modal_read":
            rs = next(reads, last["v"])
            return {"open": True, "fields": [{"label": "Currículum", "type": "resume", "resumes": rs}]}
        return {"upload_begin": {"status": "ready"}, "file_chunk": {"status": "ok"},
                "file_commit": {"status": "committed"}}.get(action, {})

    monkeypatch.setattr(server, "_js", js)


def _r(i, name, date, selected):
    return {"index": i, "name": name, "date": date, "selected": selected}


def test_upload_records_the_new_entry_in_the_ledger(page, tmp_path, monkeypatch):
    pdf = tmp_path / "CV-Prueba.pdf"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    _upload_page(monkeypatch, [[_r(0, "otro.pdf", "1/10/2026", True)],
                               [_r(0, "CV-Prueba.pdf", "7/10/2026", True), _r(1, "otro.pdf", "1/10/2026", False)]])
    r = server.linkedin_apply_upload_resume(str(pdf))
    assert r["uploaded"] is True
    assert server.resume_ledger.lookup("CV-Prueba.pdf", "7/10/2026")["sha256"] == r["sha256"]
    assert page.guard.get("current_application")["resume"]["date"] == "7/10/2026"


def test_upload_ignores_an_old_preselected_file_with_the_same_name(page, tmp_path, monkeypatch):
    pdf = tmp_path / "CV-Prueba.pdf"
    pdf.write_bytes(b"%PDF-1.4 nuevo")
    old = [_r(0, "CV-Prueba.pdf", "1/10/2026", True), _r(1, "otro.pdf", "1/10/2026", False)]
    _upload_page(monkeypatch, [old, old])  # LinkedIn never shows the new upload
    r = server.linkedin_apply_upload_resume(str(pdf), timeout=0.01)
    assert r["uploaded"] is False
    assert server.resume_ledger.entries() == []
    assert page.guard.get("current_application")["resume"]["date"] == "6/10/2026"  # the approved one is untouched
    _upload_page(monkeypatch, [old, [_r(0, "CV-Prueba.pdf", "7/10/2026", True)] + old])
    r = server.linkedin_apply_upload_resume(str(pdf))
    assert r["uploaded"] is True and server.resume_ledger.lookup("CV-Prueba.pdf", "1/10/2026") is None
    assert server.resume_ledger.lookup("CV-Prueba.pdf", "7/10/2026")["sha256"] == r["sha256"]


@pytest.mark.parametrize("setup", [
    lambda p: setattr(p, "review_text", "Currículum: (no se pudo leer cuál está elegido) [lista de 2 CV omitida]"),
    lambda p: setattr(p, "review_text", "Revisa tu solicitud"),
    lambda p: setattr(p, "fields", [{"label": "Currículum", "type": "resume", "required": False, "value": None,
                                     "resumes": [_r(0, "CV-Allan-Rosales-Tecnologia-ERP.pdf", "6/10/2026", False)]}]),
])
def test_an_approved_resume_that_cannot_be_seen_blocks_the_submit(page, setup):
    setup(page)
    r = submit()
    assert r["status"] in ("resume_unknown", "form_incomplete")
    assert "click_submit" not in page.calls


def test_select_resume_respects_the_pause(page):
    page.guard.pause("text:security check", "https://www.linkedin.com/checkpoint/")
    assert server.linkedin_apply_select_resume(name="x.pdf")["status"] == "paused_checkpoint"
    assert "select_resume" not in page.calls


def test_dialog_clicks_keep_the_fixed_gap(tmp_path, monkeypatch):
    clock = Clock()
    g = Guard(state_dir=tmp_path, limits=load_limits({}), now=clock.now, sleep=clock.sleep)
    monkeypatch.setattr(server, "guard", g)
    monkeypatch.setattr(server.sb, "run_js", lambda win, idx, js, timeout=60: {"out": json.dumps({"status": "clicked"})})
    start = clock.t
    for action in ("click_next", "modal_fill", "click_next"):
        server._js(1, 1, action)
    assert clock.t - start == 6  # 3 s before the 2nd and the 3rd, none before the 1st
    server._js(1, 1, "modal_read")  # reads don't wait
    assert clock.t - start == 6


# --- source-level guarantees ---

def _calls_with_literal(path: Path, literal: str):
    """(enclosing function, call args) for every call that passes ``literal`` as a string constant."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and any(isinstance(a, ast.Constant) and a.value == literal for a in node.args):
                    out.append((fn.name, [a.value if isinstance(a, ast.Constant) else None for a in node.args]))
    return out


def test_click_submit_is_only_in_linkedin_apply_submit():
    for py in ROOT.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        if py.name == "server.py":
            assert {f for f, _ in _calls_with_literal(py, "click_submit")} == {"linkedin_apply_submit"}
            assert text.count('"click_submit"') == 2  # the call and the _DIALOG_ACTIONS pacing set
        else:
            assert "click_submit" not in text, py.name


def test_modal_click_only_closes_the_confirmation():
    calls = _calls_with_literal(ROOT / "server.py", "modal_click")
    assert calls and all(args[args.index("modal_click") + 1] in ("Listo", "Done") for _, args in calls)
