"""The record of each application: an enriched applications.jsonl entry and one row in each Markdown log.

- ``~/Documents/CV/Postulaciones-LinkedIn.md`` (``config.postulaciones_md()``): the 8-column table.
- ``perfil.md`` → "Estado de postulaciones" (``config.perfil_md()``): the 3-column table, job id inside the text.

Rows are only ever inserted at the end of each table, never rewritten. An entry is skipped when a row already
names its job (``\\b<job_id>\\b``) at the same minute, so a sync can run any number of times, while a later
re-send of the same job (after an unconfirmed attempt) still gets its own row. Writes are atomic.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from pathlib import Path
from typing import Any, Optional

POSTULACIONES_HEADER = "| Fecha y hora | Empresa | Puesto | job_id | Enlace | CV (SHA-256) | Respuestas dadas | Estado comprobado |"
PERFIL_HEADER = "| Organización / puesto | Estado | Fecha |"
POSTULACIONES_REF = "`~/Documents/CV/Postulaciones-LinkedIn.md`"


def answers_by_label(filled: dict[str, dict]) -> dict[str, Any]:
    """``answers_filled`` ({key: {label, type, value}}) as label → value, without the CV picker."""
    out: dict[str, Any] = {}
    for row in filled.values():
        if not isinstance(row, dict) or row.get("type") in ("resume", "empty"):
            continue
        label, n = row.get("label") or "?", 2
        while label in out:
            label, n = f"{row.get('label')} ({n})", n + 1
        out[label] = row.get("value")
    return out


def _cell(v: Any) -> str:
    text = ", ".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v))
    return re.sub(r"\s+", " ", text.replace("|", "/")).strip()


def _short_sha(sha: Optional[str]) -> str:
    return f"`{sha[:8]}…{sha[-7:]}`" if sha else "sin hash"


def _when(ts: str, fmt: str) -> str:
    try:
        return dt.datetime.fromisoformat(ts).strftime(fmt)
    except (TypeError, ValueError):
        return ts or ""


_NEXT_PATHS = ("prepare", "fill_all", "apply_next")


def _statuses(e: dict) -> tuple[str, str]:
    """``(Postulaciones status, perfil.md label)``, worded by how the send happened (``via``)."""
    ok = bool(e.get("confirmed"))
    check = "LinkedIn la marca enviada" if ok else "sin confirmar: comprobar en LinkedIn"
    if e.get("manual"):
        return (f"Enviada por Allan a mano ({e.get('via') or 'manual'}); LinkedIn la marca \"Solicitud enviada\"",
                f"**Enviada por Allan a mano** ({e.get('via') or 'manual'})")
    if e.get("unexpected") and e.get("via") == "submit":
        return (f"Enviada con el \"sí\" de Allan; el clic en Enviar no se pudo comprobar en el momento ({check})",
                "**Enviada**" if ok else "**Posible envío, sin confirmar**")
    if e.get("unexpected") and e.get("via") == "close":
        return (f"LinkedIn mostró la confirmación al cerrar el formulario (¿enviada desde Safari?) ({check})",
                "**Enviada desde Safari**" if ok else "**Posible envío desde Safari, sin confirmar**")
    if e.get("unexpected"):
        return (f"Enviada al pulsar Siguiente/Revisar, sin el \"sí\" de Allan ({check}); el MCP quedó en pausa",
                "**Enviada sin el sí de Allan**" if ok else "**Posible envío sin el sí de Allan, sin confirmar**")
    return (("Enviada, `confirmed: true`", "**Enviada**") if ok else
            ("Enviada sin confirmar (`confirmed: false`): comprobar en LinkedIn", "**Enviada sin confirmar**"))


def status_text(e: dict) -> str:
    return _statuses(e)[0]


def postulaciones_row(e: dict) -> str:
    res = e.get("resume") or {}
    if res.get("name"):
        cv = f"{res['name']} ({_short_sha(res.get('sha256'))}"
        cv += f", {res['sha256_source']})" if res.get("sha256_source") else ")"
    else:
        cv = "No registrado"
    link = e.get("url") or f"https://www.linkedin.com/jobs/view/{e.get('job_id')}/"
    if e.get("external_url"):
        link += f" · {e.get('external_kind') or 'externa'}: {e['external_url']}"
    answers = e.get("answers") or {}
    given = "; ".join(f"{_cell(k)}: {_cell(v)}" for k, v in answers.items()) if answers else \
        ("No las vio el MCP" if e.get("manual") else "Sin registro de respuestas")
    if e.get("follow_company") is False:
        given += ". No sigue a la empresa"
    cells = [_when(e.get("ts", ""), "%Y-%m-%d %H:%M"), _cell(e.get("company")), _cell(e.get("title")),
             str(e.get("job_id")), link, cv, given, status_text(e)]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def perfil_row(e: dict) -> str:
    res = e.get("resume") or {}
    where = f"LinkedIn {e.get('job_id')}" + (f", {e['external_kind']}" if e.get("external_kind") else "")
    label = _statuses(e)[1]
    if e.get("manual"):
        state = f"**Enviada por Allan a mano** ({_cell(e.get('via')) or 'manual'}; registro en {POSTULACIONES_REF})"
    else:
        cv = f"; CV {_cell(res['name'])}, SHA-256 {_short_sha(res.get('sha256'))}" if res.get("name") else ""
        state = f"{label} (LinkedIn Solicitud sencilla{cv}; registro en {POSTULACIONES_REF})"
    who = ", ".join(x for x in (_cell(e.get("company")), _cell(e.get("title"))) if x)
    return f"| {who} ({where}) | {state} | {_when(e.get('ts', ''), '%d/%m/%Y %H:%M')} |"


def _table_span(lines: list[str], header: str) -> Optional[tuple[int, int]]:
    """``(header_index, index_after_last_row)`` of the table that starts with ``header``."""
    for i, line in enumerate(lines):
        if line.strip() == header:
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            return i, j
    return None


def add_rows(text: str, header: str, entries: list[dict], make_row, when_fmt: str) -> tuple[str, list[str]]:
    """Append a row per entry not yet in the table (same job id and minute). ``(new_text, added_job_ids)``."""
    lines = text.splitlines()
    span = _table_span(lines, header)
    if span is None:
        raise ValueError(f"no encontré la tabla «{header[:40]}…»")
    start, end = span
    table_rows = lines[start:end]
    added, rows = [], []
    for e in entries:
        jid = str(e.get("job_id") or "")
        when = _when(e.get("ts", ""), when_fmt)
        if not re.fullmatch(r"\d{6,12}", jid):
            continue
        if any(re.search(rf"\b{jid}\b", r) and when in r for r in table_rows + rows):
            continue
        row = make_row(e)
        rows.append(row)
        added.append(jid)
    if not rows:
        return text, []
    new_lines = lines[:end] + rows + lines[end:]
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), added


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sync(entries: list[dict], postulaciones: Path, perfil: Path, dry_run: bool = False) -> dict:
    """Add the missing rows to both Markdown logs. ``{"added": {file: [job_ids]}, "diff": str}``."""
    out: dict[str, Any] = {"added": {}, "diff": ""}
    diffs = []
    for path, header, make, fmt in ((Path(postulaciones), POSTULACIONES_HEADER, postulaciones_row, "%Y-%m-%d %H:%M"),
                                    (Path(perfil), PERFIL_HEADER, perfil_row, "%d/%m/%Y %H:%M")):
        old = path.read_text(encoding="utf-8")
        new, added = add_rows(old, header, entries, make, fmt)
        out["added"][path.name] = added
        if added:
            diffs.append("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                      path.name, f"{path.name} (nuevo)")))
            if not dry_run:
                _write(path, new)
    out["diff"] = "".join(diffs)
    return out


def has_job(path: Path, job_id: str) -> bool:
    """Whether either Markdown log already names this job in a row of its table."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for header in (POSTULACIONES_HEADER, PERFIL_HEADER):
        span = _table_span(lines, header)
        if span and any(re.search(rf"\b{job_id}\b", line) for line in lines[span[0]:span[1]]):
            return True
    return False
