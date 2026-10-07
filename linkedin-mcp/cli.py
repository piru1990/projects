#!/usr/bin/env python3
"""Bash fallback for linkedin-mcp when the ``mcp__linkedin__*`` tools aren't loaded (or to try new JS).

    .venv/bin/python cli.py tools                          # list the tools
    .venv/bin/python cli.py <tool> ['<json args>'] [--full]
    .venv/bin/python cli.py bank-md [--dry-run]            # respuestas.json → respuestas-linkedin.md
    .venv/bin/python cli.py registro-sync [--dry-run]      # missing rows → Postulaciones-LinkedIn.md and perfil.md

Only tools registered in the MCP can be called, and they go through FastMCP's own call path (same
argument validation, same decorated functions), so the lock, the pause, the linkedin.com check and
every ``confirm=True`` rule apply exactly as in the MCP. Helpers like ``_js`` are not reachable.
``server`` is imported on each run, so it reads the current ``linkedin.js`` (the MCP reads it once).

The output is compact: long texts are cut, field lists trimmed and resume lists reduced to the top 3,
but no key is dropped, so errors and stop states always show. ``--full`` prints everything.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TOOL_NAME_RE = re.compile(r"linkedin_[a-z_]+")
_DRY_RUN_COMMANDS = ("bank-md", "registro-sync")
_TEXT_LIMITS = {"description": 800, "company_about": 300, "review_text": 2500, "success_text": 300}
_TEXT_DEFAULT = 2000
_MAX_OPTIONS = 15
_TOP_RESUMES = 3


def _cut(s: str, limit: int) -> str:
    return s if len(s) <= limit else f"{s[:limit]} …[+{len(s) - limit} caracteres; usa --full]"


def compact(value: Any, key: str = "") -> Any:
    """Shorten without hiding: texts are cut, option and resume lists trimmed, None and "" dropped."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if v is None or v == "":
                continue
            if k == "resumes" and isinstance(v, list):
                keep = [x for i, x in enumerate(v)
                        if i < _TOP_RESUMES or (isinstance(x, dict) and x.get("selected"))]  # never hide the selected one
                out[k] = [compact(x) for x in keep]
                if len(v) > len(keep):
                    out["resumes_total"] = len(v)
                continue
            if k == "options" and isinstance(v, list) and len(v) > _MAX_OPTIONS:
                out[k] = v[:_MAX_OPTIONS] + [f"…(+{len(v) - _MAX_OPTIONS})"]
                continue
            out[k] = compact(v, k)
        return out
    if isinstance(value, list):
        return [compact(x, key) for x in value]
    if isinstance(value, str):
        return _cut(value, _TEXT_LIMITS.get(key, _TEXT_DEFAULT))
    return value


def _rejected(name: str, why: str) -> dict:
    return {"_error": True, "status": "not_a_tool", "message": f"{name!r} no es una tool del MCP: {why}"}


def call_tool(name: str, args: dict) -> dict:
    """Run one registered MCP tool the way the MCP does. Anything else is refused."""
    if not _TOOL_NAME_RE.fullmatch(name):
        return _rejected(name, "solo se aceptan nombres linkedin_* (las funciones internas no se exponen).")
    import server
    from mcp.server.fastmcp.exceptions import ToolError

    mgr = server.mcp._tool_manager
    if mgr.get_tool(name) is None:
        return _rejected(name, "usa `cli.py tools` para ver la lista.")
    try:
        return asyncio.run(mgr.call_tool(name, args))
    except ToolError as e:
        return {"_error": True, "status": "tool_error", "message": str(e)}


def list_tools() -> list[dict]:
    import server
    return [{"name": t.name, "doc": (t.description or "").strip().splitlines()[0]}
            for t in server.mcp._tool_manager.list_tools()]


def bank_md(dry_run: bool) -> dict:
    """Regenerate respuestas-linkedin.md from respuestas.json, under the same lock as the tools."""
    import difflib

    import answers
    import config
    from guard import Guard

    with Guard().lock() as busy:
        if busy:
            return busy
        data = answers.load(config.bank_json()).data
        errors = answers.validate(data)
        if errors:
            return {"_error": True, "status": "bank_invalid", "message": "respuestas.json tiene errores.",
                    "errors": errors}
        md_path = config.bank_md()
        new = answers.render_md(data)
        old = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            md_path.name, f"{md_path.name} (generado)"))
        if not dry_run and diff:
            tmp = md_path.with_suffix(".md.tmp")
            tmp.write_text(new, encoding="utf-8")
            tmp.replace(md_path)
        return {"status": "dry_run" if dry_run else ("written" if diff else "unchanged"),
                "path": str(md_path), "diff": diff}


def _usage_error(message: str) -> int:
    print(json.dumps({"_error": True, "status": "bad_args", "message": message}, ensure_ascii=False))
    return 2


def registro_sync(dry_run: bool) -> dict:
    """Add the rows missing from both Markdown logs for every entry of applications.jsonl (insert-only)."""
    import config
    import registro
    from guard import Guard

    g = Guard()
    with g.lock() as busy:
        if busy:
            return busy
        r = registro.sync(g.applications(), config.postulaciones_md(), config.perfil_md(), dry_run=dry_run)
        added = any(r["added"].values())
        return {"status": "dry_run" if dry_run else ("written" if added else "unchanged"), "added": r["added"],
                "diff": r["diff"]}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    flags = [a for a in rest if a.startswith("--")]
    args = [a for a in rest if not a.startswith("--")]
    unknown = [f for f in flags if f not in ("--full", "--dry-run")]
    if unknown:
        return _usage_error(f"Opción desconocida: {', '.join(unknown)}.")
    if "--dry-run" in flags and cmd not in _DRY_RUN_COMMANDS:
        return _usage_error(f"--dry-run solo vale para {', '.join(_DRY_RUN_COMMANDS)}; con una tool, la tool se "
                            "ejecuta de verdad.")
    if len(args) > (0 if cmd in ("tools",) + _DRY_RUN_COMMANDS else 1):
        return _usage_error("Sobran argumentos: va un solo objeto JSON entre comillas simples después de la tool.")
    full, dry_run = "--full" in flags, "--dry-run" in flags
    if cmd == "tools":
        result: Any = list_tools()
    elif cmd in ("bank-md", "registro-sync"):
        result = bank_md(dry_run) if cmd == "bank-md" else registro_sync(dry_run)
        if result.get("diff") and not full:
            print(result.pop("diff"))
    else:
        try:
            params = json.loads(args[0]) if args else {}
        except ValueError as e:
            print(json.dumps({"_error": True, "status": "bad_json", "message": str(e)}, ensure_ascii=False))
            return 2
        if not isinstance(params, dict):
            print(json.dumps({"_error": True, "status": "bad_json",
                              "message": "Los argumentos van como un objeto JSON, p. ej. '{\"job_id\": \"123\"}'."}))
            return 2
        result = call_tool(cmd, params)
    print(json.dumps(result if full else compact(result), ensure_ascii=False, indent=1))
    return 1 if isinstance(result, dict) and result.get("_error") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
