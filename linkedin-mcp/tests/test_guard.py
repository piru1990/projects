import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guard import Guard, detect_checkpoint, load_limits  # noqa: E402


class Clock:
    def __init__(self, t=1_791_300_000.0):  # 2026-10-06 local-ish
        self.t = t
        self.slept = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept += s
        self.t += s


@pytest.fixture
def guard(tmp_path):
    clock = Clock()
    g = Guard(state_dir=tmp_path, limits=load_limits({}), now=clock.now, sleep=clock.sleep)
    g.clock = clock
    return g


def test_limits_are_clamped():
    lim = load_limits({
        "LINKEDIN_MCP_MAX_APPLY_PER_DAY": "500",
        "LINKEDIN_MCP_MIN_SECONDS_BETWEEN_SUBMITS": "0",
        "LINKEDIN_MCP_MAX_JOB_VIEWS_PER_DAY": "abc",
        "LINKEDIN_MCP_MIN_SECONDS_BETWEEN_NAVIGATIONS": "-5",
    })
    assert lim == {"max_apply_per_day": 15, "min_seconds_between_submits": 60,
                   "max_job_views_per_day": 40, "min_seconds_between_navigations": 3,
                   "min_seconds_between_dialog_actions": 3}
    assert load_limits({"LINKEDIN_MCP_MIN_SECONDS_BETWEEN_DIALOG_ACTIONS": "0"})["min_seconds_between_dialog_actions"] == 2
    assert load_limits({"LINKEDIN_MCP_MIN_SECONDS_BETWEEN_DIALOG_ACTIONS": "99"})["min_seconds_between_dialog_actions"] == 30


def test_daily_cap_blocks_the_eleventh_application(guard):
    for i in range(10):
        assert guard.before_submit() is None
        guard.record_submit({"job_id": str(i)})
        guard.clock.t += 181
    bad = guard.before_submit()
    assert bad["status"] == "daily_apply_limit"
    assert len(guard.applications()) == 10


def test_cap_resets_next_day(guard):
    for i in range(10):
        guard.record_submit({"job_id": str(i)})
        guard.clock.t += 181
    guard.clock.t += 86_400
    assert guard.before_submit() is None


def test_submit_spacing(guard):
    guard.record_submit({"job_id": "1"})
    guard.clock.t += 60
    bad = guard.before_submit()
    assert bad["status"] == "too_soon" and 100 < bad["retry_after_s"] <= 121
    guard.clock.t += 121
    assert guard.before_submit() is None


def test_navigation_waits_out_the_gap_and_counts_views(guard):
    assert guard.before_navigation(True) is None
    guard.record_navigation(True)
    guard.clock.t += 2
    assert guard.before_navigation(True) is None
    assert guard.clock.slept == pytest.approx(6)
    guard.record_navigation(True)
    assert guard.counters()["job_views"] == 2


def test_view_cap(guard):
    for _ in range(40):
        guard.record_navigation(True)
    assert guard.before_navigation(True)["status"] == "daily_view_limit"
    assert guard.before_navigation(False) is None  # non-view navigation (e.g. list page) still allowed


def test_checkpoint_pauses_everything_until_resume(guard):
    reason = detect_checkpoint("https://www.linkedin.com/checkpoint/challenge/AgF123")
    assert reason
    guard.pause(reason, "https://www.linkedin.com/checkpoint/challenge/AgF123")
    assert guard.before_navigation(False)["status"] == "paused_checkpoint"
    assert guard.before_submit()["status"] == "paused_checkpoint"
    guard.resume()
    assert guard.before_submit() is None


@pytest.mark.parametrize("url,headings,alerts,captcha,hit", [
    ("https://www.linkedin.com/authwall?trk=x", [], [], False, True),
    ("https://www.linkedin.com/login", [], [], False, True),
    ("https://www.linkedin.com/jobs/view/123/", ["Hagamos una verificación de seguridad rápida"], [], False, True),
    ("https://www.linkedin.com/jobs/view/123/", [], ["You’ve reached the Easy Apply application limit for today"], False, True),
    ("https://www.linkedin.com/jobs/view/123/", [], [], True, True),
    ("https://www.linkedin.com/jobs/view/123/", ["Analista de Ciberseguridad"], [], False, False),
    ("https://www.linkedin.com/jobs/search-results/?keywords=jobs", ["Empleos"], [], False, False),
])
def test_detect_checkpoint(url, headings, alerts, captcha, hit):
    assert bool(detect_checkpoint(url, headings, alerts, captcha)) is hit


def test_lock_is_exclusive(guard):
    with guard.lock() as first:
        assert first is None
        other = Guard(state_dir=guard.dir, limits=guard.limits)
        with other.lock() as second:
            assert second["status"] == "busy"
    with Guard(state_dir=guard.dir).lock() as again:
        assert again is None


def test_lock_is_reentrant_for_its_thread_only(guard):
    import subprocess
    import threading

    seen = {}
    with guard.lock() as outer:
        assert outer is None
        with guard.lock() as inner:  # a compound tool calling a single-step tool
            assert inner is None

            def other_thread():
                with guard.lock() as r:
                    seen["thread"] = r

            t = threading.Thread(target=other_thread)
            t.start()
            t.join()
            code = ("import sys; sys.path.insert(0, %r); from guard import Guard; "
                    "from pathlib import Path\nwith Guard(state_dir=Path(%r)).lock() as r: print(r and r['status'])"
                    % (str(Path(__file__).resolve().parents[1]), str(guard.dir)))
            seen["process"] = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
        with guard.lock() as still:  # the outer hold survives the inner exit
            assert still is None
    assert seen["thread"]["status"] == "busy" and seen["process"] == "busy"
    with Guard(state_dir=guard.dir).lock() as free:
        assert free is None


def test_dialog_actions_keep_a_fixed_gap(guard):
    guard.before_dialog_action()
    start = guard.clock.t
    guard.before_dialog_action()
    assert guard.clock.t - start == 3  # waited the full gap, no jitter
    guard.clock.t += 10
    before = guard.clock.t
    guard.before_dialog_action()
    assert guard.clock.t == before  # already spaced: no wait
