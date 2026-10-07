import json
import subprocess
import sys
from pathlib import Path

import cli

ROOT = Path(__file__).resolve().parents[1]


def test_only_registered_tools_are_callable():
    for name in ("_js", "_fill_step", "_tab", "guard", "sb", "json", "linkedin_nope", "linkedin_status;rm",
                 "server.linkedin_status", "__import__"):
        r = cli.call_tool(name, {})
        assert r["_error"] and r["status"] == "not_a_tool", name


def test_tools_lists_the_mcp_tools():
    names = {t["name"] for t in cli.list_tools()}
    assert {"linkedin_status", "linkedin_get_job", "linkedin_apply_submit"} <= names
    assert all(n.startswith("linkedin_") for n in names)


def test_tests_cannot_reach_safari():
    r = cli.call_tool("linkedin_status", {})
    assert r["_error"] and r["status"] in ("safari_blocked", "not_running")


def test_arguments_are_validated_like_the_mcp():
    r = cli.call_tool("linkedin_get_job", {"job_id": "4398844859", "refresh": {"not": "a bool"}})
    assert r["_error"] and r["status"] == "tool_error"
    r = cli.call_tool("linkedin_apply_submit", {"job_id": "4398844859"})  # confirm defaults to False
    assert r["status"] == "confirmation_required"


def test_compact_shortens_but_keeps_every_key():
    raw = {"status": "stopped", "draft_detected": True, "registro_error": "x", "paused": None,
           "description": "d" * 5000, "confirmed": False, "complete": False,
           "fields": [{"label": "Currículum", "type": "resume", "value": "a.pdf",
                       "resumes": [{"name": f"cv{i}.pdf"} for i in range(60)],
                       "options": [str(i) for i in range(40)]}],
           "state": {"review_text": "r" * 9000, "errors": []}}
    out = cli.compact(raw)
    assert out["draft_detected"] is True and out["registro_error"] == "x" and out["confirmed"] is False
    assert out["complete"] is False and "paused" not in out  # None is dropped, False is not
    assert len(out["description"]) < 900 and "--full" in out["description"]
    f = out["fields"][0]
    assert len(f["resumes"]) == 3 and f["resumes_total"] == 60 and len(f["options"]) == 16
    assert len(out["state"]["review_text"]) < 2600


def test_compact_never_hides_the_selected_resume():
    resumes = [{"index": i, "name": "CV-Allan.pdf", "date": f"{i + 1}/10/2026", "selected": i == 7} for i in range(10)]
    out = cli.compact({"fields": [{"type": "resume", "resumes": resumes}]})["fields"][0]
    assert [r["index"] for r in out["resumes"]] == [0, 1, 2, 7] and out["resumes_total"] == 10


def test_command_line_rejects_helpers_and_scalars():
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "cli.py"), *a],  # noqa: E731
                                    capture_output=True, text=True, timeout=60, cwd=ROOT)
    r = run("_js", '{"win": 1, "idx": 1, "action": "click_submit"}')
    assert r.returncode == 1 and json.loads(r.stdout)["status"] == "not_a_tool"
    r = run("linkedin_get_job", '"4398844859"')
    assert r.returncode == 2 and json.loads(r.stdout)["status"] == "bad_json"
    r = run("linkedin_applications", '{"since": "2099-01-01"}')
    assert r.returncode == 0 and json.loads(r.stdout)["count"] == 0  # conftest's empty state dir
    for bad in (("linkedin_get_job", '{"job_id": "4398844859"}', "--dry-run"),   # would really navigate
                ("linkedin_applications", "{}", "{}"),                           # extra positional
                ("linkedin_applications", "{}", "--yes")):                       # unknown flag
        r = run(*bad)
        assert r.returncode == 2 and json.loads(r.stdout)["status"] == "bad_args", bad
