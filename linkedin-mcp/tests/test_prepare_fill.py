"""linkedin_apply_prepare / linkedin_apply_fill_all / linkedin_inspect / linkedin_answers_save against a fake form.

Safari is replaced by FakeForm (nothing reaches the browser). The form mimics the real ones seen on 06/10/2026:
contact step prefilled by LinkedIn, resume picker, screening questions, review with "Enviar solicitud".
"""

import copy
import shutil

import pytest

import answers as A
import config
import server
from guard import Guard, load_limits
from jobcache import JobCache
from resumes import ResumeLedger

JOB = "4468912423"
CV = "CV-Allan-Rosales-Tecnologia-ERP.pdf"
ITSM = "How many years of work experience do you have with IT Service Management?"
ENGLISH = "What is your level of proficiency in English?"
SALARY = "Cual es su expectativa salarial mensual en USD$ ?"


class Clock:
    def __init__(self, t=1_791_300_000.0):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _kind(label):
    return {"Enviar solicitud": "submit", "Continuar": "continue", "Siguiente": "next", "Revisar": "next",
            "Atrás": "back", "Volver": "back"}.get(label, "other")


def contact_step():
    return {"fields": [
        {"label": "Email address", "type": "select", "required": True, "value": "rosales.allan@gmail.com",
         "options": ["Selecciona una opción", "rosales.allan@gmail.com"]},
        {"label": "Código del país", "type": "select", "required": True, "value": "Guatemala (+502)",
         "options": ["Selecciona una opción", "Guatemala (+502)", "México (+52)"]},
        {"label": "Mobile phone number", "type": "text", "required": True, "value": "57030067"}],
        "buttons": ["Siguiente"]}


def resume_step(selected=0):
    names = [CV, "CV-Allan Rosales.pdf"]
    return {"fields": [{"label": "Currículum", "type": "resume", "required": True, "value": names[selected], "resumes": [
        {"index": 0, "name": CV, "date": "6/10/2026", "selected": selected == 0},
        {"index": 1, "name": "CV-Allan Rosales.pdf", "date": "6/10/2026", "selected": selected == 1}]}],
        "buttons": ["Atrás", "Siguiente"]}


def questions_step(salary=""):
    return {"fields": [
        {"label": ITSM, "type": "number", "required": True, "value": ""},
        {"label": ENGLISH, "type": "radio", "required": True, "value": None,
         "options": ["None", "Conversational", "Professional", "Native or bilingual"]},
        {"label": SALARY, "type": "text", "required": True, "value": salary}],
        "buttons": ["Atrás", "Revisar"]}


def review_step():
    return {"fields": [], "buttons": ["Atrás", "Enviar solicitud"],
            "review_text": f"Revisa tu solicitud\nCurrículum: {CV} (6/10/2026)"}


class FakeForm:
    def __init__(self, steps, start=1, one_page=False):
        self.steps = copy.deepcopy(steps)
        self.start = start
        self.one_page = one_page
        self.i = None
        self.errors = []
        self.applied = False
        self.submit_on_next = None  # step index where "Siguiente" turns out to send the application
        self.allow_submit = False
        self.calls = []

    @property
    def advanced(self):
        return [a for a, _ in self.calls if a == "click_next"]

    def read(self):
        if self.i is None:
            return {"open": False, "save_prompt": False, "success": False}
        st = self.steps[self.i]
        buttons = st["buttons"] + ["Descartar"]
        out = {"open": True, "save_prompt": False, "success": False, "company": "Empresa Confidencial",
               "dialog_title": "Aplicar a Empresa Confidencial", "fields": copy.deepcopy(st["fields"]),
               "buttons": buttons, "button_kinds": [_kind(b) for b in buttons],
               "is_review": "Enviar solicitud" in buttons, "errors": list(self.errors),
               "step": None if self.one_page else self.i + 1, "steps": None if self.one_page else len(self.steps)}
        if out["is_review"]:
            out["review_text"] = st.get("review_text", "")
        return out

    def field(self, label):
        hits = [f for f in self.steps[self.i]["fields"] if f["label"] == label]
        assert len(hits) == 1, label
        return hits[0]

    def js(self, win, idx, action, arg=None, select=False):
        self.calls.append((action, copy.deepcopy(arg)))
        if action == "job_detail":
            return {"job_id": JOB, "url": f"https://www.linkedin.com/jobs/view/{JOB}/", "title": "Service Manager",
                    "company": "Empresa Confidencial", "apply_type": "applied" if self.applied else "easy_apply",
                    "description": "…", "external_url": "", "ats": ""}
        if action == "page_state":
            return {"url": f"https://www.linkedin.com/jobs/view/{JOB}/", "title": "Service Manager | Empresa | LinkedIn",
                    "headings": [], "alerts": [], "captcha_frame": False}
        if action == "modal_read":
            return self.read()
        if action == "open_easy_apply":
            self.i = self.start - 1
            return {"status": "clicked"}
        if action == "click_next":
            buttons = self.steps[self.i]["buttons"]
            if not any(_kind(b) == "next" for b in buttons):
                return {"status": "no_next_button", "buttons": buttons}
            if arg and arg.get("expect") is not None:  # like linkedin.js: refuse if the fields aren't the planned ones
                now = [[f["label"], f["type"], f.get("value")] for f in self.steps[self.i]["fields"]]
                if now != [list(e) for e in arg["expect"]]:
                    return {"status": "step_changed"}
            if self.submit_on_next == self.i:
                self.i, self.applied = None, True
                return {"status": "clicked", "label": "Siguiente"}
            empty = [f for f in self.steps[self.i]["fields"]
                     if (f.get("required") or f.get("linkedin_requires")) and A.current_value(f) in ("", [])]
            for f in empty:
                f["error"] = "Este campo es obligatorio"
            if empty:
                self.errors = [f"{f['label']}: Este campo es obligatorio" for f in empty]
            else:
                self.errors, self.i = [], self.i + 1
            return {"status": "clicked", "label": "Siguiente"}
        if action == "modal_fill":
            results = {}
            for label, value in arg.items():
                self.field(label)["value"] = value
                results[label] = {"status": "set", "label": label}
            return {"status": "filled", "results": results}
        if action == "select_resume":
            res = next(f for f in self.steps[self.i]["fields"] if f["type"] == "resume")
            for r in res["resumes"]:
                r["selected"] = r["index"] == arg["index"]
            sel = res["resumes"][arg["index"]]
            res["value"] = sel["name"]
            return {"status": "selected", "index": sel["index"], "name": sel["name"], "date": sel["date"]}
        if action == "click_submit":
            assert self.allow_submit, "click_submit outside linkedin_apply_submit"
            self.i, self.applied = None, True
            return {"status": "clicked", "label": "Enviar solicitud"}
        if action == "set_follow":
            return {"status": "ok", "checked": bool(arg)}
        if action == "close_modal":
            if self.i is None:
                return {"status": "no_dialog"}
            self.i = None
            return {"status": "saved" if (arg or {}).get("save") else "discarded"}
        raise AssertionError(f"unexpected action {action}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    clock = Clock()
    g = Guard(state_dir=tmp_path, limits=load_limits({}), now=clock.now, sleep=clock.sleep)
    monkeypatch.setattr(server, "guard", g)
    monkeypatch.setattr(server, "jobs", JobCache(tmp_path, now=clock.now))
    ledger = ResumeLedger(tmp_path)
    ledger.add(CV, "6/10/2026", "37b42fc0" + "0" * 56, note="como el registro real")
    monkeypatch.setattr(server, "resume_ledger", ledger)
    monkeypatch.setattr(server, "_work_tab", lambda: ((7, 2), None))
    monkeypatch.setattr(server, "_checkpoint", lambda win, idx: None)
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

    def use(form):
        monkeypatch.setattr(server, "_js", form.js)
        return form

    return {"guard": g, "use": use, "clock": clock, "tmp": tmp_path, "monkeypatch": monkeypatch}


def key_of(result, label):
    hits = [q["key"] for q in result["questionnaire"] if q["label"] == label]
    assert len(hits) == 1, label
    return hits[0]


STANDARD = [contact_step(), resume_step(), questions_step(), review_step()]


def test_prepare_stops_at_the_first_step_with_questions_and_fills_nothing(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "prepared" and r["stopped_at"]["step"] == 3 and r["stopped_at"]["reason"] == "decision"
    assert r["complete"] is False and r["dialog_open"] is True
    draft = r["answers_draft"]
    assert draft[key_of(r, ITSM)] == "5" and draft[key_of(r, ENGLISH)] == "Professional"
    assert draft[key_of(r, "Mobile phone number")] == "57030067"
    assert r["to_ask"] == [key_of(r, SALARY)]
    assert r["resume"]["decision"] == "prefilled_ok"
    actions = [a for a, _ in form.calls]
    assert "modal_fill" not in actions and "select_resume" not in actions and "close_modal" not in actions
    assert len(form.advanced) == 2 and form.i == 2  # pressed Siguiente twice, stayed on the questions
    app = env["guard"].get("current_application")
    assert app["phase"] == "prepared" and app["resume"]["name"] == CV
    assert app["answers_filled"][key_of(r, "Mobile phone number")]["value"] == "57030067"


def test_fill_all_reaches_the_review_and_submit_records_the_real_values(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    filled = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert filled["status"] == "at_review", filled
    fills = [arg for a, arg in form.calls if a == "modal_fill"]
    assert fills == [{ITSM: "5", ENGLISH: "Professional", SALARY: "3000"}]
    assert filled["answers_filled"][key_of(r, SALARY)]["value"] == "3000"
    assert "click_submit" not in [a for a, _ in form.calls]
    form.allow_submit = True
    sent = server.linkedin_apply_submit(JOB, confirm=True)
    assert sent["submitted"] and sent["confirmed"]


def test_a_step_prepare_never_saw_gets_only_contact_data(env):
    pmp = {"fields": [{"label": "Do you have a PMP certification?", "type": "radio", "required": True,
                       "value": None, "options": ["Yes", "No"]},
                      {"label": "Phone", "type": "text", "required": True, "value": ""}],
           "buttons": ["Atrás", "Revisar"]}
    form = env["use"](FakeForm([contact_step(), questions_step(), pmp, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["step"] == 2
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "needs_answers" and out["new_step"] is True and out["step"] == 3
    assert [q["label"] for q in out["questions"]] == ["Do you have a PMP certification?"]
    assert sorted(out["answers_draft"].values()) == ["57030067", "Yes"]  # proposed, nothing filled yet
    assert [arg for a, arg in form.calls if a == "modal_fill"] == [{ITSM: "5", ENGLISH: "Professional", SALARY: "3000"}]
    again = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000", **out["answers_draft"]})
    assert again["status"] == "at_review"
    assert [arg for a, arg in form.calls if a == "modal_fill"][-1] == {"Do you have a PMP certification?": "Yes",
                                                                       "Phone": "57030067"}


def test_a_prefilled_salary_is_asked_and_never_kept_silently(env):
    env["use"](FakeForm([contact_step(), questions_step(salary="3000"), review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    salary = next(q for q in r["questionnaire"] if q["label"] == SALARY)
    assert salary["decision"] == "ask" and salary["current"] == "3000" and salary["key"] in r["to_ask"]
    out = server.linkedin_apply_fill_all(JOB, r["answers_draft"])
    assert out["status"] == "needs_answers" and out["new_step"] is False
    assert [q["label"] for q in out["questions"]] == [SALARY]


def test_continuar_is_never_pressed(env):
    step = contact_step()
    step["buttons"] = ["Continuar"]
    form = env["use"](FakeForm([step, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "no_next_button" and form.i == 0 and not form.applied


def test_a_next_that_sends_is_recorded_and_pauses(env):
    form = env["use"](FakeForm(STANDARD))
    form.submit_on_next = 0
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "unexpected_submit"
    log = env["guard"].applications()
    assert len(log) == 1 and log[0]["unexpected"] is True and log[0]["job_id"] == JOB
    assert env["guard"].paused_error() is not None and env["guard"].get("current_application") is None
    assert env["guard"].counters()["applications"] == 1


def test_a_saved_draft_is_not_touched(env):
    form = env["use"](FakeForm(STANDARD, start=3))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "draft_detected" and r["stopped_at"]["step"] == 3
    assert form.advanced == [] and "modal_fill" not in [a for a, _ in form.calls]


def test_prepare_refuses_while_something_is_open(env):
    form = env["use"](FakeForm(STANDARD))
    env["guard"].set("current_application", {"job_id": "4382109958"})
    assert server.linkedin_apply_prepare(JOB)["status"] == "application_in_progress"
    env["guard"].set("current_application", None)
    form.i = 0  # a form already open in the tab (Allan's, or a draft)
    assert server.linkedin_apply_prepare(JOB)["status"] == "dialog_already_open"
    assert [a for a, _ in form.calls if a not in ("job_detail", "modal_read")] == []


def test_one_page_form_is_filled_but_nothing_is_pressed(env):
    page = {"fields": contact_step()["fields"] + resume_step(selected=1)["fields"] + questions_step()["fields"][2:],
            "buttons": ["Enviar solicitud"], "review_text": f"Currículum: {CV} (6/10/2026)"}
    form = env["use"](FakeForm([page], one_page=True))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "decision" and r["complete"] is False
    assert r["resume"]["decision"] == "select"
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "Q20,000 negociable"})
    assert out["status"] == "at_review" and out["resume"]["name"] == CV
    assert form.advanced == [] and "click_submit" not in [a for a, _ in form.calls]


def test_an_answer_must_be_one_of_the_options(env):
    env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, ENGLISH): "Fluent",
                                               key_of(r, SALARY): "3000"})
    assert out["status"] == "needs_answers"
    assert out["questions"][0]["label"] == ENGLISH and "no es una de las opciones" in out["questions"][0]["reason"]


def test_fill_all_needs_prepare_and_the_same_job(env):
    env["use"](FakeForm(STANDARD))
    assert server.linkedin_apply_fill_all(JOB, {})["status"] == "no_application"
    env["guard"].set("current_application", {"job_id": JOB, "phase": "started"})
    assert server.linkedin_apply_fill_all(JOB, {})["status"] == "not_prepared"
    env["guard"].set("current_application", {"job_id": JOB, "phase": "prepared"})
    assert server.linkedin_apply_fill_all("4382109958", {})["status"] == "job_mismatch"


def test_prepare_navigates_only_when_needed(env):
    env["guard"].set("work_tab", {"id": "7:2", "window_id": 7, "job_id": "4382109958"})
    navigations = []
    mp = env["monkeypatch"]
    mp.setattr(server.sb, "navigate", lambda win, idx, url: navigations.append(url) or {"out": ""})
    mp.setattr(server.sb, "wait_for_load", lambda win, idx, timeout=30: {})
    env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "prepared" and navigations == [f"https://www.linkedin.com/jobs/view/{JOB}/"]
    assert env["guard"].counters()["job_views"] == 1


def test_inspect_only_reads(env):
    form = env["use"](FakeForm(STANDARD))
    form.i = 1
    r = server.linkedin_inspect()
    assert r["job"]["apply_type"] == "easy_apply" and r["dialog"]["step"] == 2
    assert {a for a, _ in form.calls} <= {"page_state", "job_detail", "modal_read"}
    assert env["guard"].counters()["job_views"] == 0
    env["monkeypatch"].setattr(form, "js", lambda *a, **k: {"url": "https://www.linkedin.com/messaging/thread/1/"}
                               if a[2] == "page_state" else {})
    env["monkeypatch"].setattr(server, "_js", form.js)
    assert server.linkedin_inspect()["status"] == "not_jobs_page"


def test_answers_save_previews_then_writes(env):
    skill = env["tmp"] / "skill"
    (skill / "references").mkdir(parents=True)
    shutil.copy(config.bank_json(), skill / "references" / "respuestas.json")
    env["monkeypatch"].setenv("LINKEDIN_MCP_SKILL_DIR", str(skill))
    before = (skill / "references" / "respuestas.json").read_text(encoding="utf-8")
    entry = {"question": "Años con Salesforce", "patterns": {"en": ["salesforce"]}, "applies": "years",
             "answer": {"number": 2}}
    preview = server.linkedin_answers_save([entry])
    assert preview["status"] == "preview" and "salesforce" in preview["diff"]
    assert (skill / "references" / "respuestas.json").read_text(encoding="utf-8") == before
    saved = server.linkedin_answers_save([entry], confirm=True)
    assert saved["status"] == "saved"
    assert "Años con Salesforce" in (skill / "references" / "respuestas-linkedin.md").read_text(encoding="utf-8")
    refused = server.linkedin_answers_save([{"id": "salario", "answer": {"text": "3000"}}], confirm=True)
    assert refused["status"] == "rejected"



# --- review findings (tanda 4) ---

class LazyForm(FakeForm):
    """Each step's first read shows the dialog shell without fields: LinkedIn draws them a moment later."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.drawn = set()

    def read(self):
        out = super().read()
        if out.get("open") and self.i not in self.drawn:
            self.drawn.add(self.i)
            out["fields"] = []
        return out


def test_a_half_drawn_step_is_never_passed(env):
    form = env["use"](LazyForm([contact_step(), resume_step(selected=1), questions_step(salary="3000"), review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["step"] == 2 and r["resume"]["decision"] == "select"
    assert len(form.advanced) == 1


class ConditionalForm(FakeForm):
    def js(self, win, idx, action, arg=None, select=False):
        out = super().js(win, idx, action, arg, select)
        if action == "modal_fill" and ENGLISH in arg:  # LinkedIn adds a follow-up, prefilled from an old application
            self.steps[self.i]["fields"].append({"label": "Expected monthly salary in MXN", "type": "text",
                                                 "required": True, "value": "50000"})
        return out


def test_a_question_that_appears_after_filling_is_asked(env):
    form = env["use"](ConditionalForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "needs_answers" and out["new_step"] is True
    assert [q["label"] for q in out["questions"]] == ["Expected monthly salary in MXN"]
    assert len(form.advanced) == 2  # only prepare's two; nothing pressed on the questions step


class SuccessForm(FakeForm):
    """Siguiente sends the application: LinkedIn's confirmation shows, but the job page hasn't caught up."""

    def __init__(self, *a, success=True, **k):
        super().__init__(*a, **k)
        self.success_at, self.sent, self.success = None, False, success

    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next" and self.success_at == self.i:
            self.calls.append((action, arg))
            self.i, self.sent = None, True
            return {"status": "clicked", "label": "Siguiente"}
        if action == "modal_read" and self.sent:
            self.calls.append((action, arg))
            return {"open": False, "save_prompt": False, "success": self.success,
                    "success_text": "Se envió tu solicitud a Empresa Confidencial" if self.success else ""}
        return super().js(win, idx, action, arg, select)


def test_a_confirmation_after_next_is_recorded_and_pauses(env):
    form = env["use"](SuccessForm(STANDARD))
    form.success_at = 0
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "unexpected_submit"
    log = env["guard"].applications()
    assert len(log) == 1 and log[0]["confirmed"] is True and log[0]["unexpected"] is True
    assert env["guard"].paused_error() is not None and env["guard"].counters()["applications"] == 1


def test_a_form_that_vanishes_is_recorded_unconfirmed_and_pauses(env):
    form = env["use"](SuccessForm(STANDARD, success=False))
    form.success_at = 0
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "dialog_vanished"
    log = env["guard"].applications()
    assert len(log) == 1 and log[0]["confirmed"] is False
    assert env["guard"].paused_error() is not None and env["guard"].get("current_application") is None


def test_an_unexpected_send_during_fill_all_logs_what_was_sent(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    form.submit_on_next = 2
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "unexpected_submit"
    sent = env["guard"].applications()[0]["answers"]
    assert sent[SALARY] == "3000" and sent[ITSM] == "5"


class StuckForm(FakeForm):
    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next":
            self.calls.append((action, arg))
            return {"status": "clicked", "label": "Siguiente"}  # but nothing changes
        return super().js(win, idx, action, arg, select)


def test_a_press_that_changes_nothing_is_not_repeated(env):
    form = env["use"](StuckForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "did_not_advance" and len(form.advanced) == 1


def test_linkedin_errors_become_questions(env):
    step = contact_step()
    step["fields"].append({"label": "Portfolio URL", "type": "text", "required": False, "value": "",
                           "linkedin_requires": True})
    env["use"](FakeForm([step, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "blocked"
    portfolio = next(q for q in r["questionnaire"] if q["label"] == "Portfolio URL")
    assert portfolio["decision"] == "ask" and "obligatorio" in portfolio["reason"] and portfolio["key"] in r["to_ask"]


def test_a_draft_needs_allans_ok_and_its_cv_is_still_checked(env):
    review = review_step()
    review["review_text"] = "Revisa tu solicitud\nCurrículum: CV-Allan Rosales.pdf (6/10/2026)"
    env["use"](FakeForm([contact_step(), resume_step(selected=1), questions_step(), review], start=3))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "draft_detected"
    answers_ = {**r["answers_draft"], key_of(r, SALARY): "3000"}
    assert server.linkedin_apply_fill_all(JOB, answers_)["status"] == "draft_needs_ok"
    out = server.linkedin_apply_fill_all(JOB, answers_, continue_draft=True)
    assert out["status"] == "resume_mismatch" and out["selected"]["name"] == "CV-Allan Rosales.pdf"


def test_an_older_upload_with_the_same_name_is_not_the_chosen_cv(env):
    step = resume_step()
    step["fields"][0]["resumes"] = [{"index": 0, "name": CV, "date": "6/10/2026", "selected": False},
                                    {"index": 1, "name": CV, "date": "14/2/2025", "selected": True}]
    env["use"](FakeForm([contact_step(), step, questions_step(), review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["step"] == 2 and r["resume"]["decision"] == "select"
    assert r["resume"]["available"][0] == {"index": 0, "name": CV, "date": "6/10/2026"}


def test_answers_of_another_job_are_refused(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    other = {k.replace(f"{JOB}:", "4382109958:"): v for k, v in r["answers_draft"].items()}
    out = server.linkedin_apply_fill_all(JOB, other)
    assert out["status"] == "answers_for_other_job" and "modal_fill" not in [a for a, _ in form.calls]


def test_a_repeated_label_filled_by_hand_lets_fill_all_go_on(env):
    step = {"fields": [{"label": "Comentarios", "type": "textarea", "required": True, "value": ""},
                       {"label": "Comentarios", "type": "textarea", "required": True, "value": ""}],
            "buttons": ["Revisar"]}
    form = env["use"](FakeForm([step, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    keys = [q["key"] for q in r["questionnaire"]]
    assert len(set(keys)) == 2 and all(q["decision"] == "ask" for q in r["questionnaire"])
    for f, text in zip(form.steps[0]["fields"], ("Uno", "Dos")):  # Allan types them in Safari
        f["value"] = text
    out = server.linkedin_apply_fill_all(JOB, dict(zip(keys, ("Uno", "Dos"))))
    assert out["status"] == "at_review" and "modal_fill" not in [a for a, _ in form.calls]


def test_review_can_be_asked_again_and_an_early_exit_stays_resumable(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    full = {**r["answers_draft"], key_of(r, SALARY): "3000"}
    assert server.linkedin_apply_fill_all(JOB, full)["status"] == "at_review"
    assert server.linkedin_apply_fill_all(JOB, full)["status"] == "at_review"
    # an osascript error in the middle of prepare leaves a prepared (not stuck) application
    env["guard"].set("current_application", None)
    broken = env["use"](FakeForm(STANDARD))
    real = broken.js
    broken.js = lambda win, idx, action, arg=None, select=False: (
        {"_error": True, "status": "osascript_failed", "message": "x"} if action == "click_next" else
        real(win, idx, action, arg, select))
    env["monkeypatch"].setattr(server, "_js", broken.js)
    assert server.linkedin_apply_prepare(JOB)["status"] == "osascript_failed"
    assert env["guard"].get("current_application")["phase"] == "prepared"


def test_pages_without_a_counter_get_their_own_keys(env):
    a = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": ""}], "buttons": ["Siguiente"]}
    b = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": ""}], "buttons": ["Revisar"]}
    form = env["use"](FakeForm([a, b, review_step()], one_page=True))
    r = server.linkedin_apply_prepare(JOB)
    first = key_of(r, "Comentarios")
    out = server.linkedin_apply_fill_all(JOB, {first: "Disponible los martes"})
    assert out["status"] == "needs_answers" and out["new_step"] is True
    assert out["questions"][0]["key"] != first
    assert len([1 for act, _ in form.calls if act == "modal_fill"]) == 1


def test_only_verified_contact_data_fills_an_unseen_step():
    import flow
    bank = A.load(config.bank_json())
    new, _, errors = A.save_entries(bank.data, [{"question": "Perfil de LinkedIn", "section": "contacto",
                                                 "patterns": {"en": ["linkedin profile"]},
                                                 "answer": {"text": "https://www.linkedin.com/in/x"}}], "2026-10-07")
    assert errors == [] and new["entries"][-1]["section"] == "aprobadas"
    plan = flow.plan_step([{"label": "LinkedIn profile of a reference", "type": "text", "required": True, "value": ""}],
                          5, {}, CV, set(), A.Bank(new), f"{JOB}:")
    assert plan["fill"] == {} and len(plan["stop"]) == 1



# --- second review (tanda 4) ---

class SpinnerThenSent(FakeForm):
    """After Siguiente the step first shows a spinner (same step, fewer buttons), then the form is gone: sent."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.send_at, self.phase = None, 0

    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next" and self.send_at == self.i and self.phase == 0:
            self.calls.append((action, arg))
            self.phase = 1
            return {"status": "clicked", "label": "Siguiente"}
        if action == "modal_read" and self.phase == 1:
            self.calls.append((action, arg))
            self.phase = 2
            out = self.read()
            out["buttons"], out["fields"] = ["Descartar"], []
            return out
        if action == "modal_read" and self.phase == 2:
            self.calls.append((action, arg))
            return {"open": False, "save_prompt": False, "success": True, "success_text": "Se envió tu solicitud"}
        return super().js(win, idx, action, arg, select)


@pytest.mark.parametrize("send_at", [0, 2])
def test_a_send_after_a_spinner_is_recorded(env, send_at):
    form = env["use"](SpinnerThenSent(STANDARD))
    form.send_at = send_at
    r = server.linkedin_apply_prepare(JOB)
    if send_at == 2:
        r = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert r["status"] == "unexpected_submit", r
    assert env["guard"].counters()["applications"] == 1 and env["guard"].paused_error() is not None


class Blink(FakeForm):
    """The first read after each Siguiente shows no dialog for a moment (the header re-renders)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.blink = False

    def js(self, win, idx, action, arg=None, select=False):
        out = super().js(win, idx, action, arg, select)
        if action == "click_next":
            self.blink = True
        elif action == "modal_read" and self.blink:
            self.blink = False
            return {"open": False, "save_prompt": False, "success": False}
        return out


def test_a_blink_is_not_taken_for_a_send(env):
    env["use"](Blink(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "prepared" and r["stopped_at"]["step"] == 3
    assert env["guard"].applications() == [] and env["guard"].paused_error() is None


class NeverSettles(FakeForm):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.n = 0

    def read(self):
        out = super().read()
        if out.get("open"):
            self.n += 1
            out["fields"] = out["fields"] + [{"label": f"Campo {self.n}", "type": "text", "required": False,
                                               "value": ""}]
        return out


def test_a_step_that_never_settles_is_not_pressed(env):
    form = env["use"](NeverSettles(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "step_not_settled" and form.advanced == []


class SlowOpen(FakeForm):
    def __init__(self, *a, opens_after=3, **k):
        super().__init__(*a, **k)
        self.opens_after, self.reads = opens_after, 0

    def read(self):
        self.reads += 1
        if self.i is not None and self.reads <= self.opens_after:
            return {"open": False, "save_prompt": False, "success": False}
        return super().read()


def test_prepare_waits_for_the_form_and_never_loses_it(env):
    env["use"](SlowOpen(STANDARD, opens_after=3))
    assert server.linkedin_apply_prepare(JOB)["status"] == "prepared"
    env["guard"].set("current_application", None)
    never = env["use"](SlowOpen(STANDARD, opens_after=10_000))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "dialog_not_open"
    assert env["guard"].get("current_application")["phase"] == "opening"  # still closable
    never.opens_after = 0
    never.js = (lambda real: lambda win, idx, action, arg=None, select=False: (
        {"status": "no_dialog"} if action == "close_modal" else real(win, idx, action, arg, select)))(never.js)
    env["monkeypatch"].setattr(server, "_js", never.js)
    never.i = None
    assert server.linkedin_apply_close()["still_open"] is False
    assert env["guard"].get("current_application") is None


def test_submit_needs_fill_all_and_an_unchanged_review(env):
    page = {"fields": contact_step()["fields"] + [{"label": SALARY, "type": "text", "required": True, "value": "50000"}],
            "buttons": ["Enviar solicitud"], "review_text": "Revisa tu solicitud"}
    form = env["use"](FakeForm([page], one_page=True))
    form.allow_submit = True
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "decision"
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "not_at_review"
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "at_review"
    form.steps[0]["fields"][-1]["value"] = "99999"  # someone changes it in Safari after the review was shown
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "review_changed"
    assert not form.applied


def test_a_draft_without_a_counter_is_detected(env):
    a = {"fields": [{"label": "Phone", "type": "text", "required": True, "value": "+1 555 0100"}],
         "buttons": ["Siguiente"]}
    b = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": "hola"}],
         "buttons": ["Atrás", "Revisar"]}
    env["use"](FakeForm([a, b, review_step()], one_page=True, start=2))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "draft_detected"


def test_a_draft_keeps_its_mark_and_an_old_cv_is_not_verified(env):
    step = resume_step()
    step["fields"][0]["resumes"] = [{"index": 0, "name": CV, "date": "6/10/2026", "selected": False},
                                    {"index": 1, "name": CV, "date": "14/2/2025", "selected": True}]
    pmp = {"fields": [{"label": "Do you have a PMP certification?", "type": "radio", "required": True,
                       "value": None, "options": ["Yes", "No"]}], "buttons": ["Atrás", "Revisar"]}
    review = review_step()
    review["review_text"] = f"Revisa tu solicitud\nCurrículum: {CV} (14/2/2025)"
    env["use"](FakeForm([contact_step(), step, questions_step(), pmp, review], start=3))
    r = server.linkedin_apply_prepare(JOB)
    first = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"}, continue_draft=True)
    assert first["status"] == "needs_answers" and first["step"] == 4
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000",
                                               **first["answers_draft"]})
    assert out["status"] == "resume_unverified" and out["selected"]["date"] == "14/2/2025"
    assert env["guard"].get("current_application")["draft_from_step"] == 3


def test_a_logged_job_is_not_opened_again(env):
    form = env["use"](FakeForm(STANDARD))
    env["guard"].record_submit({"job_id": JOB, "confirmed": False, "unexpected": True})
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "already_in_log" and "open_easy_apply" not in [a for a, _ in form.calls]
    assert server.linkedin_apply_prepare(JOB, allow_logged=True)["status"] == "too_soon"  # inside the gap of that send
    env["clock"].t += 181
    assert server.linkedin_apply_prepare(JOB, allow_logged=True)["status"] == "prepared"


def test_no_form_is_walked_when_no_send_is_left_today(env):
    form = env["use"](FakeForm(STANDARD))
    for i in range(10):
        env["guard"].record_submit({"job_id": str(4_000_000_000 + i)})
    assert server.linkedin_apply_prepare(JOB)["status"] == "daily_apply_limit"
    assert "open_easy_apply" not in [a for a, _ in form.calls]


def test_a_page_changed_outside_gets_new_keys(env):
    a = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": ""}], "buttons": ["Siguiente"]}
    b = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": ""},
                    {"label": "Más", "type": "text", "required": False, "value": ""}], "buttons": ["Atrás", "Revisar"]}
    form = env["use"](FakeForm([a, b, review_step()], one_page=True))
    r = server.linkedin_apply_prepare(JOB)
    first = key_of(r, "Comentarios")
    form.i = 1  # Allan pressed Siguiente in Safari
    out = server.linkedin_apply_fill_all(JOB, {first: "Disponible los martes"})
    assert out["status"] == "needs_answers" and out["new_step"] is True
    assert "modal_fill" not in [act for act, _ in form.calls]


def test_choosing_a_cv_by_hand_tool_changes_the_choice(env):
    form = env["use"](FakeForm([contact_step(), resume_step(selected=1), questions_step(), review_step()]))
    r = server.linkedin_apply_prepare(JOB, resume="CV-Allan Rosales.pdf")
    assert r["stopped_at"]["step"] == 3  # the preselected one was the chosen one
    env["guard"].set("current_application", None)
    form2 = env["use"](FakeForm([contact_step(), resume_step(selected=1), questions_step(), review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["step"] == 2 and r["resume"]["decision"] == "select"
    assert server.linkedin_apply_select_resume(index=1)["status"] == "selected"  # Allan prefers this one
    assert env["guard"].get("current_application")["resume_choice"] == "CV-Allan Rosales.pdf"
    out = server.linkedin_apply_fill_all(JOB, r["answers_draft"])
    assert [arg for act, arg in form2.calls if act == "select_resume"] == [{"name": None, "index": 1}]  # not undone
    assert out["status"] == "needs_answers" and out["step"] == 3
    assert env["guard"].get("current_application")["resume"]["name"] == "CV-Allan Rosales.pdf"


# --- third review (tanda 4) ---

class SpinnerKeepsFields(FakeForm):
    """After Siguiente the old step stays on screen for a while with its forward button gone, then moves on."""

    def __init__(self, *a, spin=3, **k):
        super().__init__(*a, **k)
        self.spin, self.left = spin, 0

    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next":
            out = super().js(win, idx, action, arg, select)
            self.left = self.spin
            self.spun_from = self.i - 1 if not self.errors else self.i
            return out
        if action == "modal_read" and self.left:
            self.calls.append((action, arg))
            self.left -= 1
            st = self.steps[self.spun_from]
            return {"open": True, "save_prompt": False, "success": False, "company": "Empresa Confidencial",
                    "fields": copy.deepcopy(st["fields"]), "buttons": ["Atrás", "Descartar"],
                    "button_kinds": ["back", "other"], "is_review": False, "errors": [],
                    "step": self.spun_from + 1, "steps": len(self.steps)}
        return super().js(win, idx, action, arg, select)


def test_a_spinner_is_not_taken_for_the_next_step(env):
    salary = {"fields": [{"label": SALARY, "type": "text", "required": True, "value": "3000"}],
              "buttons": ["Atrás", "Revisar"]}
    env["use"](SpinnerKeepsFields([contact_step(), salary, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["step"] == 2 and r["stopped_at"]["reason"] == "decision"
    assert key_of(r, SALARY) in r["to_ask"]


def test_an_answer_changed_after_the_review_is_not_ignored(env):
    env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    base = {**r["answers_draft"], key_of(r, SALARY): "3000"}
    assert server.linkedin_apply_fill_all(JOB, base)["status"] == "at_review"
    out = server.linkedin_apply_fill_all(JOB, {**base, key_of(r, SALARY): "3500"})
    assert out["status"] == "answers_not_applied" and out["keys"] == [key_of(r, SALARY)]


def test_old_tools_cannot_act_on_a_prepared_application(env):
    form = env["use"](FakeForm(STANDARD))
    server.linkedin_apply_prepare(JOB)
    assert server.linkedin_apply_start(JOB)["status"] == "application_in_progress"
    assert server.linkedin_apply_fill({SALARY: "1"})["status"] == "use_fill_all"
    assert server.linkedin_apply_next()["status"] == "use_fill_all"
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "not_at_review"
    assert "modal_fill" not in [a for a, _ in form.calls]


def test_the_old_next_tool_records_a_send_too(env):
    form = env["use"](FakeForm(STANDARD))
    form.submit_on_next = 0
    assert server.linkedin_apply_start(JOB)["open"] is True
    r = server.linkedin_apply_next()
    assert r["status"] == "unexpected_submit" and env["guard"].counters()["applications"] == 1
    assert env["guard"].paused_error() is not None


class LostAfterPress(FakeForm):
    """Siguiente sends, and every read right after fails (the page reloads): nobody saw the outcome."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.broken = 0

    def js(self, win, idx, action, arg=None, select=False):
        if action == "modal_read" and self.broken:
            self.calls.append((action, arg))
            self.broken -= 1
            return {"_error": True, "status": "bad_js_result", "message": "x"}
        out = super().js(win, idx, action, arg, select)
        if action == "click_next" and self.applied:
            self.broken = 3
        return out


def test_a_press_nobody_saw_is_resolved_on_the_next_call(env):
    form = env["use"](LostAfterPress(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    form.submit_on_next = 2
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out.get("press_unobserved") is True and env["guard"].applications() == []
    again = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert again["status"] == "unexpected_submit"
    assert env["guard"].counters()["applications"] == 1 and env["guard"].get("press_pending") is None


def test_a_change_on_a_multistep_review_blocks_the_submit(env):
    form = env["use"](FakeForm(STANDARD))
    form.allow_submit = True
    r = server.linkedin_apply_prepare(JOB)
    assert server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})["status"] == "at_review"
    form.steps[3]["review_text"] += f"\n{SALARY}\n99999"  # edited in Safari after Allan saw the review
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "review_changed"
    assert not form.applied


class LateBlink(FakeForm):
    def __init__(self, *a, at=4, **k):
        super().__init__(*a, **k)
        self.at, self.reads = at, None

    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next":
            self.reads = 0
        if action == "modal_read" and self.reads is not None:
            self.reads += 1
            if self.reads == self.at:
                self.calls.append((action, arg))
                return {"open": False, "save_prompt": False, "success": False}
        return super().js(win, idx, action, arg, select)


def test_a_late_blink_is_not_taken_for_a_send(env):
    env["use"](LateBlink(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "at_review" and env["guard"].applications() == []


def test_a_draft_of_a_form_without_cv_can_be_finished(env):
    review = review_step()
    review["review_text"] = "Revisa tu solicitud"
    env["use"](FakeForm([contact_step(), questions_step(), review], start=2))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"}, continue_draft=True)
    assert out["status"] == "at_review" and "unreviewed_steps" in out


def test_a_conditional_question_on_a_one_page_form_keeps_the_keys(env):
    page = {"fields": contact_step()["fields"] + [{"label": SALARY, "type": "text", "required": True, "value": ""}],
            "buttons": ["Enviar solicitud"], "review_text": "Revisa tu solicitud"}
    form = env["use"](FakeForm([page], one_page=True))
    r = server.linkedin_apply_prepare(JOB)
    form.steps[0]["fields"].append({"label": "Are you willing to commute?", "type": "radio", "required": True,
                                    "value": None, "options": ["Yes", "No"]})
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "needs_answers" and [q["label"] for q in out["questions"]] == ["Are you willing to commute?"]
    assert out["questions"][0]["key"].startswith(f"{JOB}:1|")


def test_a_step_with_nothing_on_it_says_so(env):
    empty = {"fields": [], "buttons": ["Atrás", "Cargar currículum", "Siguiente"]}
    env["use"](FakeForm([contact_step(), empty, review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "empty_step"


def test_a_slow_draft_is_still_a_draft(env):
    class SlowDraft(SlowOpen, NeverSettles):
        pass
    env["use"](SlowDraft(STANDARD, start=3, opens_after=3))
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "draft_detected"


def test_an_untracked_form_can_still_be_closed(env):
    form = env["use"](FakeForm(STANDARD))
    form.i = 0  # open in the work tab, but nothing on record
    real = form.js
    form.js = lambda win, idx, action, arg=None, select=False: (
        (setattr(form, "i", None) or {"status": "saved"}) if action == "close_modal" else
        real(win, idx, action, arg, select))
    env["monkeypatch"].setattr(server, "_js", form.js)
    r = server.linkedin_apply_close()
    assert r["still_open"] is False


def test_a_same_day_duplicate_upload_is_not_verified(env):
    server.resume_ledger.add(CV, "6/10/2026", "ff" * 32)
    step = resume_step()
    step["fields"][0]["resumes"][0]["selected"] = True
    env["use"](FakeForm([contact_step(), step, questions_step(), review_step()], start=3))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"}, continue_draft=True)
    assert out["status"] == "resume_unverified"


def test_prepare_opens_nothing_inside_the_gap_after_a_send(env):
    form = env["use"](FakeForm(STANDARD))
    env["guard"].record_submit({"job_id": "4382109958"})
    r = server.linkedin_apply_prepare(JOB)
    assert r["status"] == "too_soon" and r["retry_after_s"] > 0
    assert "open_easy_apply" not in [a for a, _ in form.calls] and env["guard"].get("current_application") is None
    env["clock"].t += 181
    out = server.linkedin_apply_prepare(JOB)
    assert out["status"] == "prepared" and out["stopped_at"]["step"] == 3


def test_fill_all_waits_out_a_gap_that_starts_after_prepare(env):
    form = env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    env["guard"].record_submit({"job_id": "4382109958"})  # something else was sent in the meantime
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "too_soon" and out["retry_after_s"] > 0
    advanced = len(form.advanced)
    env["clock"].t += 181
    again = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert again["status"] == "at_review" and len(form.advanced) > advanced



# --- fourth review (tanda 4) ---

class AppearsAtClick(FakeForm):
    """A prefilled question shows up on step 3 between planning and the click (server-driven UI)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.done = False

    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_next" and self.i == 2 and not self.done:
            self.done = True
            self.steps[2]["fields"].append({"label": "Expected monthly salary in MXN", "type": "text",
                                            "required": False, "value": "50000"})
        return super().js(win, idx, action, arg, select)


def test_a_question_that_appears_at_the_click_is_not_pressed_through(env):
    form = env["use"](AppearsAtClick(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    assert out["status"] == "needs_answers"
    assert [q["label"] for q in out["questions"]] == ["Expected monthly salary in MXN"]
    assert form.i == 2  # still on the questions step


class SentButNoReply(FakeForm):
    def js(self, win, idx, action, arg=None, select=False):
        if action == "click_submit":
            self.calls.append((action, arg))
            self.i, self.applied = None, True
            return {"_error": True, "status": "timeout", "message": "osascript exceeded 60s"}
        return super().js(win, idx, action, arg, select)


def test_an_enviar_nobody_saw_is_recorded_not_repeated(env):
    form = env["use"](SentButNoReply(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    first = server.linkedin_apply_submit(JOB, confirm=True)
    assert first.get("press_unobserved") is True and env["guard"].applications() == []
    again = server.linkedin_apply_submit(JOB, confirm=True)
    assert again["status"] == "unexpected_submit"
    assert len([a for a, _ in form.calls if a == "click_submit"]) == 1  # never clicked twice
    assert env["guard"].counters()["applications"] == 1


def test_an_enviar_in_flight_is_not_clicked_again(env):
    class InFlight(FakeForm):
        def js(self, win, idx, action, arg=None, select=False):
            if action == "click_submit":
                self.calls.append((action, arg))
                return {"_error": True, "status": "timeout", "message": "x"}  # form still on the review
            return super().js(win, idx, action, arg, select)
    form = env["use"](InFlight(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    server.linkedin_apply_submit(JOB, confirm=True)
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "submit_unverified"
    assert len([a for a, _ in form.calls if a == "click_submit"]) == 1


def test_a_confirmation_on_screen_is_recorded_by_submit_and_close(env):
    class Confirmed(FakeForm):
        def read(self):
            if self.applied:
                return {"open": False, "save_prompt": False, "success": True, "success_text": "Se envió tu solicitud"}
            return super().read()
    for tool in ("submit", "close"):
        env["guard"].set("current_application", None)
        env["guard"].resume()
        env["clock"].t += 181  # past the minimum gap after the previous (recorded) send
        form = env["use"](Confirmed(STANDARD))
        r = server.linkedin_apply_prepare(JOB, allow_logged=True)
        server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
        form.applied = True  # Allan pressed Enviar himself in Safari
        out = server.linkedin_apply_submit(JOB, confirm=True) if tool == "submit" else server.linkedin_apply_close()
        assert out["status"] == "unexpected_submit", tool
    assert env["guard"].counters()["applications"] == 2


def test_a_pending_press_on_a_lost_tab_is_counted(env):
    form = env["use"](FakeForm(STANDARD))
    server.linkedin_apply_prepare(JOB)
    env["guard"].set("press_pending", {"job_id": JOB, "where": "fill_all", "ts": "x"})
    env["guard"].set("work_tab", {"id": "7:2", "window_id": 7, "job_id": "4382109958"})
    out = server.linkedin_apply_close()
    assert out["status"] == "dialog_vanished" and env["guard"].counters()["applications"] == 1


def test_an_unreadable_page_or_a_save_prompt_is_not_a_send(env):
    class Unreadable(FakeForm):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.off = False

        def js(self, win, idx, action, arg=None, select=False):
            if self.off and action == "modal_read":
                return {"_error": True, "status": "js_from_apple_events_disabled", "message": "x"}
            return super().js(win, idx, action, arg, select)
    form = env["use"](Unreadable(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    env["guard"].set("press_pending", {"job_id": JOB, "where": "fill_all", "ts": "x"})
    form.off = True
    out = server.linkedin_apply_fill_all(JOB, r["answers_draft"])
    assert out["status"] == "js_from_apple_events_disabled" and env["guard"].applications() == []
    assert env["guard"].get("press_pending") is not None
    form.off = False
    form.steps[2]["buttons"] = ["Atrás", "Revisar"]
    real = form.read
    form.read = lambda: {"open": False, "save_prompt": True, "success": False}
    out = server.linkedin_apply_close(save_draft=False)
    assert env["guard"].applications() == [] and env["guard"].get("press_pending") is None
    form.read = real


def test_the_old_next_tool_says_when_it_did_not_advance(env):
    env["use"](FakeForm(STANDARD))
    server.linkedin_apply_start(JOB)
    assert server.linkedin_apply_next()["advanced"] is True
    assert server.linkedin_apply_next()["advanced"] is True
    stuck = server.linkedin_apply_next()  # questions empty: LinkedIn refuses
    assert stuck["advanced"] is False and stuck["status"] == "form_has_errors" and stuck["pressed"] == "Siguiente"


def test_an_empty_step_passes_only_with_allans_ok(env):
    empty = {"fields": [], "buttons": ["Atrás", "Siguiente"]}
    env["use"](FakeForm([contact_step(), resume_step(), empty, questions_step(), review_step()]))
    r = server.linkedin_apply_prepare(JOB)
    assert r["stopped_at"]["reason"] == "empty_step"
    assert server.linkedin_apply_fill_all(JOB, r["answers_draft"])["status"] == "empty_step"
    out = server.linkedin_apply_fill_all(JOB, r["answers_draft"], pass_empty_step=True)
    assert out["status"] == "needs_answers" and out["step"] == 4
    salary = next(q["key"] for q in out["questions"] if q["label"] == SALARY)
    done = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], **out["answers_draft"], salary: "3000"})
    assert done["status"] == "at_review"


def test_going_back_on_a_counterless_form_keeps_the_page_number(env):
    a = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": ""}], "buttons": ["Siguiente"]}
    b = {"fields": [{"label": SALARY, "type": "text", "required": True, "value": ""}], "buttons": ["Atrás", "Revisar"]}
    form = env["use"](FakeForm([a, b, review_step()], one_page=True))
    r = server.linkedin_apply_prepare(JOB)
    k1 = key_of(r, "Comentarios")
    out = server.linkedin_apply_fill_all(JOB, {k1: "Martes"})
    k2 = out["questions"][0]["key"]
    assert server.linkedin_apply_fill_all(JOB, {k1: "Martes", k2: "3000"})["status"] == "at_review"
    form.i = 1  # Allan goes back one page in Safari
    again = server.linkedin_apply_fill_all(JOB, {k1: "Martes", k2: "3500"})
    assert again["status"] == "at_review"  # same page number: the new answer is filled, nothing re-asked
    assert form.steps[1]["fields"][0]["value"] == "3500"


def test_a_send_by_prepare_logs_the_page_it_pressed(env):
    form = env["use"](FakeForm(STANDARD))
    form.submit_on_next = 0
    server.linkedin_apply_prepare(JOB)
    logged = env["guard"].applications()[0]["answers"]
    assert logged["Mobile phone number"] == "57030067"


def test_a_cv_key_in_the_answers_does_not_block_the_review(env):
    env["use"](FakeForm(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    cv_key = r["resume"]["key"]
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000", cv_key: CV})
    assert out["status"] == "at_review"


def test_a_cv_named_in_a_draft_review_must_be_readable(env):
    step = resume_step()
    step["fields"][0]["resumes"] = [{"index": 0, "name": CV, "date": "6/10/2026", "selected": False},
                                    {"index": 1, "name": CV, "date": "14/2/2025", "selected": True}]
    review = review_step()
    review["review_text"] = f"Revisa tu solicitud\nCurrículum\n{CV}\nCargado el 14/2/2025"
    env["use"](FakeForm([contact_step(), step, questions_step(), review], start=3))
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"}, continue_draft=True)
    assert out["status"] == "resume_unknown"


# --- fifth review (tanda 4) ---

def test_an_unverified_enviar_survives_fill_all_and_close(env):
    class InFlight(FakeForm):
        def js(self, win, idx, action, arg=None, select=False):
            if action == "click_submit":
                self.calls.append((action, arg))
                return {"_error": True, "status": "timeout", "message": "x"}  # the review stays on screen
            return super().js(win, idx, action, arg, select)
    form = env["use"](InFlight(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    answers_ = {**r["answers_draft"], key_of(r, SALARY): "3000"}
    server.linkedin_apply_fill_all(JOB, answers_)
    server.linkedin_apply_submit(JOB, confirm=True)
    assert server.linkedin_apply_fill_all(JOB, answers_)["status"] == "submit_unverified"
    assert server.linkedin_apply_close()["status"] == "submit_unverified"
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "submit_unverified"
    assert len([a for a, _ in form.calls if a == "click_submit"]) == 1
    form.i, form.applied = None, True  # the in-flight Enviar lands later
    out = server.linkedin_apply_close()
    assert out["status"] == "unexpected_submit" and env["guard"].counters()["applications"] == 1


def test_not_sent_lets_allan_close_after_checking(env):
    class InFlight(FakeForm):
        def js(self, win, idx, action, arg=None, select=False):
            if action == "click_submit":
                return {"_error": True, "status": "timeout", "message": "x"}
            return super().js(win, idx, action, arg, select)
    env["use"](InFlight(STANDARD))
    r = server.linkedin_apply_prepare(JOB)
    server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"})
    server.linkedin_apply_submit(JOB, confirm=True)
    out = server.linkedin_apply_close(save_draft=True, not_sent=True)
    assert out["still_open"] is False and env["guard"].get("press_pending") is None
    assert env["guard"].applications() == []


def test_a_cv_chosen_after_the_cv_step_is_not_silently_ignored(env):
    form = env["use"](FakeForm(STANDARD))
    form.allow_submit = True
    r = server.linkedin_apply_prepare(JOB)
    out = server.linkedin_apply_fill_all(JOB, {**r["answers_draft"], key_of(r, SALARY): "3000"},
                                         resume="CV-Allan Rosales.pdf")
    assert out["status"] == "resume_mismatch" and "Atrás" in out["message"]
    assert server.linkedin_apply_submit(JOB, confirm=True)["status"] == "not_at_review"
    assert not form.applied


def test_volver_on_the_first_page_means_a_draft(env):
    a = {"fields": [{"label": "Comentarios", "type": "text", "required": True, "value": "hola"}],
         "buttons": ["Volver", "Revisar"]}
    env["use"](FakeForm([a, review_step()], one_page=True))
    assert server.linkedin_apply_prepare(JOB)["status"] == "draft_detected"
