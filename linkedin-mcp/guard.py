"""Pacing, daily caps, checkpoint pause, single-operation lock and the local application log.

The point is to keep the account's activity at the level of a careful person: few job views, few
applications, nothing in parallel, and a full stop the moment LinkedIn asks for a verification.
It does not try to disguise automation (no random jitter, no user-agent games).

State lives in ``~/.cache/linkedin-mcp/`` (override with ``LINKEDIN_MCP_STATE_DIR``):
- ``state.json``: today's counters, last navigation/submit timestamps, checkpoint pause.
- ``applications.jsonl``: one line per submitted application.
- ``lock``: ``fcntl`` lock so the MCP and a Bash fallback never act at the same time.

The lock is re-entrant within one thread (compound tools call the single-step ones) and exclusive
across threads and processes.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

# (env var, default, hard floor, hard ceiling)
_LIMITS = {
    "max_apply_per_day": ("LINKEDIN_MCP_MAX_APPLY_PER_DAY", 10, 1, 15),
    "min_seconds_between_submits": ("LINKEDIN_MCP_MIN_SECONDS_BETWEEN_SUBMITS", 180, 60, 3600),
    "max_job_views_per_day": ("LINKEDIN_MCP_MAX_JOB_VIEWS_PER_DAY", 40, 1, 60),
    "min_seconds_between_navigations": ("LINKEDIN_MCP_MIN_SECONDS_BETWEEN_NAVIGATIONS", 8, 3, 120),
    # Clicks and typing inside the Easy Apply dialog: a fixed gap, never random.
    "min_seconds_between_dialog_actions": ("LINKEDIN_MCP_MIN_SECONDS_BETWEEN_DIALOG_ACTIONS", 3, 2, 30),
}


def load_limits(env: Optional[dict] = None) -> dict:
    """Read limits from the environment, clamped to the hard floor/ceiling so a typo can't remove them."""
    env = os.environ if env is None else env
    out = {}
    for key, (var, default, lo, hi) in _LIMITS.items():
        try:
            val = int(float(env.get(var, default)))
        except (TypeError, ValueError):
            val = default
        out[key] = max(lo, min(hi, val))
    return out


def default_state_dir() -> Path:
    return Path(os.environ.get("LINKEDIN_MCP_STATE_DIR") or Path.home() / ".cache" / "linkedin-mcp")


# ---------------------------------------------------------------------------
# Checkpoint detection (pure, so it can be unit tested)
# ---------------------------------------------------------------------------

_CHECKPOINT_URL_RE = re.compile(r"linkedin\.com/(checkpoint|authwall|uas/|login|signup|m/login)", re.I)

# Matched only against page/dialog headings and alerts, never against a job description,
# so a security-role posting that mentions "verificación de seguridad" does not trip it.
_CHECKPOINT_TEXT = [
    "verificacion de seguridad", "comprobacion de seguridad", "control de seguridad",
    "security verification", "security check", "captcha", "no soy un robot", "i'm not a robot",
    "verifica que eres una persona", "verify you are human", "let's confirm it's you", "confirma que eres tu",
    "cuenta restringida", "restringido temporalmente", "restringida temporalmente",
    "account has been restricted", "temporarily restricted",
    "limite de solicitudes", "limite diario", "alcanzado el limite", "reached the limit",
    "reached the daily limit", "application limit",
]


def _fold(s: Any) -> str:
    s = unicodedata.normalize("NFD", "" if s is None else str(s))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()


def detect_checkpoint(url: str, headings: Optional[list] = None, alerts: Optional[list] = None,
                      captcha_frame: bool = False) -> Optional[str]:
    """Return a short reason if the page looks like a LinkedIn verification/limit/sign-in wall."""
    if url and _CHECKPOINT_URL_RE.search(url):
        return f"url:{url}"
    if captcha_frame:
        return "captcha_frame"
    for chunk in list(headings or []) + list(alerts or []):
        t = _fold(chunk)
        for needle in _CHECKPOINT_TEXT:
            if needle in t:
                return f"text:{needle}"
    return None


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class Guard:
    def __init__(self, state_dir: Optional[Path] = None, limits: Optional[dict] = None,
                 now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        self.dir = Path(state_dir) if state_dir else default_state_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.limits = limits or load_limits()
        self.now = now
        self.sleep = sleep
        self.state_path = self.dir / "state.json"
        self.log_path = self.dir / "applications.jsonl"
        self.lock_path = self.dir / "lock"
        self._lock_owner: Optional[int] = None
        self._lock_depth = 0

    # ---- state ----
    def _today(self) -> str:
        return dt.datetime.fromtimestamp(self.now()).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            st = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            st = {}
        st.setdefault("last_nav_ts", 0.0)
        st.setdefault("last_submit_ts", 0.0)
        st.setdefault("last_dialog_ts", 0.0)
        st.setdefault("paused", None)
        st.setdefault("work_tab", None)
        if st.get("date") != self._today():
            st.update(date=self._today(), views=0, applies=0)
        return st

    def _save(self, st: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        tmp.replace(self.state_path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        st = self._load()
        st[key] = value
        self._save(st)

    def counters(self) -> dict:
        st = self._load()
        now = self.now()
        return {
            "date": st["date"],
            "job_views": st["views"],
            "job_views_left": max(0, self.limits["max_job_views_per_day"] - st["views"]),
            "applications": st["applies"],
            "applications_left": max(0, self.limits["max_apply_per_day"] - st["applies"]),
            "next_submit_in_s": max(0, int(st["last_submit_ts"] + self.limits["min_seconds_between_submits"] - now)),
            "paused": st["paused"],
            "limits": self.limits,
        }

    # ---- checkpoint pause ----
    def paused_error(self) -> Optional[dict]:
        p = self._load()["paused"]
        if not p:
            return None
        return {
            "_error": True, "status": "paused_checkpoint",
            "message": "LinkedIn pidió una verificación o mostró un límite. Todo está en pausa: Allan la resuelve "
                       "a mano en Safari y, cuando lo diga en el chat, se llama a linkedin_resume_after_checkpoint.",
            "paused": p,
        }

    def pause(self, reason: str, url: str = "") -> dict:
        st = self._load()
        st["paused"] = {"reason": reason, "url": url,
                        "since": dt.datetime.fromtimestamp(self.now()).isoformat(timespec="seconds")}
        self._save(st)
        return self.paused_error()

    def resume(self) -> dict:
        st = self._load()
        was = st["paused"]
        st["paused"] = None
        self._save(st)
        return {"resumed": True, "was": was}

    # ---- pacing ----
    def before_navigation(self, counts_as_view: bool) -> Optional[dict]:
        """Refuse when paused or out of views; otherwise wait out the minimum gap since the last navigation."""
        bad = self.paused_error()
        if bad:
            return bad
        st = self._load()
        if counts_as_view and st["views"] >= self.limits["max_job_views_per_day"]:
            return {"_error": True, "status": "daily_view_limit",
                    "message": f"Ya se abrieron {st['views']} vacantes hoy (límite "
                               f"{self.limits['max_job_views_per_day']}). Sigue mañana.",
                    "date": st["date"]}
        wait = st["last_nav_ts"] + self.limits["min_seconds_between_navigations"] - self.now()
        if wait > 0:
            self.sleep(wait)
        return None

    def record_navigation(self, counts_as_view: bool) -> None:
        st = self._load()
        st["last_nav_ts"] = self.now()
        if counts_as_view:
            st["views"] += 1
        self._save(st)

    def before_dialog_action(self) -> None:
        """Wait out the fixed gap since the last click or fill in the Easy Apply dialog, then stamp this one."""
        st = self._load()
        wait = st["last_dialog_ts"] + self.limits["min_seconds_between_dialog_actions"] - self.now()
        if wait > 0:
            self.sleep(wait)
        st = self._load()
        st["last_dialog_ts"] = self.now()
        self._save(st)

    def before_submit(self) -> Optional[dict]:
        bad = self.paused_error()
        if bad:
            return bad
        st = self._load()
        if st["applies"] >= self.limits["max_apply_per_day"]:
            return {"_error": True, "status": "daily_apply_limit",
                    "message": f"Ya se enviaron {st['applies']} solicitudes hoy (límite "
                               f"{self.limits['max_apply_per_day']}). Sigue mañana.",
                    "date": st["date"]}
        wait = st["last_submit_ts"] + self.limits["min_seconds_between_submits"] - self.now()
        if wait > 0:
            return {"_error": True, "status": "too_soon",
                    "message": f"Faltan {int(wait) + 1} s para el siguiente envío "
                               f"(mínimo {self.limits['min_seconds_between_submits']} s entre envíos).",
                    "retry_after_s": int(wait) + 1}
        return None

    def record_submit(self, entry: dict) -> dict:
        st = self._load()
        st["applies"] += 1
        st["last_submit_ts"] = self.now()
        self._save(st)
        entry = {"ts": dt.datetime.fromtimestamp(self.now()).isoformat(timespec="seconds"), **entry}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def applications(self, since: Optional[str] = None) -> list[dict]:
        if not self.log_path.exists():
            return []
        rows = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if since and row.get("ts", "") < since:
                continue
            rows.append(row)
        return rows

    # ---- one operation at a time ----
    @contextlib.contextmanager
    def lock(self) -> Iterator[Optional[dict]]:
        """Yield ``None`` when the lock is held, or a ``busy`` error dict if another operation runs.

        Re-entrant for the thread that holds it, so a compound tool can call the single-step tools.
        Another thread or process (the Bash fallback) still gets ``busy``.
        """
        me = threading.get_ident()
        if self._lock_depth and self._lock_owner == me:
            self._lock_depth += 1
            try:
                yield None
            finally:
                self._lock_depth -= 1
            return
        fh = self.lock_path.open("a+")
        try:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield {"_error": True, "status": "busy",
                       "message": "Otra operación de linkedin-mcp está en curso. Espera a que termine."}
                return
            self._lock_owner, self._lock_depth = me, 1
            try:
                yield None
            finally:
                self._lock_owner, self._lock_depth = None, 0
                fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()
