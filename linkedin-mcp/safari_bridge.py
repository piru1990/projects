"""Minimal AppleScript bridge to Safari for linkedin-mcp.

Copied and trimmed from ``intensegroup-claude-tools/safari-mcp/server.py`` (2026-10-06) so this
MCP keeps working on its own if that OneDrive folder goes away. Same rules as the original:

- Arguments reach AppleScript through ``argv``; they are never interpolated into the script.
- Running JavaScript needs Safari → Develop → "Allow JavaScript from Apple Events", which the
  user switches on by hand. Nothing here changes that setting.
- No quit, no window close: Safari on this Mac is shared with another person.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unicodedata
from typing import Any, Optional

OSA_TIMEOUT = 30.0
US = "\x1f"  # unit separator between fields
RS = "\x1e"  # record separator between rows


def err(status: str, message: str, **extra: Any) -> dict:
    return {"_error": True, "status": status, "message": message, **extra}


def safari_running() -> bool:
    return subprocess.run(["pgrep", "-x", "Safari"], capture_output=True).returncode == 0


def osa(script: str, *args: str, timeout: Optional[float] = None) -> dict:
    """Run an AppleScript. ``args`` reach the script as ``argv``. Returns ``{"out": str}`` or an error dict.

    ``LINKEDIN_MCP_NO_SAFARI=1`` (set by the tests, and by any review run) refuses every call, so nothing
    can reach the real browser or spend a LinkedIn view outside the real state's counters.
    """
    if os.environ.get("LINKEDIN_MCP_NO_SAFARI") == "1":
        return err("safari_blocked", "LINKEDIN_MCP_NO_SAFARI=1: Safari está bloqueado en este proceso.")
    if sys.platform != "darwin":
        return err("unsupported_platform", "linkedin-mcp only works on macOS (it drives Safari).")
    try:
        proc = subprocess.run(
            ["osascript", "-", *args],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout or OSA_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return err("timeout", f"osascript exceeded {timeout or OSA_TIMEOUT}s")
    if proc.returncode != 0:
        msg = proc.stderr.strip()
        if "-1743" in msg or "Not authorized" in msg:
            return err(
                "automation_denied",
                "macOS blocked Apple Events to Safari. Allow it in System Settings → Privacy & Security → "
                "Automation (enable Safari for the app that runs this MCP, e.g. Claude).",
                detail=msg,
            )
        if "-1728" in msg or "Can't get" in msg or "Invalid index" in msg:
            return err("tab_not_found", "Window or tab no longer exists (tab ids shift as tabs open/close).",
                       detail=msg)
        if "JavaScript" in msg and ("Apple Events" in msg or "-1708" in msg):
            return err(
                "js_from_apple_events_disabled",
                "Safari → Desarrollo → 'Permitir JavaScript desde Apple Events' está apagado. "
                "Allan lo activa a mano (pide la contraseña del Mac) y lo apaga al terminar.",
                detail=msg,
            )
        return err("osascript_failed", msg or f"exit {proc.returncode}")
    return {"out": proc.stdout.rstrip("\n")}


def parse_tab_id(tab_id: str) -> Optional[tuple[int, int]]:
    m = re.fullmatch(r"(\d+):(\d+)", (tab_id or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


_LIST_SCRIPT = """
on run argv
  set us to ASCII character 31
  set rs to ASCII character 30
  set out to ""
  tell application "Safari"
    repeat with w in windows
      set wid to id of w
      set widx to index of w
      set ci to 0
      try
        set ci to index of current tab of w
      end try
      set i to 0
      repeat with t in tabs of w
        set i to i + 1
        set u to ""
        try
          set u to URL of t
        end try
        if u is missing value then set u to ""
        set n to ""
        try
          set n to name of t
        end try
        if n is missing value then set n to ""
        set out to out & wid & us & i & us & widx & us & (i = ci) & us & u & us & n & rs
      end repeat
    end repeat
  end tell
  return out
end run
"""


def list_tabs() -> dict:
    """All Safari tabs as ``{"value": [{id, window_id, tab_index, url, title, active, selected_in_window}]}``."""
    r = osa(_LIST_SCRIPT)
    if r.get("_error"):
        return r
    tabs = []
    for row in r["out"].split(RS):
        row = row.strip("\n")
        if not row:
            continue
        wid, idx, widx, is_cur, url, title = (row.split(US) + [""] * 6)[:6]
        tabs.append({
            "id": f"{wid}:{idx}",
            "window_id": int(wid),
            "tab_index": int(idx),
            "url": url,
            "title": title,
            "active": is_cur == "true" and widx == "1",
            "selected_in_window": is_cur == "true",
        })
    return {"value": tabs}


_TAB_URL_SCRIPT = """
on run argv
  set wid to (item 1 of argv) as integer
  set ti to (item 2 of argv) as integer
  tell application "Safari"
    set u to ""
    try
      set u to URL of tab ti of window id wid
    end try
    if u is missing value then set u to ""
    set n to ""
    try
      set n to name of tab ti of window id wid
    end try
    return u & (ASCII character 31) & n
  end tell
end run
"""


def tab_meta(win: int, idx: int) -> dict:
    r = osa(_TAB_URL_SCRIPT, str(win), str(idx))
    if r.get("_error"):
        return r
    url, _, title = r["out"].partition(US)
    return {"url": url, "title": title}


_DO_JS_SCRIPT = """
on run argv
  tell application "Safari"
    set res to do JavaScript (item 3 of argv) in tab ((item 2 of argv) as integer) of window id ((item 1 of argv) as integer)
  end tell
  if res is missing value then return ""
  return res as text
end run
"""


def run_js(win: int, idx: int, js: str, timeout: float = 60) -> dict:
    return osa(_DO_JS_SCRIPT, str(win), str(idx), js, timeout=timeout)


# Make a tab the current one of its window, without raising the window. Pages ignore clicks
# while hidden (document.visibilityState != "visible"), so actions select the tab first.
_SELECT_TAB_SCRIPT = """
on run argv
  tell application "Safari"
    set w to window id ((item 1 of argv) as integer)
    set current tab of w to tab ((item 2 of argv) as integer) of w
  end tell
  return "ok"
end run
"""


def select_tab(win: int, idx: int) -> dict:
    return osa(_SELECT_TAB_SCRIPT, str(win), str(idx))


_PAGE_TEXT_SCRIPT = """
on run argv
  tell application "Safari" to return text of tab ((item 2 of argv) as integer) of window id ((item 1 of argv) as integer)
end run
"""


def page_text(win: int, idx: int) -> dict:
    """Visible text of a tab. Works without JavaScript from Apple Events."""
    return osa(_PAGE_TEXT_SCRIPT, str(win), str(idx), timeout=60)


_NAVIGATE_SCRIPT = """
on run argv
  tell application "Safari" to set URL of tab ((item 2 of argv) as integer) of window id ((item 1 of argv) as integer) to (item 3 of argv)
  return "ok"
end run
"""


def navigate(win: int, idx: int, url: str) -> dict:
    return osa(_NAVIGATE_SCRIPT, str(win), str(idx), url)


_NEW_TAB_SCRIPT = """
on run argv
  set u to item 1 of argv
  set wid to (item 2 of argv) as integer
  tell application "Safari"
    if wid > 0 then
      set w to window id wid
    else
      if (count of windows) is 0 then make new document
      set w to window 1
    end if
    set t to make new tab at end of tabs of w with properties {URL:u}
    set current tab of w to t
    return (id of w as text) & ":" & (index of t as text)
  end tell
end run
"""


def new_tab(url: str, window_id: int = 0) -> dict:
    """Open ``url`` in a new tab (in ``window_id`` if given). Returns ``{"out": "<win>:<idx>"}``."""
    return osa(_NEW_TAB_SCRIPT, url, str(window_id))


def wait_for_load(win: int, idx: int, timeout: float = 30.0) -> dict:
    """Poll ``document.readyState`` until ``complete`` (needs JavaScript from Apple Events)."""
    deadline = time.time() + timeout
    time.sleep(0.6)  # let navigation start
    last: dict = {}
    while time.time() < deadline:
        last = run_js(win, idx, "document.readyState", timeout=10)
        if last.get("_error") and last.get("status") != "timeout":
            return last
        if not last.get("_error") and last["out"] == "complete":
            return {"loaded": True}
        time.sleep(0.5)
    return {"loaded": False, "timed_out": True}


def norm(s: Any) -> str:
    """Same normalization as the JS ``norm``: no accents/bullets/NBSP, collapsed spaces, lowercase."""
    s = unicodedata.normalize("NFD", "" if s is None else str(s))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[   \t\r\n]", " ", s)
    s = re.sub(r"^[\s•·*-]+", "", s)
    s = re.sub(r"[\s*]+$", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()
