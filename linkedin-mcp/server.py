"""linkedin-mcp: apply to LinkedIn jobs ("Solicitud sencilla") through the user's own Safari session.

Design (see README.md):
- Drives the real Safari over AppleScript; the user signs in himself. No login, no messages, no
  invitations, no profile edits, no bulk scraping — those tools simply don't exist.
- Pacing and caps live in ``guard.py``. Any LinkedIn verification/limit page pauses everything
  until the user resolves it by hand and says so in the chat.
- ``linkedin_apply_submit`` needs ``confirm=True``, which Claude passes only after an explicit
  "sí" from the user for that specific job.
- Only acts on linkedin.com tabs and only navigates to URLs it builds (``/jobs/view/<id>/``).
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional, Union

from mcp.server.fastmcp import FastMCP

import answers
import config
import external
import flow
import registro
import safari_bridge as sb
import triage
from guard import Guard, detect_checkpoint
from jobcache import JobCache
from resumes import ResumeLedger, resume_hash

HERE = Path(__file__).resolve().parent
_JS = (HERE / "linkedin.js").read_text(encoding="utf-8")
_LINKEDIN_RE = re.compile(r"^https://([a-z0-9-]+\.)?linkedin\.com/", re.I)
_LIST_URL_RE = re.compile(r"linkedin\.com/jobs/(search-results|search|collections)/", re.I)
_JOB_ID_RE = re.compile(r"\d{6,12}")
_JOB_URL = "https://www.linkedin.com/jobs/view/{}/"
_UPLOAD_MAX_BYTES = 2 * 1024 * 1024  # LinkedIn's own resume limit ("inferior a 2 MB")
_UPLOAD_EXTS = {".pdf": "application/pdf", ".doc": "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_UPLOAD_CHUNK = 200_000  # base64 chars per osascript call (argv stays well under ARG_MAX)
# linkedin.js actions that click or type in the page: each waits the fixed dialog gap (guard.py).
_DIALOG_ACTIONS = {"open_easy_apply", "modal_fill", "typeahead_pick", "modal_click", "click_next", "click_submit",
                   "set_follow", "select_resume", "upload_begin", "file_commit", "close_modal"}

mcp = FastMCP("linkedin-mcp")
guard = Guard()
jobs = JobCache(guard.dir)
resume_ledger = ResumeLedger(guard.dir)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _locked(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Run a tool under the guard's lock so two operations never touch LinkedIn at once."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        with guard.lock() as busy:
            if busy:
                return busy
            return fn(*args, **kwargs)
    return wrapper


def _is_linkedin(url: str) -> bool:
    return bool(_LINKEDIN_RE.match(url or ""))


def _linkedin_tabs() -> dict:
    """Only linkedin.com tabs: Safari is shared, other tabs are none of this MCP's business."""
    if not sb.safari_running():
        return sb.err("not_running", "Safari no está abierto.")
    r = sb.list_tabs()
    if r.get("_error"):
        return r
    return {"value": [t for t in r["value"] if _is_linkedin(t["url"])]}


def _tab(tab_id: str) -> tuple[Optional[tuple[int, int]], Optional[dict]]:
    parsed = sb.parse_tab_id(tab_id)
    if parsed is None:
        return None, sb.err("bad_tab_id", f"tab_id debe ser '<windowId>:<tabIndex>', llegó {tab_id!r}.")
    meta = sb.tab_meta(*parsed)
    if meta.get("_error"):
        return None, meta
    if not _is_linkedin(meta["url"]):
        return None, sb.err("not_linkedin", "Esa pestaña no es de linkedin.com; este MCP solo actúa en LinkedIn.",
                            tab_id=tab_id)
    return parsed, None


def _js(win: int, idx: int, action: str, arg: Any = None, select: bool = False) -> dict:
    """Run one ``linkedin.js`` action and decode its JSON. Clicks and typing keep the fixed dialog gap."""
    if action in _DIALOG_ACTIONS:
        guard.before_dialog_action()
    if select:
        # Pages ignore clicks while their tab is hidden, so make it the window's current tab.
        sel = sb.select_tab(win, idx)
        if sel.get("_error"):
            return sel
        time.sleep(0.3)
    js = f"({_JS})({json.dumps(action)},{json.dumps(arg, ensure_ascii=True)})"
    r = sb.run_js(win, idx, js, timeout=60)
    if r.get("_error"):
        return r
    try:
        data = json.loads(r["out"])
    except ValueError:
        return sb.err("bad_js_result", "La página no devolvió JSON (¿sigue cargando?).", raw=r["out"][:300])
    if isinstance(data, dict) and data.get("status") == "js_error":
        return sb.err("js_error", data.get("message", ""))
    return data


def _checkpoint(win: int, idx: int) -> Optional[dict]:
    """Pause everything if the tab shows a verification, sign-in wall or limit notice."""
    st = _js(win, idx, "page_state")
    if st.get("_error"):
        return None
    reason = detect_checkpoint(st.get("url", ""), st.get("headings"), st.get("alerts"), st.get("captcha_frame", False))
    if reason:
        return guard.pause(reason, st.get("url", ""))
    return None


def _poll(fn: Callable[[], dict], ok: Callable[[dict], bool], timeout: float, step: float = 0.8) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = fn()
        if not last.get("_error") and ok(last):
            return last
        time.sleep(step)
    return last


def _work_tab() -> tuple[Optional[tuple[int, int]], Optional[dict]]:
    """The tab this MCP opened for job pages, re-found by its job URL because tab indexes shift."""
    saved = guard.get("work_tab") or {}
    jid = saved.get("job_id")
    if not jid:
        return None, None
    tabs = _linkedin_tabs()
    if tabs.get("_error"):
        return None, tabs
    hits = [t for t in tabs["value"] if f"/jobs/view/{jid}" in t["url"]]
    hits.sort(key=lambda t: t["id"] != saved.get("id"))  # prefer the id we stored
    if not hits:
        return None, None
    t = hits[0]
    if t["id"] != saved.get("id"):
        guard.set("work_tab", {**saved, "id": t["id"], "window_id": t["window_id"]})
    return (t["window_id"], t["tab_index"]), None


def _current_app_tab() -> tuple[Optional[tuple[int, int]], Optional[dict], dict]:
    app = guard.get("current_application") or {}
    if not app:
        return None, sb.err("no_application", "No hay una solicitud abierta. Usa linkedin_apply_start."), app
    tab_job = (guard.get("work_tab") or {}).get("job_id")
    if tab_job != app.get("job_id"):
        return None, sb.err("work_tab_mismatch", f"La solicitud abierta es de la vacante {app.get('job_id')}, pero la "
                                                 f"pestaña de trabajo está en {tab_job}. Ciérrala con "
                                                 "linkedin_apply_close antes de seguir.",
                            open_job_id=app.get("job_id"), work_tab_job_id=tab_job), app
    pos, bad = _work_tab()
    if bad:
        return None, bad, app
    if not pos:
        return None, sb.err("work_tab_lost", "No encuentro la pestaña de la vacante (¿se cerró?). "
                                             "Ábrela de nuevo con linkedin_get_job(job_id, refresh=True)."), app
    return pos, None, app


def _matches(field: dict, want: Any) -> bool:
    val = field.get("value")
    if field.get("type") == "checkbox":
        wants = want if isinstance(want, list) else ([] if want is False else [want])
        if want is True:
            return bool(val)
        return sorted(sb.norm(v) for v in (val or [])) == sorted(sb.norm(w) for w in wants)
    if field.get("type") in ("select", "radio", "typeahead"):
        return bool(val) and (sb.norm(val) == sb.norm(want) or sb.norm(want) in sb.norm(val))
    return str(val if val is not None else "") == str(want if want is not None else "")


def _dialog_ready(s: dict) -> bool:
    """The dialog shell renders before its content; wait for the step counter or a nav button."""
    return bool(s.get("open")) and (s.get("step") is not None or len(s.get("buttons") or []) > 1)


_REVIEW_RESUME_RE = re.compile(r"^Currículum: (?!\(no se pudo)(.+?)(?: \((\d{1,2}/\d{1,2}/\d{4})\))?(?: \[lista de \d+ CV omitida\])?$",
                               re.M)


def _selected_resume(state: dict) -> Optional[dict]:
    """``{name, date}`` of the resume the dialog shows as chosen: the resume field, else the review summary."""
    res = next((f for f in state.get("fields", []) if f.get("type") == "resume"), None)
    if res:
        sel = next((r for r in res.get("resumes", []) if r.get("selected")), None)
        return {"name": sel["name"], "date": sel.get("date") or ""} if sel else None
    m = _REVIEW_RESUME_RE.search(state.get("review_text") or "")
    return {"name": m.group(1), "date": m.group(2) or ""} if m else None


def _same_company(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = sb.norm(a), sb.norm(b)
    return not na or not nb or na in nb or nb in na


def _resume_record(app: dict, state: Optional[dict] = None) -> dict:
    """The CV that went out: name, LinkedIn date and SHA-256 (with where the hash comes from)."""
    res = app.get("resume") or (_selected_resume(state) if state else None) or {}
    if not res.get("name"):
        return {}
    out = {"name": res["name"], "date": res.get("date") or ""}
    if res.get("sha256"):
        out.update(sha256=res["sha256"], sha256_source="subido en esta solicitud")
    else:
        out.update(resume_hash(res["name"], res.get("date"), resume_ledger, config.cv_dir()))
    return out


def _enrich(app: dict, state: Optional[dict] = None) -> dict:
    """Answers (label → value) and CV for a send's record. Never raises: a send is logged even if this part fails."""
    try:
        return {"answers": registro.answers_by_label(app.get("answers_filled") or {}),
                "resume": _resume_record(app, state)}
    except Exception as e:  # noqa: BLE001
        return {"answers": {}, "resume": {}, "enrich_error": f"{type(e).__name__}: {e}"}


def _log_send(entry: dict) -> tuple[dict, dict]:
    """Count and log a send (applications.jsonl), then add its rows to both Markdown logs. A failure in the
    Markdown part never undoes the send: it comes back as ``registro_error``."""
    entry = guard.record_submit(entry)
    try:
        r = registro.sync([entry], config.postulaciones_md(), config.perfil_md())
        return entry, {"registro": r["added"]}
    except Exception as e:  # noqa: BLE001
        return entry, {"registro_error": f"{type(e).__name__}: {e}. Corre `cli.py registro-sync` cuando se arregle."}


def _find_field(fields: list[dict], key: str) -> Optional[dict]:
    k = sb.norm(key)
    for test in (lambda l: l == k, lambda l: l.startswith(k), lambda l: k and k in l):
        hits = [f for f in fields if test(sb.norm(f.get("label")))]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None
    return None


# -----------------------------------------------------------------------------
# Status and reading
# -----------------------------------------------------------------------------


@mcp.tool()
def linkedin_status() -> dict:
    """First call of a session: Safari, LinkedIn tabs, sign-in, JavaScript, today's counters and any pause.

    Lists only linkedin.com tabs. If the page shows a verification or a limit notice,
    this call also turns on the pause.
    """
    tabs = _linkedin_tabs()
    if tabs.get("_error"):
        return {**tabs, "counters": guard.counters()}
    out: dict[str, Any] = {"safari_running": True, "linkedin_tabs": tabs["value"], "js_enabled": None,
                           "logged_in": None}
    if tabs["value"]:
        t = tabs["value"][0]
        st = _js(t["window_id"], t["tab_index"], "page_state")
        if st.get("_error"):
            out["js_enabled"] = st.get("status") != "js_from_apple_events_disabled"
            out["js_error"] = st
        else:
            out["js_enabled"] = True
            out["logged_in"] = st.get("logged_in")
            reason = detect_checkpoint(st.get("url", ""), st.get("headings"), st.get("alerts"),
                                       st.get("captcha_frame", False))
            if reason:
                guard.pause(reason, st.get("url", ""))
    else:
        out["hint"] = "No hay pestañas de LinkedIn abiertas: Allan abre su búsqueda de empleos en Safari."
    out["counters"] = guard.counters()
    out["work_tab"] = guard.get("work_tab")
    out["current_application"] = guard.get("current_application")
    return out


@mcp.tool()
@_locked
def linkedin_list_jobs(tab_id: Optional[str] = None, page: Optional[Union[int, str]] = None) -> dict:
    """Read the job cards of a LinkedIn job-search tab (the one Allan opened).

    Each job: ``job_id``, ``title``, ``company``, ``location``, ``posted``, ``insight`` and the flags
    ``applied``, ``saved``, ``viewed``, ``easy_apply``, ``actively_reviewing``, ``early_applicant``,
    ``verified``. ``page`` (a number or ``"next"``) changes the results page first; that counts as a
    navigation for pacing. Without ``tab_id`` it uses the first job-search tab.
    """
    bad = guard.paused_error()
    if bad:
        return bad
    if tab_id:
        pos, bad = _tab(tab_id)
        if bad:
            return bad
    else:
        tabs = _linkedin_tabs()
        if tabs.get("_error"):
            return tabs
        lists = [t for t in tabs["value"] if _LIST_URL_RE.search(t["url"])]
        if not lists:
            return sb.err("no_list_tab", "No hay una pestaña con la búsqueda de empleos de LinkedIn.")
        pos = (lists[0]["window_id"], lists[0]["tab_index"])
        tab_id = lists[0]["id"]
    win, idx = pos
    if page is not None:
        bad = guard.before_navigation(counts_as_view=False)
        if bad:
            return bad
        r = _js(win, idx, "goto_page", page if page == "next" else int(page), select=True)
        guard.record_navigation(counts_as_view=False)
        if r.get("_error") or r.get("status") != "clicked":
            return r if r.get("_error") else sb.err(r.get("status", "page_failed"), "No encontré esa página.", page=page)
        time.sleep(2.5)
    want_page = None if page in (None, "next") else int(page)
    res = _poll(lambda: _js(win, idx, "list_jobs"),
                lambda d: d.get("count", 0) > 0 and (want_page is None or d.get("page") == want_page), timeout=12)
    stop = _checkpoint(win, idx)
    if stop:
        return stop
    if res.get("_error"):
        return res
    logged = {a.get("job_id") for a in guard.applications()}
    for j in res.get("jobs", []):
        j["in_local_log"] = j["job_id"] in logged
    res["tab_id"] = tab_id
    return res


@mcp.tool()
@_locked
def linkedin_triage(tab_id: Optional[str] = None, page: Optional[Union[int, str]] = None) -> dict:
    """Read a job-search tab and score every card against Allan's verified profile. Opens no job (no views).

    Deterministic, with the rules in the skill's ``references/triage.json``: each positive criterion quotes text
    that must exist in the Experiencia, Docencia or Formación sections of perfil.md (one whose quote is missing,
    or that is malformed, is skipped and listed in ``skipped_rules``). Per job: ``encaje`` alto/medio/bajo with
    ``puntaje`` and ``motivos``; ``banderas`` for experience with no evidence (banca, telco/NOC, redes/SOC/SIEM,
    programador principal, ERP distinto de SAP u Odoo, eléctrico, cloud, obra civil, certificaciones sin
    verificar, educación virtual); ``basis`` = ``titulo`` (fit ``encaje_provisional``) or ``descripcion`` (a
    fresh cached page, which adds at most 2 points); ``tipo`` from the card (``tipo_segun: tarjeta``) or the
    cached page; ``modalidad`` and ``estado`` (nueva, vista, guardada, cerrada, ya solicitada…). A flag in the
    title or company caps "alto" at "medio"; one only in the description is just shown. Sorted best first,
    flagged after unflagged, closed and applied last. ``page`` changes the results page first (a navigation for
    pacing, not a view).
    """
    try:
        rules_data = json.loads(config.triage_json().read_text(encoding="utf-8"))
        perfil_text = config.perfil_md().read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        return sb.err("triage_rules_unreadable", f"No pude leer triage.json o perfil.md: {e}")
    lst = linkedin_list_jobs(tab_id, page)
    if lst.get("_error"):
        return lst
    try:
        rules, skipped = triage.load_rules(rules_data, perfil_text)
        rows = triage.triage(lst.get("jobs", []), rules, jobs.fresh())
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        return sb.err("triage_rules_invalid", f"triage.json tiene una regla mal formada: {type(e).__name__}: {e}")
    return {"tab_id": lst.get("tab_id"), "page": lst.get("page"), "pages": lst.get("pages"),
            "has_next": lst.get("has_next"), "total_results": lst.get("total_results"), "count": len(rows),
            "jobs": rows, "skipped_rules": skipped,
            "note": "Encaje provisional = solo por el título; el tipo «según tarjeta» puede cambiar al abrir la "
                    "vacante (cbc, 06/10/2026). Las banderas no descartan: se muestran para que Allan decida."}


def _job_result(job_id: str, row: dict, from_cache: bool) -> dict:
    """A cached job row as the tool returns it: plus where it came from, external_kind and today's counters."""
    d = dict(row["data"])
    kind = external.classify(d.get("external_url") or None, d.get("ats") or None) or {}
    d.update(external_kind=kind.get("external_kind"), external_site=kind.get("site"),
             account_hint=kind.get("account_hint"), clean_url=kind.get("clean_url"))
    d["from_cache"] = from_cache
    d["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(row["fetched_at"]))
    d["on_work_tab"] = (guard.get("work_tab") or {}).get("job_id") == job_id
    d["in_local_log"] = any(a.get("job_id") == job_id for a in guard.applications())
    d["counters"] = {k: v for k, v in guard.counters().items() if k in ("job_views", "job_views_left")}
    app = guard.get("current_application") or {}
    if app and app.get("job_id") != job_id:
        d["application_in_progress"] = {"job_id": app.get("job_id"), "title": app.get("title"),
                                        "message": "Sigue abierta la solicitud de otra vacante: las tools apply_* "
                                                   "actúan sobre esa hasta que se cierre con linkedin_apply_close."}
    return d


def _job_read_ok(d: dict, job_id: str) -> bool:
    return d.get("job_id") == job_id and bool(d.get("title")) and d.get("apply_type") != "unknown"


@mcp.tool()
@_locked
def linkedin_get_job(job_id: str, refresh: bool = False) -> dict:
    """Read a job: from the local cache (24 h, no view spent) or by opening
    ``https://www.linkedin.com/jobs/view/<job_id>/`` in this MCP's own tab.

    Returns title, company, ``meta`` (location · posted · applicants), ``chips`` (workplace, job type),
    ``apply_type`` (``easy_apply`` | ``external`` | ``ats_continue`` | ``applied`` | ``closed`` | ``unknown``),
    ``external_url`` for external applications, ``ats``/``apply_url`` for ``ats_continue`` (a "Continuar"
    link to the company's ATS that Allan presses himself), ``description`` and ``company_about``, plus
    ``external_kind`` (``google_forms`` | ``microsoft_forms`` | ``ats:<name>`` | ``job_board`` |
    ``company_site``), ``account_hint`` (si/no/a_veces/desconocido: a hint, not a check) and ``clean_url``.

    ``from_cache: true`` means no navigation happened; ``on_work_tab`` says whether the MCP's tab is on this
    job. Acting on the job (linkedin_apply_start) needs it there: use ``refresh=True``. Opening the page
    counts as one job view (daily cap) and respects the minimum gap between navigations.
    """
    if not _JOB_ID_RE.fullmatch(str(job_id)):
        return sb.err("bad_job_id", "job_id debe ser el número de la vacante (p. ej. 4474644406).")
    job_id = str(job_id)
    if not refresh:
        row = jobs.get(job_id)
        if row:
            return _job_result(job_id, row, from_cache=True)
    app = guard.get("current_application") or {}
    if app:  # navigating the work tab would destroy that form (and a reload too, for the same job)
        return sb.err("application_in_progress", f"Hay una solicitud abierta (vacante {app.get('job_id')}). Ciérrala "
                                                 "con linkedin_apply_close (guarda borrador por defecto) antes de "
                                                 "abrir o recargar una vacante.", open_job_id=app.get("job_id"))
    bad = guard.before_navigation(counts_as_view=True)
    if bad:
        return bad
    url = _JOB_URL.format(job_id)
    saved = guard.get("work_tab") or {}
    pos, bad = _work_tab()
    if bad:
        return bad
    if pos:
        r = sb.navigate(pos[0], pos[1], url)
        if r.get("_error"):
            return r
    else:
        tabs = _linkedin_tabs()
        if tabs.get("_error"):
            return tabs
        win = saved.get("window_id") or (tabs["value"][0]["window_id"] if tabs["value"] else 0)
        r = sb.new_tab(url, win)
        if r.get("_error") and win:
            r = sb.new_tab(url, 0)
        if r.get("_error"):
            return r
        pos = sb.parse_tab_id(r["out"])
    guard.record_navigation(counts_as_view=True)
    guard.set("work_tab", {"id": f"{pos[0]}:{pos[1]}", "window_id": pos[0], "job_id": job_id})
    load = sb.wait_for_load(pos[0], pos[1], timeout=30)
    if load.get("_error"):
        return load
    time.sleep(1.5)  # client-side render after readyState
    stop = _checkpoint(*pos)
    if stop:
        return stop
    d = _poll(lambda: _js(pos[0], pos[1], "job_detail"), lambda x: _job_read_ok(x, job_id), timeout=12)
    if d.get("_error"):
        return d
    if _job_read_ok(d, job_id) and not d.get("description"):  # the description renders after the title (07/10/2026)
        later = _poll(lambda: _js(pos[0], pos[1], "job_detail"),
                      lambda x: _job_read_ok(x, job_id) and bool(x.get("description")), timeout=6)
        if _job_read_ok(later, job_id):
            d = later
    if len(d.get("description", "")) > 12000:
        d["description"] = d["description"][:12000] + " …[recortado]"
    if _job_read_ok(d, job_id):
        out = _job_result(job_id, jobs.put(job_id, d), from_cache=False)
    else:  # never cache a page that didn't show this job (redirect, still loading, unknown layout)
        jobs.invalidate(job_id)
        out = _job_result(job_id, {"fetched_at": time.time(), "data": d}, from_cache=False)
        out["incomplete_read"] = True
        out["message"] = ("La página no mostró esta vacante completa (¿redirigió o seguía cargando?). No se guardó en "
                          "caché; revisa la pestaña o vuelve a intentar con refresh=True.")
    out["tab_id"] = f"{pos[0]}:{pos[1]}"
    return out


# -----------------------------------------------------------------------------
# Easy Apply
# -----------------------------------------------------------------------------


@mcp.tool()
@_locked
def linkedin_apply_start(job_id: str) -> dict:
    """Step-by-step path: open the "Solicitud sencilla" (Easy Apply) dialog of a job opened with linkedin_get_job.

    Returns the first step (see linkedin_apply_read). For external, closed or already-applied jobs it
    returns that status instead and opens nothing. Refuses while another application is open
    (``application_in_progress``). The main path is linkedin_apply_prepare + linkedin_apply_fill_all.
    """
    bad = guard.paused_error()
    if bad:
        return bad
    if guard.get("current_application"):
        return sb.err("application_in_progress", "Ya hay una solicitud abierta; sigue con ella o ciérrala con "
                                                 "linkedin_apply_close.",
                      open_job_id=(guard.get("current_application") or {}).get("job_id"))
    saved = guard.get("work_tab") or {}
    if saved.get("job_id") != str(job_id):
        return sb.err("open_job_first", "La pestaña de trabajo no está en esta vacante: ábrela con "
                                        "linkedin_get_job(job_id, refresh=True).")
    pos, bad = _work_tab()
    if bad:
        return bad
    if not pos:
        return sb.err("work_tab_lost", "No encuentro la pestaña de la vacante. Ábrela con "
                                       "linkedin_get_job(job_id, refresh=True).")
    d = _js(*pos, "job_detail")
    if d.get("_error"):
        return d
    if d.get("apply_type") != "easy_apply":
        message = "Esta vacante no se postula con Solicitud sencilla desde aquí."
        if d.get("apply_type") == "ats_continue":
            message = (f"Se postula por el ATS de la empresa ({d.get('ats') or 'sin nombre'}) con el enlace "
                       "\"Continuar\". Pulsarlo cuenta como envío, así que lo pulsa Allan en Safari.")
        return {"status": d.get("apply_type"), "job_id": job_id, "title": d.get("title"),
                "company": d.get("company"), "external_url": d.get("external_url"),
                "ats": d.get("ats"), "apply_url": d.get("apply_url"),
                "applied_status": d.get("applied_status"), "message": message}
    state = _poll(lambda: _js(*pos, "modal_read"), _dialog_ready, timeout=3)
    if not state.get("open"):
        r = _js(*pos, "open_easy_apply", select=True)
        if r.get("_error") or r.get("status") != "clicked":
            return r if r.get("_error") else sb.err(r.get("status", "open_failed"), "No pude abrir la Solicitud sencilla.")
        state = _poll(lambda: _js(*pos, "modal_read"), _dialog_ready, timeout=15)
    stop = _checkpoint(*pos)
    if stop:
        return stop
    if not state.get("open"):
        return sb.err("dialog_not_open", "El formulario de Solicitud sencilla no se abrió.", state=state)
    guard.set("current_application", {"job_id": str(job_id), "title": d.get("title"), "company": d.get("company"),
                                      "url": _JOB_URL.format(job_id),
                                      "started": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"job_id": job_id, "title": d.get("title"), **state}


@mcp.tool()
@_locked
def linkedin_apply_read() -> dict:
    """Read the current step of the open Easy Apply dialog.

    ``fields[]``: ``label``, ``type`` (text, tel, email, number, textarea, select, radio, checkbox,
    typeahead, resume), ``required``, ``value``, ``options``, ``max_length``, ``error``; the resume step
    lists ``resumes[]`` (index, name, date, selected). Also ``step``/``steps``, ``buttons``,
    ``is_review`` (the submit button is visible), ``follow_company`` and, on review, ``review_text``.
    """
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    state = _poll(lambda: _js(*pos, "modal_read"), _dialog_ready, timeout=8)
    stop = _checkpoint(*pos)
    if stop:
        return stop
    return {"job_id": app.get("job_id"), **state}


@mcp.tool()
@_locked
def linkedin_apply_fill(answers: dict[str, Any]) -> dict:
    """Fill fields of the current step by label (exact, prefix or unique substring; accents and case ignored).

    Values: text/number as strings; ``select``/``radio`` the option text; ``checkbox`` a list of option
    texts (or true/false for a single box); ``typeahead`` the text to type, then the first matching
    suggestion is picked. Re-reads the step and reports ``ok``/``mismatch`` per answer and ``all_ok``.
    Never advances or submits. Not for applications opened with linkedin_apply_prepare (use fill_all).
    """
    bad = guard.paused_error()
    if bad:
        return bad
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    if app.get("phase"):
        return sb.err("use_fill_all", "Esta solicitud se abrió con linkedin_apply_prepare: llénala con "
                                      "linkedin_apply_fill_all.")
    r = _js(*pos, "modal_fill", answers, select=True)
    if r.get("_error") or r.get("status") != "filled":
        return r if r.get("_error") else sb.err(r.get("status", "fill_failed"), "No hay formulario abierto.")
    results = r["results"]
    for key, res in results.items():
        if res.get("status") == "typed_needs_pick":
            time.sleep(1.5)
            p = _js(*pos, "typeahead_pick", {"option": answers[key]}, select=True)
            res["pick"] = p
            res["status"] = "set" if p.get("status") == "picked" else "typeahead_no_match"
    time.sleep(0.6)
    state = _js(*pos, "modal_read")
    if state.get("_error"):
        return state
    fields = state.get("fields", [])
    for key, res in results.items():
        if res.get("status") != "set":
            continue
        f = _find_field(fields, res.get("label") or key)
        res["value"] = f.get("value") if f else None
        res["status"] = "ok" if f and _matches(f, answers[key]) else "mismatch"
    return {"job_id": app.get("job_id"), "results": results,
            "all_ok": all(x.get("status") == "ok" for x in results.values()), "state": state}


@mcp.tool()
@_locked
def linkedin_apply_select_resume(name: Optional[str] = None, index: Optional[int] = None) -> dict:
    """On the resume step, select a resume already stored in LinkedIn by file name (most recent match) or index."""
    bad = guard.paused_error()
    if bad:
        return bad
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    if name is None and index is None:
        return sb.err("missing_arg", "Indica name o index.")
    r = _js(*pos, "select_resume", {"name": name, "index": index}, select=True)
    if r.get("_error"):
        return r
    stop = _checkpoint(*pos)
    if stop:
        return stop
    if r.get("status") == "selected":
        chosen = {"resume": {"name": r.get("name"), "date": r.get("date"), "index": r.get("index")}}
        if app.get("phase"):
            chosen["resume_choice"] = r.get("name")
        guard.set("current_application", {**app, **chosen})
    time.sleep(0.5)
    return {"job_id": app.get("job_id"), **r, "state": _js(*pos, "modal_read")}


@mcp.tool()
@_locked
def linkedin_apply_upload_resume(file_path: str, timeout: float = 45.0) -> dict:
    """Upload a local resume (PDF/DOC/DOCX, max 2 MB) on the resume step, with no macOS file dialog.

    **This sends the file to LinkedIn** (it stays in the account's resume list). Call it only with a
    file Allan approved. Returns the file's SHA-256 for the application record.
    """
    bad = guard.paused_error()
    if bad:
        return bad
    path = Path(file_path).expanduser()
    if not path.is_file():
        return sb.err("file_not_found", f"No existe: {path}")
    mime = _UPLOAD_EXTS.get(path.suffix.lower())
    if not mime:
        return sb.err("bad_file_type", "LinkedIn acepta PDF, DOC o DOCX.")
    size = path.stat().st_size
    if size == 0 or size > _UPLOAD_MAX_BYTES:
        return sb.err("bad_file_size", f"El archivo debe pesar menos de 2 MB (tiene {size} bytes).")
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    data = path.read_bytes()

    def resume_list(s: dict) -> list[dict]:
        res = next((f for f in s.get("fields", []) if f.get("type") == "resume"), None)
        return res.get("resumes", []) if res else []

    before = resume_list(_js(*pos, "modal_read"))
    same_before = sum(1 for x in before if x["name"] == path.name)
    r = _js(*pos, "upload_begin", select=True)
    if r.get("_error") or r.get("status") != "ready":
        return r if r.get("_error") else sb.err(r.get("status", "upload_failed"), "No encontré el botón Cargar currículum.")
    b64 = base64.b64encode(data).decode("ascii")
    for i in range(0, len(b64), _UPLOAD_CHUNK):
        c = _js(*pos, "file_chunk", {"data": b64[i:i + _UPLOAD_CHUNK], "reset": i == 0})
        if c.get("_error"):
            return c
    commit = _js(*pos, "file_commit", {"name": path.name, "mime": mime})
    if commit.get("_error") or commit.get("status") != "committed":
        return commit if commit.get("_error") else sb.err(commit.get("status", "commit_failed"), "LinkedIn no aceptó el archivo.")

    def uploaded(s: dict) -> bool:
        # A same-name resume may already be there (and preselected): only a NEW entry with this name counts.
        now = resume_list(s)
        grew = len(now) > len(before) or sum(1 for x in now if x["name"] == path.name) > same_before
        return grew and any(x["name"] == path.name and x["selected"] for x in now)

    state = _poll(lambda: _js(*pos, "modal_read"), uploaded, timeout=timeout, step=1.5)
    ok = uploaded(state) if not state.get("_error") else False
    sha = hashlib.sha256(data).hexdigest()
    if ok:
        sel = next(x for x in resume_list(state) if x["name"] == path.name and x["selected"])
        resume_ledger.add(path.name, sel.get("date") or "", sha, str(path),
                          note=f"subido en la Solicitud sencilla {app.get('job_id')}")
        chosen = {"resume": {"name": path.name, "date": sel.get("date"), "index": sel.get("index"), "sha256": sha}}
        if app.get("phase"):
            chosen["resume_choice"] = path.name
        guard.set("current_application", {**app, **chosen})
    return {"job_id": app.get("job_id"), "uploaded": ok, "file": path.name, "size_bytes": size, "sha256": sha,
            "state": state}


@mcp.tool()
@_locked
def linkedin_apply_next() -> dict:
    """Press "Siguiente"/"Revisar" (Next/Review) once and return the new step, or the validation errors.

    It never presses "Enviar solicitud" (that is linkedin_apply_submit) nor "Continuar". If the form goes away
    after the press, that is recorded as a possible send and the MCP pauses. Not for applications opened with
    linkedin_apply_prepare (use fill_all).
    """
    bad = guard.paused_error()
    if bad:
        return bad
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    if app.get("phase"):
        return sb.err("use_fill_all", "Esta solicitud se abrió con linkedin_apply_prepare: avanza con "
                                      "linkedin_apply_fill_all.")
    bad = _cap_reached()
    if bad:
        return bad
    before = _stable_read(pos)
    if before.get("_error"):
        return before
    if not before.get("open"):
        return sb.err("dialog_not_open", "El formulario no está abierto en la pestaña.")
    if before.get("is_review"):
        return {"job_id": app.get("job_id"), "status": "already_on_review", "state": before}
    app = {**app, "answers_filled": {**(app.get("answers_filled") or {}),
                                     **flow.step_values(before.get("fields", []), _step_no(before, app),
                                                        f"{app.get('job_id')}:")}}
    app["resume"] = _resume_on(before.get("fields", [])) or app.get("resume")
    guard.set("current_application", app)
    new, stop = _press_next(pos, before, app, "apply_next")
    if stop:
        return {"job_id": app.get("job_id"), "advanced": False, **stop}
    pressed = new.pop("pressed", None)
    advanced = (new.get("step") != before.get("step") or bool(new.get("is_review"))
                or (new.get("step") is None and flow.page_fingerprint(new) != flow.page_fingerprint(before)))
    out = {"job_id": app.get("job_id"), "advanced": advanced, "pressed": pressed, "state": new}
    if new.get("errors") and not advanced:
        out["status"] = "form_has_errors"
    return out


@mcp.tool()
@_locked
def linkedin_apply_submit(job_id: str, confirm: bool = False, follow_company: bool = False) -> dict:
    """Press "Enviar solicitud" on the review step and record the application.

    Pass ``confirm=True`` **only after an explicit "sí" from Allan in the chat for this job**.
    Also requires, right before the click: the same ``job_id`` as the open application and as the page in
    the tab, the same company in the dialog, the review step with no errors and no empty required field,
    the resume chosen for this application (if one was chosen through the MCP), daily cap left and the
    minimum gap since the last submit. Unchecks "Seguir a <empresa>" unless ``follow_company=True``.
    If LinkedIn answers the click with validation errors, nothing was sent and nothing is recorded.
    """
    if confirm is not True:
        return sb.err("confirmation_required", "Enviar exige confirm=True, y solo después de un \"sí\" explícito "
                                                "de Allan para esta vacante.")
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    pend = guard.get("press_pending") or {}
    if pend.get("job_id") == app.get("job_id"):
        resolved = _resolve_pending(pos, app, _stable_read(pos))
        if resolved:
            return resolved
    if app.get("job_id") != str(job_id):
        return sb.err("job_mismatch", "El job_id no coincide con la solicitud abierta.",
                      open_job_id=app.get("job_id"))
    bad = guard.before_submit()
    if bad:
        return bad
    if app.get("phase") and app.get("phase") != "at_review":
        return sb.err("not_at_review", "Esta solicitud se preparó con linkedin_apply_prepare: llega a la revisión con "
                                       "linkedin_apply_fill_all antes de enviar.", phase=app.get("phase"))
    state = _js(*pos, "modal_read")
    if state.get("_error"):
        return state
    if state.get("success"):  # LinkedIn's confirmation is on screen: it was sent (by Allan, or by an unseen click)
        return _closed_after_click(pos, app, "submit", state)
    if not state.get("open") or not state.get("is_review"):
        return sb.err("not_on_review", "Llega primero a la pantalla de revisión con " +
                      ("linkedin_apply_fill_all." if app.get("phase") else "linkedin_apply_next."), state=state)
    if state.get("errors"):
        return sb.err("form_has_errors", "El formulario tiene errores.", errors=state["errors"])
    if (app.get("review_sig") and flow.signature(state) != app["review_sig"]) or \
            (app.get("review_hash") and _review_hash(state) != app["review_hash"]):
        return sb.err("review_changed", "La revisión cambió desde que la viste; vuelve a pasar por "
                                        "linkedin_apply_fill_all y muéstrasela a Allan.")
    detail = _js(*pos, "job_detail")
    if detail.get("_error"):
        return detail
    if detail.get("job_id") != str(job_id):
        return sb.err("job_mismatch", "La pestaña no muestra esta vacante.", tab_job_id=detail.get("job_id"))
    if not _same_company(state.get("company"), app.get("company")):
        return sb.err("company_mismatch", f"El formulario es para \"{state.get('company')}\" y la solicitud abierta "
                                          f"es de \"{app.get('company')}\".")
    empty = [f.get("label") for f in state.get("fields", []) if f.get("required") and answers.current_value(f) in ("", [])]
    if empty:
        return sb.err("form_incomplete", "Hay campos obligatorios vacíos.", fields=empty)
    seen = _selected_resume(state)
    if app.get("phase"):
        bad = _cv_check(app, state, app.get("resume_choice") or config.DEFAULT_RESUME)
        if bad:
            return bad
    want = None if app.get("phase") else app.get("resume")
    if want and not seen:
        return sb.err("resume_unknown", "No pude leer qué CV está elegido en el formulario; revísalo en Safari antes "
                                        "de enviar.", approved=want)
    if want and (seen["name"] != want.get("name") or (want.get("date") and seen["date"]
                                                       and seen["date"] != want["date"])):
        return sb.err("resume_mismatch", "El CV elegido en el formulario no es el aprobado para esta solicitud.",
                      approved=want, selected=seen)
    stop = _checkpoint(*pos)
    if stop:
        return stop
    if state.get("follow_company"):
        f = _js(*pos, "set_follow", bool(follow_company), select=True)
        if f.get("_error") or f.get("checked") != bool(follow_company):
            return sb.err("follow_toggle_failed", "No pude ajustar la casilla de seguir a la empresa.", detail=f)
        again = _js(*pos, "modal_read")  # the toggle must not have touched anything Allan approved
        if again.get("_error") or (app.get("review_sig") and (flow.signature(again) != app["review_sig"]
                                                              or _review_hash(again) != app.get("review_hash"))):
            return sb.err("review_changed", "Al ajustar «Seguir a la empresa» cambió otra cosa de la revisión. "
                                            "No envié; revísalo en Safari.")
    guard.set("press_pending", {"job_id": str(job_id), "where": "submit", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    r = _js(*pos, "click_submit", select=True)
    if r.get("_error"):
        if r.get("status") in _JS_NEVER_RAN:
            guard.set("press_pending", None)
            return r
        return {**r, "press_unobserved": True,
                "message": "No sé si se pulsó Enviar. No lo repito: revisa en Safari y llama a linkedin_apply_close "
                           "(si se envió, lo registra)."}
    if r.get("status") != "clicked":
        guard.set("press_pending", None)
        return sb.err(r.get("status", "submit_failed"), "No pude pulsar Enviar solicitud.")
    after = _poll(lambda: _js(*pos, "modal_read"),
                  lambda s: bool(s.get("success")) or bool(s.get("errors")) or not s.get("open"), timeout=25, step=1.0)
    if after.get("open") and after.get("errors") and not after.get("success"):
        # LinkedIn validates before sending: errors on a still-open form mean nothing went out.
        guard.set("press_pending", None)
        return {**sb.err("form_has_errors", "LinkedIn no aceptó el envío: el formulario muestra errores. No se envió "
                                            "ni se registró.", errors=after["errors"]), "submitted": False}
    confirmed = bool(after.get("success"))
    if not confirmed:
        detail = _poll(lambda: _js(*pos, "job_detail"), lambda d: d.get("apply_type") == "applied", timeout=10)
        confirmed = detail.get("apply_type") == "applied"
    entry, logged = _log_send({
        "job_id": str(job_id), "title": app.get("title"), "company": app.get("company"), "url": app.get("url"),
        "apply_type": "easy_apply", "via": "submit", "follow_company": bool(follow_company), "confirmed": confirmed,
        **_enrich(app, state),
        "success_text": after.get("success_text", ""), "review_text": state.get("review_text", ""),
    })
    guard.set("press_pending", None)
    if after.get("success"):
        done = _js(*pos, "modal_click", "Listo", select=True)
        if done.get("status") != "clicked":
            done = _js(*pos, "modal_click", "Done", select=True)
        if done.get("status") != "clicked":
            _js(*pos, "close_modal", {"save": False}, select=True)
    guard.set("current_application", None)
    cache_error = None
    try:  # best effort: the submit already happened and is logged
        if confirmed:
            jobs.mark(str(job_id), apply_type="applied")
        else:
            jobs.invalidate(str(job_id))
    except Exception as e:  # noqa: BLE001
        cache_error = f"{type(e).__name__}: {e}"
    stop = _checkpoint(*pos)
    return {"submitted": True, "confirmed": confirmed, "entry": {k: v for k, v in entry.items() if k != "review_text"},
            "cache_error": cache_error, **logged,
            "errors": after.get("errors") or None, "paused": stop,
            "message": None if confirmed else "Se pulsó Enviar pero no vi la confirmación; revisa la vacante con "
                                              "linkedin_get_job(job_id, refresh=True) antes de reintentar. Quedó "
                                              "registrada para no duplicarla.",
            "counters": guard.counters()}


@mcp.tool()
@_locked
def linkedin_apply_close(save_draft: bool = True, not_sent: bool = False) -> dict:
    """Close the Easy Apply dialog without submitting. ``save_draft`` picks "Guardar" (default) or "Descartar".

    After an Enviar click that couldn't be checked, the form is closed only with ``not_sent=True``, which Claude
    passes only after Allan checked in Safari that nothing was sent; if the form is gone, it is recorded.

    If the work tab is gone or shows another job, that form is no longer open here: the open application is
    just forgotten (status ``forgotten``) so other jobs can be opened.
    """
    pos, bad, app = _current_app_tab()
    if bad and bad.get("status") == "no_application":  # a form open in the work tab that nothing tracks
        wpos, wbad = _work_tab()
        st = _js(*wpos, "modal_read") if wpos and not wbad else {}
        if not (st.get("open") or st.get("save_prompt")):
            return bad
        pos, app = wpos, {"job_id": (guard.get("work_tab") or {}).get("job_id"), "untracked": True}
        bad = None
    if pos and app and not app.get("untracked"):
        st = _stable_read(pos)
        pend = guard.get("press_pending") or {}
        if not_sent is True and pend.get("where") == "submit" and pend.get("job_id") == app.get("job_id") \
                and (st.get("open") or st.get("save_prompt")) and not st.get("success"):
            guard.set("press_pending", None)  # Allan checked in Safari: the form is there and nothing was sent
        pending = _resolve_pending(pos, app, st)
        if pending:
            return pending
        if st.get("success"):  # LinkedIn's confirmation is on screen: it was sent
            return _closed_after_click(pos, app, "close", st)
    if bad and bad.get("status") in ("work_tab_mismatch", "work_tab_lost") and app:
        pend = guard.get("press_pending") or {}
        if pend.get("job_id") == app.get("job_id"):  # a click nobody saw, and now no tab to check: count it
            guard.set("press_pending", None)
            guard.set("current_application", None)
            entry, logged = _log_send({"job_id": app.get("job_id"), "title": app.get("title"),
                                       "company": app.get("company"), "url": app.get("url"), "apply_type": "easy_apply",
                                       "confirmed": False, "unexpected": True, "via": pend.get("where"),
                                       **_enrich(app)})
            return {**sb.err("dialog_vanished", "Había un clic sin comprobar y la pestaña ya no muestra la vacante. "
                                                "Quedó registrada sin confirmar y el MCP está en pausa: revísalo."),
                    "entry": {k: v for k, v in entry.items() if k != "answers"},
                    "paused": guard.pause(f"dialog_vanished:{pend.get('where')}", ""), **logged}
        guard.set("current_application", None)
        return {"job_id": app.get("job_id"), "status": "forgotten",
                "message": "La pestaña de trabajo ya no muestra esa vacante, así que su formulario no sigue abierto "
                           "aquí. Se olvidó la solicitud abierta."}
    if bad:
        return bad
    r = _js(*pos, "close_modal", {"save": save_draft}, select=True)
    if r.get("status") == "close_clicked":
        time.sleep(1.2)
        r = _js(*pos, "close_modal", {"save": save_draft}, select=True)
        if r.get("status") == "no_dialog":  # closed without asking (nothing to save)
            r = {"status": "closed"}
    if r.get("_error"):
        return r
    state = _js(*pos, "modal_read")
    if not state.get("open") and not state.get("save_prompt"):
        guard.set("current_application", None)
    return {"job_id": app.get("job_id"), **r, "still_open": bool(state.get("open") or state.get("save_prompt"))}


# -----------------------------------------------------------------------------
# Prepare and fill in few calls (the skill's main path)
# -----------------------------------------------------------------------------

_JOB_SUMMARY = ("job_id", "title", "company", "meta", "chips", "apply_type", "applied_status", "external_url",
                "external_kind", "external_site", "account_hint", "clean_url", "ats", "apply_url", "in_local_log")
_FILLING_PHASES = ("prepared", "filling", "draft", "at_review")
_SENT = ("unexpected_submit", "dialog_vanished")
_NOT_SETTLED = {"status": "step_not_settled",
                "message": "El paso no terminó de mostrarse (los campos seguían cambiando). No avancé; revísalo en Safari."}
_CV_WAY_OUT = ("Para seguir: pulsa Atrás en Safari hasta el paso del CV y vuelve a llamar a linkedin_apply_fill_all, "
               "o cierra con linkedin_apply_close(save_draft=False) y prepárala de nuevo.")


def _load_bank() -> tuple[Optional[answers.Bank], Optional[dict]]:
    try:
        bank = answers.load(config.bank_json())
    except (OSError, ValueError) as e:
        return None, sb.err("bank_unreadable", f"No pude leer {config.bank_json()}: {e}")
    errors = answers.validate(bank.data)
    if errors:
        return None, sb.err("bank_invalid", "respuestas.json tiene errores; corrígelos antes de seguir.", errors=errors)
    return bank, None


def _stable_read(pos: tuple[int, int], tries: int = 10, wait_open: bool = False, seed: Optional[dict] = None) -> dict:
    """modal_read once the step has rendered: two reads in a row with the same signature.

    LinkedIn draws the dialog shell first and the fields after; acting on a half-drawn step would let
    prefilled values through unseen. A step that keeps changing comes back marked ``_unsettled`` (callers
    stop). ``wait_open`` first waits for the dialog to appear (right after clicking "Solicitud sencilla"),
    with its own budget. ``seed`` is a read just taken, to compare the first new read with.
    """
    last: dict = {}
    prev = seed if seed and seed.get("open") and not seed.get("_error") else None
    if prev is not None:
        time.sleep(0.8)
    if wait_open:
        for _ in range(19):
            last = _js(*pos, "modal_read")
            if not last.get("_error") and (last.get("open") or last.get("success") or last.get("save_prompt")):
                break
            time.sleep(0.8)
        if last.get("_error") or not last.get("open"):
            return last
        prev = last
        time.sleep(0.8)
    for _ in range(tries):
        cur = _js(*pos, "modal_read")
        last = cur
        if not cur.get("_error"):
            if not cur.get("open"):
                return cur
            if prev is not None and _dialog_ready(cur) and flow.signature(prev) == flow.signature(cur):
                return cur
            prev = cur
        time.sleep(0.8)
    if last.get("_error") or not last.get("open"):
        return last
    return {**last, "_unsettled": True}


def _confirm_gone(pos: tuple[int, int]) -> Optional[dict]:
    """The dialog read as gone: look twice more, 1.5 s apart (its header can re-render between steps).
    None if it is really gone; otherwise the read that showed it again (or LinkedIn's confirmation)."""
    for _ in range(2):
        time.sleep(1.5)
        again = _js(*pos, "modal_read")
        if not again.get("_error") and (again.get("open") or again.get("success")):
            return again
    return None


def _review_hash(state: dict) -> str:
    return hashlib.sha256(" ".join((state.get("review_text") or "").split()).encode("utf-8")).hexdigest()


def _cv_check(app: dict, state: dict, resume_name: str) -> Optional[dict]:
    """On the review: is the CV the approved one? None when fine, else an error dict.

    If the tool saw the resume step, it compares with what it saw. If not (a draft), the review must show the
    chosen file with the date of its newest known upload, and exactly one file with that name and date
    (resumes.json); otherwise it is unverified. A review with no "Currículum:" line belongs to a form that never
    asked for a CV.
    """
    seen = _selected_resume(state)
    shows_cv = bool(seen) or bool(app.get("resume")) or any(f.get("type") == "resume" for f in state.get("fields") or []) \
        or bool(re.search(r"^Currículum: |\.(pdf|docx?|odt)\b", state.get("review_text") or "", re.M | re.I))
    if not shows_cv:
        return None
    want = app.get("resume")
    if not seen:
        return sb.err("resume_unknown", "No pude leer qué CV muestra la revisión. " + _CV_WAY_OUT, approved=want)
    if want:
        if seen["name"] != want.get("name") or (want.get("date") and seen["date"] and seen["date"] != want["date"]):
            return sb.err("resume_mismatch", "La revisión muestra otro CV que el elegido.", approved=want,
                          selected=seen)
        if want.get("name") != resume_name:
            return sb.err("resume_mismatch", f"El CV elegido ahora es {resume_name}, pero el formulario lleva "
                                             f"{want.get('name')}. " + _CV_WAY_OUT, approved=resume_name, selected=seen)
        return None
    if seen["name"] != resume_name:
        return sb.err("resume_mismatch", "La revisión muestra otro CV que el elegido. " + _CV_WAY_OUT,
                      approved=resume_name, selected=seen)
    newest = resume_ledger.newest(resume_name)
    one = resume_ledger.lookup(seen["name"], seen["date"]) if seen["date"] else None
    if not newest or not one or seen["date"] != newest.get("linkedin_date"):
        return sb.err("resume_unverified", "La revisión muestra un CV con ese nombre, pero no puedo confirmar que sea "
                                           "la copia más reciente (lo eligió un borrador). " + _CV_WAY_OUT,
                      selected=seen, newest_known=newest)
    return None


def _step_no(state: dict, app: dict) -> int:
    """The step number for field keys: LinkedIn's "N/M páginas", or our own page count when it shows none."""
    return state.get("step") or app.get("page") or 1


def _forward(state: dict) -> bool:
    return any(k in ("next", "submit") for k in state.get("button_kinds") or [])


def _closed_after_click(pos: tuple[int, int], app: dict, where: str, new: dict) -> dict:
    """The dialog went away after pressing Siguiente/Revisar. Record it (so caps and the log stay true), as sent
    if LinkedIn's confirmation or the job page says so and as unconfirmed otherwise, and pause until Allan looks."""
    sent = bool(new.get("success"))
    url = ""
    if not sent:
        d = _poll(lambda: _js(*pos, "job_detail"), lambda x: x.get("apply_type") == "applied", timeout=10)
        sent, url = d.get("apply_type") == "applied", d.get("url", "")
    guard.set("current_application", None)
    guard.set("press_pending", None)
    entry, logged = _log_send({
        "job_id": app.get("job_id"), "title": app.get("title"), "company": app.get("company"), "url": app.get("url"),
        "apply_type": "easy_apply", "confirmed": sent, "unexpected": True, "via": where,
        "success_text": new.get("success_text", ""), **_enrich(app),
    })
    try:
        if sent:
            jobs.mark(str(app.get("job_id")), apply_type="applied")
        else:
            jobs.invalidate(str(app.get("job_id")))
    except Exception:  # noqa: BLE001
        pass
    status = "unexpected_submit" if sent else "dialog_vanished"
    paused = guard.pause(f"{status}:{where}", url)
    message = ("El formulario se cerró al pulsar Siguiente/Revisar y LinkedIn indica que la solicitud se envió."
               if sent else "El formulario desapareció después de pulsar Siguiente/Revisar y no sé si se envió.")
    return {**sb.err(status, message + " Quedó registrada para no duplicarla y el MCP está en pausa: revísalo en "
                                       "Safari y avísame."),
            "entry": {k: v for k, v in entry.items() if k != "answers"}, "paused": paused, **logged}


def _resolve_pending(pos: tuple[int, int], app: dict, state: dict) -> Optional[dict]:
    """A Siguiente pressed in an earlier call whose outcome was never seen: if the form is now gone (or the page
    can't be read), treat it as a possible send; if the form is there, it didn't send."""
    pend = guard.get("press_pending") or {}
    if not pend or pend.get("job_id") != app.get("job_id"):
        return None
    if state.get("success"):
        return _closed_after_click(pos, app, pend.get("where", "?"), state)
    if state.get("_error"):  # can't tell yet: keep it pending and say so
        return {**state, "press_pending": pend,
                "message": "Hay un clic anterior cuyo resultado no vi y no puedo leer la página. Revísalo en Safari."}
    if not state.get("open") and not state.get("save_prompt"):
        back = _confirm_gone(pos)
        if back is None or back.get("success"):
            return _closed_after_click(pos, app, pend.get("where", "?"), back or {})
    if pend.get("where") == "submit":  # the form is still there, but that click may be in flight: nothing re-arms
        return sb.err("submit_unverified", "Un clic anterior en Enviar no se pudo comprobar. Revisa en Safari si se "
                                           "envió. Si se envió, linkedin_apply_close lo registra en cuanto el "
                                           "formulario ya no esté; si Allan comprueba que no se envió, cierra con "
                                           "linkedin_apply_close(not_sent=True) y prepárala de nuevo.")
    guard.set("press_pending", None)
    return None


def _cap_reached(pacing: bool = False) -> Optional[dict]:
    """Pressing Siguiente can turn out to send (cbc, 06/10/2026): no form is walked when no send is left today,
    and (``pacing``) no Siguiente is pressed inside the minimum gap after the last send."""
    c = guard.counters()
    if c["applications_left"] <= 0:
        return sb.err("daily_apply_limit", f"Ya se enviaron {c['applications']} solicitudes hoy. Sigue mañana.")
    if pacing and c["next_submit_in_s"] > 0:
        return {**sb.err("too_soon", f"Faltan {c['next_submit_in_s']} s del espacio mínimo después del último envío; "
                                     "espera y vuelve a llamar."), "retry_after_s": c["next_submit_in_s"]}
    return None


_JS_NEVER_RAN = ("safari_blocked", "unsupported_platform", "automation_denied", "tab_not_found",
                 "js_from_apple_events_disabled")


def _press_next(pos: tuple[int, int], before: dict, app: dict, where: str) -> tuple[Optional[dict], Optional[dict]]:
    """Press Siguiente/Revisar once (never "Continuar" or a submit). ``(settled_new_state, None)`` or ``(None, stop)``.

    The click itself checks, in the same JS call, that the fields on screen are exactly the ones planned (else
    ``step_changed``, nothing pressed). The press stays marked pending until a real outcome is seen (another step,
    LinkedIn errors, the review); a form that goes away (confirmed by two more reads) or LinkedIn's confirmation is
    recorded and pauses. ``did_not_advance`` if nothing changes (the next call re-checks the pending press).
    """
    bad = _cap_reached(pacing=True)
    if bad:
        return None, bad
    expect = [[f.get("label"), f.get("type"), f.get("value")] for f in before.get("fields") or []]
    guard.set("press_pending", {"job_id": app.get("job_id"), "where": where, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    r = _js(*pos, "click_next", {"expect": expect}, select=True)
    if r.get("_error"):
        if r.get("status") in _JS_NEVER_RAN:
            guard.set("press_pending", None)
            return None, r
        return None, {**r, "press_unobserved": True}
    if r.get("status") != "clicked":
        guard.set("press_pending", None)
        if r.get("status") == "step_changed":
            return None, {"status": "step_changed", "message": "El paso cambió justo antes de pulsar; lo vuelvo a leer."}
        return None, {"status": r.get("status", "no_next_button"), "buttons": r.get("buttons"),
                      "message": "No hay un botón Siguiente o Revisar que se pueda pulsar (si solo está «Continuar», "
                                 "puede enviar la solicitud: no lo pulso). Revísalo en Safari."}
    time.sleep(1.2)
    sig = flow.signature(before)

    def moved(s: dict) -> bool:  # a spinner (same step, no forward button) is not the next step yet
        return bool(s.get("success")) or not s.get("open") or (_dialog_ready(s) and (
            bool(s.get("errors")) or (flow.signature(s) != sig and (s.get("step") != before.get("step")
                                                                    or _forward(s) or bool(s.get("is_review"))))))

    new: Optional[dict] = None
    for _ in range(3):
        first = _poll(lambda: _js(*pos, "modal_read"), moved, timeout=10)
        if first.get("_error"):
            return None, {**first, "press_unobserved": True}
        if first.get("save_prompt") and not first.get("open"):
            guard.set("press_pending", None)
            return None, sb.err("save_prompt", "Apareció «¿Quieres guardar esta solicitud?». No elijo nada: "
                                               "revísalo en Safari.")
        if first.get("success"):
            return None, _closed_after_click(pos, app, where, first)
        if not first.get("open"):
            back = _confirm_gone(pos)
            if back is None or back.get("success"):
                return None, _closed_after_click(pos, app, where, back or first)
            continue  # it came back: keep waiting for the real next step
        if not moved(first):
            new = first
            continue  # still on the pressed step (spinner or nothing yet): wait again, up to 3 polls
        cand = _stable_read(pos, seed=first)
        if cand.get("_error"):
            return None, {**cand, "press_unobserved": True}
        if cand.get("success") or not cand.get("open"):
            back = None if cand.get("success") else _confirm_gone(pos)
            if back is None or back.get("success"):
                return None, _closed_after_click(pos, app, where, back or cand)
            continue
        new = cand
        break
    if new is None or not moved(new):
        unchanged = new is not None and flow.signature(new) == sig and not new.get("errors")
        return None, {"status": "did_not_advance" if unchanged else "press_unobserved", "press_unobserved": True,
                      "buttons": (new or {}).get("buttons"),
                      "message": ("Pulsé Siguiente y el paso no cambió. " if unchanged else
                                  "Pulsé Siguiente y no pude ver en qué quedó. ") + "Revísalo en Safari; no insisto."}
    guard.set("press_pending", None)
    stop = _checkpoint(*pos)
    if stop:
        return None, stop
    if new.get("_unsettled"):
        return None, dict(_NOT_SETTLED)
    return {**new, "pressed": r.get("label")}, None


def _resume_on(fields: list[dict]) -> Optional[dict]:
    res = next((f for f in fields if f.get("type") == "resume"), None)
    sel = res and next((r for r in res.get("resumes") or [] if r.get("selected")), None)
    return {k: sel.get(k) for k in ("name", "date", "index")} if sel else None


def _page_key(state: dict) -> str:
    return json.dumps([sorted(f.get("label") or "" for f in state.get("fields") or []),
                       sorted(set(state.get("buttons") or []))], ensure_ascii=False)


def _new_page(app: dict, state: dict, outside: bool = False) -> None:
    """Pages without "N/M páginas": number them ourselves. A page seen before gets its number back when the page
    changed outside the tool (Atrás in Safari), or when our own Siguiente leads forward to a later page already
    seen; otherwise it is a new page (two pages can look alike)."""
    known = (app.get("pages") or {}).get(_page_key(state))
    if known and not outside and known <= app.get("page", 1):
        known = None
    if known:
        app["page"] = known
    else:
        app["page"] = app["page_max"] = max(app.get("page_max", 1), app.get("page", 1)) + 1
    _remember_page(app, state)


def _remember_page(app: dict, state: dict) -> None:
    app.setdefault("pages", {})[_page_key(state)] = app.get("page", 1)
    app["page_review"] = bool(state.get("is_review"))
    app["page_labels"] = [f.get("label") for f in state.get("fields") or []]
    app["page_kinds"] = sorted(set(state.get("button_kinds") or []))
    app["page_forward"] = "next" in app["page_kinds"]


def _page_changed_outside(app: dict, state: dict) -> bool:
    """A step-less page that isn't the one we left: it had Siguiente, and its buttons changed (Atrás appeared,
    Siguiente became Revisar…) or its questions are not a superset of the old ones. A conditional question only
    adds labels and leaves the buttons alone; a one-page form never changes page."""
    if state.get("step") is not None or "page_labels" not in app:
        return False
    if app.get("page_review") and not state.get("is_review"):
        return True  # Atrás from the review
    if not app.get("page_forward"):
        return False
    if sorted(set(state.get("button_kinds") or [])) != app.get("page_kinds"):
        return True
    return not set(app["page_labels"]) <= {f.get("label") for f in state.get("fields") or []}


@mcp.tool()
@_locked
def linkedin_apply_prepare(job_id: str, resume: str = config.DEFAULT_RESUME, allow_logged: bool = False) -> dict:
    """Open a job's Easy Apply form and gather its questions in ONE call, without filling anything.

    Navigates only if the work tab isn't already on the job (that costs one view). For non-Easy-Apply jobs it
    returns the job with ``external_kind`` and stops. Otherwise it opens the form and, on each fully drawn step,
    presses Siguiente only if the step needs nothing from Allan (every field ``prefilled_ok`` or an empty optional
    field, and the newest upload of ``resume`` selected). It stops at the first step with something to decide, or
    at the review. It never fills and never presses Descartar: the form stays open for linkedin_apply_fill_all.

    Returns ``questionnaire`` (per field: ``key``, step, label, type, options, max_length, current value,
    ``decision`` = proposed | prefilled_ok | confirm | ask | leave_empty | select | upload_needed, ``value`` or
    ``suggested``, bank ``entry``/``status``/``source``, ``reason``, ``ask_via`` = choice | choice_multi | chat),
    ``answers_draft`` (key → value for proposed and prefilled_ok rows) and ``to_ask`` (keys Allan must answer).
    Stops with ``application_in_progress`` if an application is open, ``dialog_already_open`` if the tab already
    shows a form, ``draft_detected`` if the form opens past its first page (a saved draft), ``already_in_log`` if
    the local log has this job (``allow_logged=True`` only after Allan checked it), ``daily_apply_limit`` and
    ``too_soon`` (with ``retry_after_s``) inside the minimum gap after a send; nothing is opened in those cases.
    """
    if not _JOB_ID_RE.fullmatch(str(job_id)):
        return sb.err("bad_job_id", "job_id debe ser el número de la vacante (p. ej. 4474644406).")
    job_id = str(job_id)
    prefix = f"{job_id}:"
    bad = guard.paused_error()
    if bad:
        return bad
    app = guard.get("current_application") or {}
    if app:
        same = app.get("job_id") == job_id
        return sb.err("application_in_progress",
                      "Esta solicitud ya está abierta: sigue con linkedin_apply_fill_all o ciérrala con "
                      "linkedin_apply_close." if same else
                      f"Hay una solicitud abierta de otra vacante ({app.get('job_id')}). Ciérrala con "
                      "linkedin_apply_close antes de preparar otra.", open_job_id=app.get("job_id"))
    bad = _cap_reached()
    if bad:
        return bad
    logged = [a for a in guard.applications() if a.get("job_id") == job_id]
    if logged and allow_logged is not True:
        return sb.err("already_in_log", "Esta vacante ya está en el registro local de envíos. No la abro; si Allan "
                                        "comprueba que no se envió, repite con allow_logged=True.",
                      entries=[{k: a.get(k) for k in ("ts", "confirmed", "unexpected", "via")} for a in logged])
    bad = _cap_reached(pacing=True)  # Siguiente can send: don't open a form that must wait out the gap
    if bad:
        return bad
    bank, bad = _load_bank()
    if bad:
        return bad
    wt = guard.get("work_tab") or {}
    pos, bad = _work_tab() if wt.get("job_id") == job_id else (None, None)
    if bad:
        return bad
    if pos:  # already on the job: read it live, no navigation and no view
        d = _js(*pos, "job_detail")
        if d.get("_error"):
            return d
        if not _job_read_ok(d, job_id):
            return sb.err("job_not_shown", "La pestaña de trabajo no muestra esta vacante completa. Vuelve a abrirla "
                                           "con linkedin_get_job(job_id, refresh=True).", detail=d)
        d["description"] = (d.get("description") or "")[:12000]
        job = _job_result(job_id, jobs.put(job_id, d), from_cache=False)
    else:
        job = linkedin_get_job(job_id, refresh=True)
        if job.get("_error") or job.get("incomplete_read"):
            return job
        pos, bad = _work_tab()
        if bad or not pos:
            return bad or sb.err("work_tab_lost", "No encuentro la pestaña de la vacante.")
    summary = {k: job.get(k) for k in _JOB_SUMMARY if job.get(k) not in (None, "", [])}
    if job.get("apply_type") != "easy_apply":
        messages = {
            "external": "Se postula fuera de LinkedIn; mira external_kind y account_hint.",
            "ats_continue": "Se postula con el enlace «Continuar» al ATS de la empresa: pulsarlo cuenta como envío, "
                            "así que lo pulsa Allan (protocolo de sondeo en el skill).",
            "applied": "Ya figura como solicitada.", "closed": "Ya no acepta solicitudes.",
        }
        return {"status": job.get("apply_type"), "job": summary,
                "message": messages.get(job.get("apply_type"), "No reconozco cómo se postula a esta vacante.")}
    state = _js(*pos, "modal_read")
    if state.get("_error"):
        return state
    if state.get("open") or state.get("save_prompt"):
        return sb.err("dialog_already_open", "Ya hay un formulario abierto en la pestaña (¿un borrador, o lo abrió "
                                             "Allan?). No lo toco: pregúntale si lo cierro guardando o descartando "
                                             "(linkedin_apply_close lo puede cerrar).", job=summary)
    app = {"job_id": job_id, "title": summary.get("title"), "company": summary.get("company"),
           "url": _JOB_URL.format(job_id), "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "phase": "prepared",
           "resume_choice": resume, "answers_filled": {}, "prepared_keys": [], "page": 1, "page_max": 1}
    items: list[dict] = []

    def park(**extra: Any) -> None:  # every exit leaves an application linkedin_apply_close can reach
        guard.set("current_application", {**app, "prepared_keys": [it["key"] for it in items], **extra})

    park(phase="opening")
    r = _js(*pos, "open_easy_apply", select=True)
    if r.get("_error"):
        return {**r, "message": "No sé si el formulario se abrió; si aparece, ciérralo con linkedin_apply_close."}
    if r.get("status") != "clicked":
        guard.set("current_application", None)
        return sb.err(r.get("status", "open_failed"), "No pude abrir la Solicitud sencilla.")
    state = _stable_read(pos, wait_open=True)
    stop = _checkpoint(*pos)
    if stop:
        return stop
    if not state.get("open"):
        return sb.err("dialog_not_open", "El formulario de Solicitud sencilla no se abrió. Si aparece más tarde, "
                                         "ciérralo con linkedin_apply_close.", state=state)
    park()
    reason, early, extra = None, None, {}
    if (state.get("step") or 1) > 1 or "back" in (state.get("button_kinds") or []):  # a first page has no Atrás
        reason = "draft"
        app.update(phase="draft", draft_from_step=state.get("step") or "?")
        items = flow.questionnaire(state.get("fields", []), _step_no(state, app), bank, resume, prefix)
    elif state.get("_unsettled"):
        reason, extra = "step_not_settled", _NOT_SETTLED
    if state.get("step") is None:
        _remember_page(app, state)
    for _ in range(20):
        if reason:
            break
        step = _step_no(state, app)
        fields = state.get("fields", [])
        step_items = flow.questionnaire(fields, step, bank, resume, prefix)
        items = [it for it in items if it["step"] != step] + step_items
        if not fields and not state.get("is_review"):
            reason = "empty_step"
        elif state.get("errors"):
            reason = "errors"
        elif flow.needs_decision(step_items):
            reason = "decision"
        elif state.get("is_review"):
            reason = "review"
        if reason:
            break
        park()
        pressed_app = {**app, "prepared_keys": [it["key"] for it in items],
                       "answers_filled": {**app["answers_filled"], **flow.step_values(fields, step, prefix)},
                       "resume": _resume_on(fields) or app.get("resume")}
        new, stop = _press_next(pos, state, pressed_app, "prepare")
        if stop:
            if stop.get("status") == "step_changed":
                state = _stable_read(pos)
                if not state.get("open") or state.get("_error") or state.get("_unsettled"):
                    reason, extra = "step_not_settled", _NOT_SETTLED
                continue
            if stop.get("status") in _SENT or stop.get("status") == "press_unobserved" or (
                    stop.get("_error") and stop.get("status") not in ("save_prompt", "too_soon")):
                early = {**stop, "job": summary}
                break
            reason, extra = stop.get("status"), stop
            break
        app["answers_filled"].update(flow.step_values(fields, step, prefix))
        app["resume"] = _resume_on(fields) or app.get("resume")
        if new.get("errors") and not new.get("is_review") and new.get("step") == state.get("step"):
            items = [it for it in items if it["step"] != step] + flow.questionnaire(new.get("fields", []), step, bank,
                                                                                     resume, prefix)
            state, reason = new, "blocked"
            break
        if new.get("step") is None and state.get("step") is None:
            _new_page(app, new)
        state = new
    else:
        reason = "too_many_steps"
    if early:
        if early.get("status") not in _SENT:
            park()
        return early
    park(prepared_step=_step_no(state, app), steps=state.get("steps"))
    draft = {it["key"]: it["value"] for it in items if it["decision"] in ("proposed", "prefilled_ok")
             and it["type"] != "resume"}
    to_ask = [it["key"] for it in items if it["decision"] not in ("proposed", "prefilled_ok", "leave_empty", "select")]
    res_row = next((it for it in items if it["type"] == "resume"), None)
    messages = {
        "draft": "El formulario abrió en un paso posterior al primero: hay un borrador guardado. No toqué nada. "
                 "Pregúntale a Allan si sigo desde ahí (linkedin_apply_fill_all con continue_draft=True; los pasos "
                 "anteriores no los vi) o si lo cierro (guardar o descartar).",
        "review": "Llegó a la revisión sin nada que decidir: sigue con linkedin_apply_fill_all para ver el resumen.",
        "decision": "Se detuvo en el primer paso con algo que decidir. Muestra la tabla y pregunta lo de to_ask.",
        "errors": "El paso muestra errores de LinkedIn; están en to_ask.",
        "blocked": "LinkedIn no dejó avanzar: los campos con error están en to_ask.",
        "empty_step": "El paso no muestra campos (¿falta subir un CV?). Revísalo en Safari.",
        "too_many_steps": "Demasiados pasos; revisa el formulario en Safari.",
    }
    return {"status": "draft_detected" if reason == "draft" else "prepared", "job": summary,
            "complete": reason == "review",
            "stopped_at": {"step": _step_no(state, app), "steps": state.get("steps"), "reason": reason,
                           "buttons": state.get("buttons")},
            "questionnaire": [flow.public_item(it) for it in items], "answers_draft": draft, "to_ask": to_ask,
            "resume": flow.public_item(res_row) if res_row else {"chosen": resume, "note": "aún no apareció el paso del CV"},
            "retry_after_s": extra.get("retry_after_s"),
            "dialog_open": True, "message": extra.get("message") or messages.get(reason, "")}


def _review_gaps(app: dict, record: dict, answers_: dict, review_step: int, prefix: str) -> Optional[dict]:
    """At the review: every page before it was planned (none passed by hand) and every answer is what was put in."""
    not_applied = [k for k, v in answers_.items()
                   if k in record and record[k].get("type") != "resume"
                   and not flow.same({"type": record[k].get("type")}, record[k].get("value"), v)]
    if not_applied:
        return sb.err("answers_not_applied", "Algunas respuestas no son las que quedaron en pasos ya pasados (¿cambió "
                                             "alguna?). Pulsa Atrás en Safari hasta ese paso y vuelve a llamar a "
                                             "linkedin_apply_fill_all.", keys=not_applied)
    start = app.get("draft_from_step")
    if start == "?":
        return None
    seen = set()
    for k in record:
        try:
            seen.add(int(k[len(prefix):].split("|", 1)[0]))
        except ValueError:
            pass
    missing = [s for s in range(int(start or 1), review_step) if s not in seen]
    if missing:
        return sb.err("unplanned_steps", "Hay pasos antes de la revisión que la tool no leyó (¿se avanzó a mano?). "
                                         "Pulsa Atrás en Safari hasta el primero y vuelve a llamar a "
                                         "linkedin_apply_fill_all.", steps=missing)
    return None


@mcp.tool()
@_locked
def linkedin_apply_fill_all(job_id: str, answers: dict[str, Any], resume: Optional[str] = None,
                            continue_draft: bool = False, pass_empty_step: bool = False) -> dict:
    """Fill the prepared form step after step with Allan's approved answers, until the review. Never submits.

    ``answers`` maps questionnaire ``key`` → value (start from ``answers_draft`` and add Allan's answers); keys
    of another job are refused. Options must match an option exactly. ``resume`` defaults to the one given to
    prepare. On each step it fills and selects the resume, re-reads the fully drawn step and plans it again
    (conditional questions that appear are caught), and presses Siguiente/Revisar (never "Continuar") only when
    nothing is left to fill or decide. It stops, leaving the form open, on a question without an answer (on a
    step prepare never saw only verified contact data is filled: ``new_step: true``), a prefilled value nobody
    reviewed, a typeahead or repeated label, a mismatch, LinkedIn errors (returned as questions), a press that
    changes nothing, a verification, or the review (``at_review`` with ``review_text``). At the review it also
    checks the CV, that no page was passed by hand and that every answer is the one in the form. Call it again
    after Allan answers; it continues on the current step. A saved draft needs ``continue_draft=True``; a step
    with no fields (``empty_step``) is pressed through only with ``pass_empty_step=True`` (Allan looked at it).
    """
    bad = guard.paused_error()
    if bad:
        return bad
    pos, bad, app = _current_app_tab()
    if bad:
        return bad
    job_id = str(job_id)
    prefix = f"{job_id}:"
    if app.get("job_id") != job_id:
        return sb.err("job_mismatch", "El job_id no coincide con la solicitud abierta.", open_job_id=app.get("job_id"))
    if app.get("phase") not in _FILLING_PHASES:
        return sb.err("not_prepared", "Esta solicitud no se abrió con linkedin_apply_prepare. Ciérrala con "
                                      "linkedin_apply_close(save_draft=True) y vuelve a prepararla.")
    if app.get("draft_from_step") and app.get("phase") == "draft" and continue_draft is not True:
        return sb.err("draft_needs_ok", "Es un borrador guardado: los pasos anteriores no los vi. Solo con el ok de "
                                        "Allan, repite con continue_draft=True.")
    if not isinstance(answers, dict):
        return sb.err("bad_answers", "answers va como objeto {key: valor} con las keys del cuestionario.")
    bad = _cap_reached()
    if bad:
        return bad
    foreign = sorted(k for k in answers if not str(k).startswith(prefix))
    if foreign:
        return sb.err("answers_for_other_job", "Hay respuestas con keys que no son de esta vacante: no las uso.",
                      keys=foreign[:10])
    first = _stable_read(pos)
    pending = _resolve_pending(pos, app, first)
    if pending:
        return pending
    detail = _js(*pos, "job_detail")
    if detail.get("_error"):
        return detail
    if detail.get("job_id") != job_id:
        return sb.err("job_mismatch", "La pestaña no muestra esta vacante.", tab_job_id=detail.get("job_id"))
    bank, bad = _load_bank()
    if bad:
        return bad
    resume_name = resume or app.get("resume_choice") or config.DEFAULT_RESUME
    app = {**app, "resume_choice": resume_name, "phase": "filling"}
    prepared = set(app.get("prepared_keys") or [])
    record = dict(app.get("answers_filled") or {})

    def snapshot(**extra: Any) -> dict:
        return {**app, "prepared_keys": sorted(prepared), "answers_filled": record, **extra}

    def save(**extra: Any) -> None:
        guard.set("current_application", snapshot(**extra))

    fills_here, pressed, seed = 0, False, first
    for _ in range(40):
        state = _stable_read(pos, seed=seed)
        seed = None
        if state.get("_error"):
            save()
            return state
        if not state.get("open") or state.get("success"):
            back = None if state.get("success") or not pressed else _confirm_gone(pos)
            if state.get("success") or (pressed and (back is None or back.get("success"))):
                return {**_closed_after_click(pos, snapshot(), "fill_all", back or state), "answers_filled": record}
            if back:
                continue
            save()
            return sb.err("dialog_not_open", "El formulario no está abierto en la pestaña.")
        if state.get("_unsettled"):
            save()
            return {**_NOT_SETTLED, "dialog_open": True}
        if state.get("step") is None:
            if fills_here == 0 and _page_changed_outside(app, state):
                _new_page(app, state, outside=True)  # Allan moved the form by hand: its own page number
            else:
                _remember_page(app, state)
        step, fields = _step_no(state, app), state.get("fields", [])
        if not fields and not state.get("is_review"):
            if pass_empty_step is not True:
                save()
                return {**sb.err("empty_step", "El paso no muestra campos (¿falta subir un CV?). Revísalo en Safari; "
                                               "si Allan dice que se puede pasar, repite con pass_empty_step=True."),
                        "step": step, "buttons": state.get("buttons"), "dialog_open": True}
            record[f"{prefix}{step}|(paso sin campos)|0"] = {"label": "(paso sin campos)", "type": "empty",
                                                             "value": None}
        plan = flow.plan_step(fields, step, answers, resume_name, prepared, bank, prefix)
        if plan["stop"]:
            new_step = any(it["key"] not in prepared for it in plan["stop"])
            prepared.update(it["key"] for it in plan["items"])  # Allan sees them now
            save()
            draft = {it["key"]: it["value"] for it in plan["items"]
                     if it.get("decision") in ("proposed", "prefilled_ok") and it["type"] != "resume"
                     and it["key"] not in answers}
            return {"status": "needs_answers", "job_id": job_id, "new_step": new_step, "step": step,
                    "steps": state.get("steps"), "questions": [flow.public_item(it) for it in plan["stop"]],
                    "answers_draft": draft, "dialog_open": True,
                    "message": "Paso nuevo: muestra sus preguntas a Allan." if new_step else
                               "Faltan respuestas, alguna no calza con el formulario o LinkedIn marca un error."}
        if plan["select_resume"] or plan["fill"]:
            fills_here += 1
            if fills_here > 3:
                save()
                return {**sb.err("fill_loop", "El paso cambia cada vez que lo lleno; revísalo en Safari."),
                        "step": step, "dialog_open": True}
            if plan["select_resume"]:
                r = _js(*pos, "select_resume", {"index": plan["select_resume"]["index"]}, select=True)
                if r.get("_error") or r.get("status") != "selected" or r.get("name") != resume_name:
                    save()
                    return sb.err("resume_select_failed", "No pude elegir el CV aprobado.", detail=r)
            if plan["fill"]:
                r = _js(*pos, "modal_fill", plan["fill"], select=True)
                if r.get("_error") or r.get("status") != "filled":
                    save()
                    return r if r.get("_error") else sb.err(r.get("status", "fill_failed"), "No pude llenar el paso.")
                failed = {k: v for k, v in r["results"].items() if v.get("status") != "set"}
                if failed:
                    save()
                    return {**sb.err("fill_failed", "Algunos campos no se pudieron llenar."), "results": failed,
                            "step": step, "dialog_open": True}
            after = _stable_read(pos)
            if after.get("_error"):
                save()
                return after
            wrong = flow.verify(after.get("fields", []), step, plan["fill_keys"], prefix)
            got = _resume_on(after.get("fields", []))
            if plan["select_resume"] and (not got or got["name"] != resume_name):
                wrong.append({"key": plan["select_resume"]["key"], "expected": resume_name, "got": got})
            if wrong:
                save()
                return {**sb.err("mismatch", "Lo que quedó en el formulario no es lo que se llenó."), "mismatch": wrong,
                        "step": step, "dialog_open": True}
            seed = after
            continue  # plan the same step again on a fresh read: conditional questions may have appeared
        record.update(flow.step_values(fields, step, prefix))
        if _resume_on(fields):
            app["resume"] = _resume_on(fields)
        save()
        stop = _checkpoint(*pos)
        if stop:
            return stop
        if state.get("is_review"):
            bad = _cv_check(app, state, resume_name) or _review_gaps(app, record, answers, step, prefix)
            if bad:
                return {**bad, "review_text": state.get("review_text", ""), "dialog_open": True}
            save(phase="at_review", review_sig=flow.signature(state), review_hash=_review_hash(state))
            out = {"status": "at_review", "job_id": job_id, "title": app.get("title"), "company": app.get("company"),
                   "review_text": state.get("review_text", ""), "resume": app.get("resume") or _selected_resume(state),
                   "follow_company": state.get("follow_company"), "answers_filled": record, "dialog_open": True,
                   "message": "En la revisión. Muestra el resumen a Allan y pregunta «¿Envío la solicitud a "
                              "<empresa> – <puesto>?». Solo con su sí: linkedin_apply_submit(job_id, confirm=True)."}
            if app.get("draft_from_step"):
                out["unreviewed_steps"] = (f"los anteriores al paso {app['draft_from_step']} (abrió como borrador): "
                                           "muestra review_text completo a Allan")
            return out
        new, stop = _press_next(pos, state, snapshot(), "fill_all")
        if stop:
            if stop.get("status") == "step_changed":
                continue
            if stop.get("status") not in _SENT:
                save()
            return {**stop, "answers_filled": record, "dialog_open": stop.get("status") not in _SENT}
        if new.get("errors") and not new.get("is_review") and new.get("step") == state.get("step"):
            errs = flow.questionnaire(new.get("fields", []), step, bank, resume_name, prefix)
            prepared.update(it["key"] for it in errs)
            save()
            return {**sb.err("form_has_errors", "LinkedIn no dejó avanzar: el paso tiene errores."),
                    "errors": new["errors"], "step": step, "dialog_open": True,
                    "questions": [flow.public_item(it) for it in errs if it.get("decision") == "ask"]}
        if new.get("step") is None and state.get("step") is None:
            _new_page(app, new)
        fills_here, pressed, seed = 0, True, new
        save()
    save()
    return sb.err("too_many_steps", "Demasiados pasos; revisa el formulario en Safari.")


@mcp.tool()
@_locked
def linkedin_inspect(tab_id: Optional[str] = None) -> dict:
    """Read-only look at a LinkedIn jobs tab (default: the work tab): no navigation, no click, no view counted.

    Returns the URL, the job as the page shows it (``apply_type``, ``external_url``, ``applied_status``…), the
    Easy Apply dialog if one is open (step, fields, buttons) and how many other dialogs are on screen (their
    text is not returned). Meant for probing what "Continuar" does after Allan presses it. Only ``/jobs/``
    pages. A verification on the page still turns on the pause.
    """
    if tab_id:
        pos, bad = _tab(tab_id)
        if bad:
            return bad
    else:
        pos, bad = _work_tab()
        if bad:
            return bad
        if not pos:
            return sb.err("no_work_tab", "No hay pestaña de trabajo; pasa tab_id (ver linkedin_status).")
    st = _js(*pos, "page_state")
    if st.get("_error"):
        return st
    if not re.match(r"^https://([a-z0-9-]+\.)?linkedin\.com/jobs/", st.get("url", ""), re.I):
        return sb.err("not_jobs_page", "linkedin_inspect solo lee páginas de empleos (/jobs/).")
    reason = detect_checkpoint(st.get("url", ""), st.get("headings"), st.get("alerts"), st.get("captcha_frame", False))
    if reason:
        return guard.pause(reason, st.get("url", ""))
    out: dict[str, Any] = {"tab_id": f"{pos[0]}:{pos[1]}", "url": st.get("url"), "title": st.get("title"),
                           "other_dialogs": len(st.get("alerts") or [])}
    if "/jobs/view/" in st.get("url", ""):
        d = _js(*pos, "job_detail")
        if not d.get("_error"):
            out["job"] = {k: d.get(k) for k in _JOB_SUMMARY if d.get(k) not in (None, "", [])}
    m = _js(*pos, "modal_read")
    if not m.get("_error"):
        out["dialog"] = {k: m.get(k) for k in ("open", "save_prompt", "success", "success_text", "dialog_title",
                                                "step", "steps", "fields", "buttons", "button_kinds", "is_review",
                                                "errors") if m.get(k) not in (None, "", [])}
    return out


@mcp.tool()
@_locked
def linkedin_answers_save(entries: list[dict[str, Any]], confirm: bool = False) -> dict:
    """Save answers Allan approved as reusable into the bank (``respuestas.json``), as ``aprobado <today>``.

    Each entry approves an existing ``confirmar`` entry (``{"id", "answer"?}``) or adds a new one
    (``{"question", "patterns": {"es": [...], "en": [...]}, "answer": {"text"|"number"|"yes_no"|"choice"},
    "applies"?: "general"|"years"}``). Entries that would change or shadow a ``verificado`` or ``preguntar``
    entry (salary, start date, work mode, relocation…) are refused. Without ``confirm=True`` it only returns
    the diff: show it to Allan, and repeat with ``confirm=True`` after his ok. Saving also regenerates
    ``respuestas-linkedin.md``.
    """
    try:
        data = answers.load(config.bank_json()).data
    except (OSError, ValueError) as e:
        return sb.err("bank_unreadable", f"No pude leer {config.bank_json()}: {e}")
    new, diff, errors = answers.save_entries(data, list(entries or []), time.strftime("%Y-%m-%d"))
    if errors:
        return {**sb.err("rejected", "No se guardó nada."), "errors": errors}
    if confirm is not True:
        return {"status": "preview", "diff": diff,
                "message": "Muestra el diff a Allan; con su ok, repite con confirm=True."}
    answers.write(new, config.bank_json())
    md = config.bank_md()
    tmp = md.with_suffix(".md.tmp")
    tmp.write_text(answers.render_md(new), encoding="utf-8")
    tmp.replace(md)
    return {"status": "saved", "diff": diff, "path": str(config.bank_json())}


# -----------------------------------------------------------------------------
# Log and pause
# -----------------------------------------------------------------------------


_VIA_RE = re.compile(r"[a-z_]{1,30}")


@mcp.tool()
@_locked
def linkedin_record_manual(job_id: str, via: str = "ats_continue", notes: str = "") -> dict:
    """Record an application Allan sent himself (e.g. the ATS "Continuar" link) once LinkedIn shows it as sent.

    Reads the job live from the work tab when it is already on that job (no view), else opens it fresh (one
    view), and records only if that page is this job and reads ``applied`` with its "Solicitud enviada" line.
    Refuses a job already in the local log or already in either Markdown log (``already_in_markdown``: a send
    from another day is not counted again today). It counts toward today's applications and the gap between
    sends, but a full cap doesn't block it (the send already happened). Adds the "enviada por Allan" rows to
    both Markdown logs and marks the cached job as applied.
    """
    if not _JOB_ID_RE.fullmatch(str(job_id)):
        return sb.err("bad_job_id", "job_id debe ser el número de la vacante (p. ej. 4474644406).")
    job_id = str(job_id)
    if not _VIA_RE.fullmatch(via or ""):
        return sb.err("bad_via", "via es una palabra corta en minúsculas, p. ej. ats_continue.")
    logged = [a for a in guard.applications() if a.get("job_id") == job_id]
    if logged:
        return sb.err("already_in_log", "Esta vacante ya está en el registro local.",
                      entries=[{k: a.get(k) for k in ("ts", "confirmed", "via", "manual")} for a in logged])
    try:
        in_md = [p.name for p in (config.postulaciones_md(), config.perfil_md()) if registro.has_job(p, job_id)]
    except OSError as e:
        return sb.err("logs_unreadable", f"No pude leer los registros en Markdown: {e}")
    if in_md:
        return sb.err("already_in_markdown", "Esta vacante ya tiene fila en " + " y ".join(in_md) +
                      " (¿se envió otro día?). No la cuento de nuevo hoy.")
    pos, bad = _work_tab() if (guard.get("work_tab") or {}).get("job_id") == job_id else (None, None)
    if pos and not bad:  # the tab is already on the job (Allan just pressed Continuar there): read it, no new view
        d = _js(*pos, "job_detail")
        if not d.get("_error"):
            d = _job_result(job_id, {"fetched_at": time.time(), "data": d}, from_cache=False)
    else:
        d = linkedin_get_job(job_id, refresh=True)
    if d.get("_error"):
        return d
    if d.get("job_id") != job_id or d.get("incomplete_read"):
        return sb.err("job_not_shown", "La página no muestra esta vacante; no registro nada.", tab_job_id=d.get("job_id"))
    if d.get("apply_type") != "applied" or not d.get("applied_status"):
        return sb.err("not_applied", "LinkedIn no muestra esta vacante como solicitada; no la registro.",
                      apply_type=d.get("apply_type"), applied_status=d.get("applied_status"))
    entry, logged_rows = _log_send({
        "job_id": job_id, "title": d.get("title"), "company": d.get("company"), "url": _JOB_URL.format(job_id),
        "apply_type": "applied", "via": via, "manual": True, "confirmed": True, "notes": (notes or "")[:500],
        "applied_status": d.get("applied_status"), "ats": d.get("ats") or None,
        "external_url": d.get("clean_url") or d.get("external_url") or None, "external_kind": d.get("external_kind"),
    })
    try:
        jobs.mark(job_id, apply_type="applied")
    except Exception:  # noqa: BLE001
        pass
    return {"recorded": True, "entry": entry, **logged_rows, "counters": guard.counters()}


@mcp.tool()
def linkedin_applications(since: Optional[str] = None) -> dict:
    """Applications this MCP submitted (local log), optionally since an ISO date like ``2026-10-06``."""
    rows = guard.applications(since)
    for r in rows:
        r.pop("review_text", None)
    return {"count": len(rows), "value": rows, "counters": guard.counters()}


@mcp.tool()
@_locked
def linkedin_resume_after_checkpoint(confirm: bool = False) -> dict:
    """Lift the checkpoint pause. Call only after Allan says in the chat that he resolved it in Safari.

    Re-checks the LinkedIn tabs first; if one still shows a verification, the pause stays.
    """
    if confirm is not True:
        return sb.err("confirmation_required", "Solo con confirm=True, después de que Allan confirme que resolvió "
                                                "la verificación.")
    tabs = _linkedin_tabs()
    if tabs.get("_error"):
        return tabs
    for t in tabs["value"]:
        st = _js(t["window_id"], t["tab_index"], "page_state")
        if st.get("_error"):
            continue
        reason = detect_checkpoint(st.get("url", ""), st.get("headings"), st.get("alerts"),
                                   st.get("captcha_frame", False))
        if reason:
            return {**guard.pause(reason, st.get("url", "")), "message": "La pestaña sigue mostrando una verificación."}
    return guard.resume()


if __name__ == "__main__":
    mcp.run()
