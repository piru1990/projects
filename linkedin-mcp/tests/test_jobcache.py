import pytest

import server
from guard import Guard, load_limits
from jobcache import JobCache


class Clock:
    def __init__(self, t=1_791_300_000.0):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_cache_put_get_expire_mark_invalidate(tmp_path):
    clock = Clock()
    c = JobCache(tmp_path, now=clock.now)
    assert c.get("4398844859") is None
    c.put("4398844859", {"title": "Jefe de Proyectos", "apply_type": "easy_apply"})
    assert c.get("4398844859")["data"]["title"] == "Jefe de Proyectos"
    c.mark("4398844859", apply_type="applied")
    assert c.get("4398844859")["data"]["apply_type"] == "applied"
    assert list(c.fresh()) == ["4398844859"]
    clock.t += 24 * 3600 + 1
    assert c.get("4398844859") is None and c.fresh() == {}
    c.invalidate("4398844859")
    c.invalidate("4398844859")  # twice is fine
    assert not (tmp_path / "jobs" / "4398844859.json").exists()


def test_cache_refuses_paths_that_are_not_job_ids(tmp_path):
    c = JobCache(tmp_path)
    for bad in ("../state", "12ab", ""):
        with pytest.raises(ValueError):
            c.put(bad, {})


DETAIL = {"job_id": "4398844859", "url": "https://www.linkedin.com/jobs/view/4398844859/",
          "company": "cbc", "title": "21004040 Jefe de Proyectos de Sistemas", "meta": "", "chips": [],
          "apply_type": "ats_continue", "applied_status": "", "external_url": "", "ats": "SmartRecruiters",
          "apply_url": "https://www.linkedin.com/jobs/view/4398844859/?applicantTrackingSystemName=SmartRecruiters",
          "description": "x" * 50, "company_about": ""}


@pytest.fixture
def fake_safari(tmp_path, monkeypatch):
    """server.linkedin_get_job with Safari replaced by counters; nothing touches the real browser or state."""
    clock = Clock()
    g = Guard(state_dir=tmp_path, limits=load_limits({}), now=clock.now, sleep=clock.sleep)
    calls = {"navigate": 0}
    monkeypatch.setattr(server, "guard", g)
    monkeypatch.setattr(server, "jobs", JobCache(tmp_path, now=clock.now))
    monkeypatch.setattr(server, "_work_tab", lambda: ((7, 2), None))
    monkeypatch.setattr(server, "_checkpoint", lambda win, idx: None)

    def navigate(win, idx, url):
        calls["navigate"] += 1
        calls["url"] = url
        return {"out": ""}

    monkeypatch.setattr(server.sb, "navigate", navigate)
    monkeypatch.setattr(server.sb, "wait_for_load", lambda win, idx, timeout=30: {})
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server, "_js", lambda win, idx, action, arg=None, select=False:
                        dict(DETAIL) if action == "job_detail" else {})
    calls["clock"] = clock
    return calls


def test_get_job_reads_once_then_from_cache(fake_safari):
    first = server.linkedin_get_job("4398844859")
    assert first["from_cache"] is False and first["tab_id"] == "7:2" and first["on_work_tab"] is True
    assert first["external_kind"] == "ats:smartrecruiters" and first["account_hint"] == "a_veces"
    assert first["counters"]["job_views"] == 1 and fake_safari["navigate"] == 1
    again = server.linkedin_get_job("4398844859")
    assert again["from_cache"] is True and "tab_id" not in again
    assert again["counters"]["job_views"] == 1 and fake_safari["navigate"] == 1
    assert again["external_kind"] == "ats:smartrecruiters"


def test_refresh_and_expiry_navigate_again(fake_safari):
    server.linkedin_get_job("4398844859")
    fake_safari["clock"].t += 60
    assert server.linkedin_get_job("4398844859", refresh=True)["from_cache"] is False
    assert fake_safari["navigate"] == 2
    fake_safari["clock"].t += 24 * 3600 + 1
    assert server.linkedin_get_job("4398844859")["from_cache"] is False
    assert fake_safari["navigate"] == 3
    assert server.guard.counters()["job_views"] == 1  # a day later: the daily counter started over


def test_cached_job_knows_the_work_tab_moved(fake_safari):
    server.linkedin_get_job("4398844859")
    server.guard.set("work_tab", {"id": "7:2", "window_id": 7, "job_id": "4468912423"})
    cached = server.linkedin_get_job("4398844859")
    assert cached["from_cache"] is True and cached["on_work_tab"] is False
    start = server.linkedin_apply_start("4398844859")
    assert start["status"] == "open_job_first" and "refresh=True" in start["message"]


def test_cached_job_recomputes_the_local_log(fake_safari):
    server.linkedin_get_job("4398844859")
    assert server.linkedin_get_job("4398844859")["in_local_log"] is False
    server.guard.record_submit({"job_id": "4398844859"})
    assert server.linkedin_get_job("4398844859")["in_local_log"] is True


def test_bad_job_id_never_reaches_the_cache_or_safari(fake_safari):
    for bad in ("../state", "4398844859\n", "12345"):
        assert server.linkedin_get_job(bad)["status"] == "bad_job_id", repr(bad)
    assert fake_safari["navigate"] == 0


def test_a_read_that_is_not_this_job_is_never_cached(fake_safari, monkeypatch):
    other = dict(DETAIL, job_id="4468912423", title="Otra vacante", company="OtraCo", apply_type="easy_apply")
    monkeypatch.setattr(server, "_js", lambda win, idx, action, arg=None, select=False:
                        dict(other) if action == "job_detail" else {})
    monkeypatch.setattr(server, "_poll", lambda fn, ok, timeout, step=0.8: fn())  # one read, as after a timeout
    first = server.linkedin_get_job("4398844859")
    assert first["incomplete_read"] is True and "refresh=True" in first["message"]
    again = server.linkedin_get_job("4398844859")
    assert again["from_cache"] is False and fake_safari["navigate"] == 2  # it read the page again
    assert server.jobs.get("4398844859") is None


def test_cached_read_warns_about_another_open_application(fake_safari):
    server.linkedin_get_job("4398844859")
    server.guard.set("current_application", {"job_id": "4468912423", "title": "Service Manager"})
    r = server.linkedin_get_job("4398844859")
    assert r["from_cache"] is True and r["application_in_progress"]["job_id"] == "4468912423"
    server.guard.set("current_application", {"job_id": "4398844859"})
    assert "application_in_progress" not in server.linkedin_get_job("4398844859")


def test_malformed_cache_files_are_ignored(tmp_path):
    c = JobCache(tmp_path)
    (tmp_path / "jobs").mkdir()
    for i, body in enumerate(('[]', '{"fetched_at": "x", "data": {}}', '{"fetched_at": 1, "data": []}', 'nope')):
        (tmp_path / "jobs" / f"43988448{i:02d}.json").write_text(body)
        assert c.get(f"43988448{i:02d}") is None
        c.mark(f"43988448{i:02d}", apply_type="applied")  # no exception
    assert c.fresh() == {}


def test_get_job_waits_for_the_description(fake_safari, monkeypatch):
    reads = {"n": 0}

    def js(win, idx, action, arg=None, select=False):
        if action != "job_detail":
            return {}
        reads["n"] += 1
        return dict(DETAIL, description="" if reads["n"] < 3 else "Buscamos un Tech Lead…")

    monkeypatch.setattr(server, "_js", js)
    r = server.linkedin_get_job("4398844859")
    assert r["description"] == "Buscamos un Tech Lead…"
    assert server.jobs.get("4398844859")["data"]["description"] == "Buscamos un Tech Lead…"
