"""Answer bank for Easy Apply questions: propose only what is verified or approved, ask the rest.

The bank is ``references/respuestas.json`` in the postular-linkedin skill (``config.bank_json()``);
``respuestas-linkedin.md`` is generated from it with ``render_md``. Pure: no Safari, and no I/O
outside ``load``/``write``.

Rules (README, "Banco de respuestas"):
- ``preguntar`` → ``ask`` and ``confirmar`` → ``confirm``, even when LinkedIn prefilled the field.
- ``prefilled_ok`` only for a verified/approved entry whose value equals the prefilled one.
- A prefilled field with no entry → ``ask``; an empty optional field with no entry → ``leave_empty``.
- Years questions: the total-experience entry matches only its exact templates, and a qualified
  question ("… with SAP") matches only an entry that names that subject. Zero or several entries → ``ask``.
- Options are resolved here to the exact option text. Zero or several matching options → ``ask``.
"""

from __future__ import annotations

import copy
import datetime as dt
import difflib
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

from safari_bridge import norm

STATUSES = ("verificado", "aprobado", "confirmar", "preguntar")
FILLABLE = ("verificado", "aprobado")
LOCKED = ("verificado", "preguntar")  # linkedin_answers_save never changes these
CHOICE_TYPES = ("select", "radio")
ANSWER_KEYS = ("text", "number", "yes_no", "choice")

_PUNCT_RE = re.compile(r"[^a-z0-9+#./&\s-]")
_EDGE_PUNCT_RE = re.compile(r"(?<![a-z0-9])[./&-]+|[./&-]+(?![a-z0-9])")
_PLACEHOLDER_RE = re.compile(r"^((selecciona|seleccionar|select|elige|elegir|choose|escoge)( una| un| an| a)?"
                             r"( opcion| option)?|-+)?$")
_YEARS_RE = re.compile(r"(?<![a-z])(years?|anos?)(?![a-z])")
_EXP_RE = re.compile(r"(?<![a-z])(experience|experiencia)(?![a-z])")
_QUALIFIER_RE = re.compile(r"(?<![a-z])(in|en|of|de|del|on|como|as)\s+(.+)$")
_YES = {"si", "yes"}
_NO = {"no"}
_NUM = r"(\d+(?:[.,]\d+)?)"


def clean(s: Any) -> str:
    """``norm`` plus punctuation folded to spaces (``¿…?``, ``$``, parentheses), keeping ``node.js``/``s/4hana``."""
    s = norm(s).replace("'", "").replace("’", "")
    s = _PUNCT_RE.sub(" ", s)
    s = _EDGE_PUNCT_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_placeholder(option: Any) -> bool:
    return bool(_PLACEHOLDER_RE.match(clean(option)))


def real_options(field: dict) -> list[str]:
    return [o for o in field.get("options") or [] if not is_placeholder(o)]


def current_value(field: dict) -> Any:
    """The field's value with a select placeholder ("Selecciona una opción") read as empty."""
    v = field.get("value")
    if field.get("type") == "checkbox":
        return list(v or [])
    if v is None:
        return ""
    if field.get("type") == "select" and is_placeholder(v):
        return ""
    return str(v)


def is_years_question(label: str) -> bool:
    l = clean(label)
    return bool(_YEARS_RE.search(l) and _EXP_RE.search(l)) or "how many years" in l or "cuantos anos" in l


def _is_yes_no(options: list[str]) -> bool:
    keys = {clean(o) for o in options}
    return len(options) == 2 and keys <= (_YES | _NO) and bool(keys & _YES) and bool(keys & _NO)


def parse_range(option: str) -> Optional[tuple[float, float, bool, bool]]:
    """``(lo, hi, lo_inclusive, hi_inclusive)`` for a years option such as "3-5 años" or "Más de 10 años"."""
    s = norm(option).replace(",", ".")
    if re.fullmatch(r"(ninguna?|ninguno|none|no experience|sin experiencia)", s):
        return 0, 0, True, True
    m = re.search(rf"(menos de|less than|under|<)\s*{_NUM}", s)
    if m:
        return 0, float(m.group(2)), True, False
    m = re.search(rf"(mas de|more than|over|>)\s*{_NUM}", s)
    if m:
        return float(m.group(2)), math.inf, False, True
    m = re.search(rf"{_NUM}\s*(\+|o mas|or more|y mas|and above|or above)", s)
    if m:
        return float(m.group(1)), math.inf, True, True
    m = re.search(rf"{_NUM}\s*(-|–|a|to|and|y)\s*{_NUM}", s)
    if m:
        return float(m.group(1)), float(m.group(3)), True, True
    m = re.fullmatch(rf"{_NUM}( anos?| years?)?", s)
    if m:
        n = float(m.group(1))
        return n, n, True, True
    return None


def _in_range(n: float, r: tuple[float, float, bool, bool]) -> bool:
    lo, hi, lo_inc, hi_inc = r
    return (n > lo or (lo_inc and n == lo)) and (n < hi or (hi_inc and n == hi))


def _threshold(label: str) -> Optional[tuple[float, bool]]:
    """``(N, strict)`` from "at least 5 years" / "más de 3 años" / "5+ years"; None if the label has no number."""
    l = norm(label)
    m = re.search(rf"(at least|minimum of|minimum|minimo de|minimo|al menos|mas de|more than|over)\s+{_NUM}", l)
    if m:
        return float(m.group(2)), m.group(1) in ("mas de", "more than", "over")
    m = re.search(rf"{_NUM}\s*\+?\s*(years?|anos?)", l)
    if m:
        return float(m.group(1)), False
    return None


# -----------------------------------------------------------------------------
# Bank
# -----------------------------------------------------------------------------


class Bank:
    def __init__(self, data: dict):
        self.data = data
        self.entries: list[dict] = list(data.get("entries", []))
        self._pats = {e["id"]: [clean(p) for lang in ("es", "en") for p in (e.get("patterns") or {}).get(lang, [])]
                      for e in self.entries}

    def get(self, entry_id: str) -> Optional[dict]:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    def match(self, label: str) -> list[tuple[dict, int, int]]:
        """Entries whose patterns appear in ``label``, as ``(entry, start, end)`` of the longest hit each.

        A hit nested inside a longer hit of another entry is dropped, so "Jira Service Management"
        names Jira and not ITSM ("service management").
        """
        l = clean(label)
        years = is_years_question(label)
        hits = []
        for e in self.entries:
            applies = e.get("applies", "general")
            if (applies == "years" and not years) or (applies == "general" and years):
                continue
            pats = self._pats[e["id"]]
            if e.get("match") == "exact":
                if l in pats:
                    hits.append((e, 0, len(l)))
                continue
            best = None
            for p in pats:
                for m in re.finditer(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", l):
                    if best is None or m.end() - m.start() > best[1] - best[0]:
                        best = (m.start(), m.end())
            if best:
                hits.append((e, *best))
        return [h for h in hits
                if not any(o is not h and o[1] <= h[1] and h[2] <= o[2] and o[2] - o[1] > h[2] - h[1] for o in hits)]


def load(path: Path) -> Bank:
    return Bank(json.loads(Path(path).read_text(encoding="utf-8")))


def dumps(data: dict) -> str:
    """The bank as readable JSON: one key per line in each entry, lists and small objects inline."""
    one = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    lines = ["{"]
    for i, (k, v) in enumerate(data.items()):
        comma = "," if i < len(data) - 1 else ""
        if k in ("entries", "approvals") and isinstance(v, list):
            lines.append(f"  {one(k)}: [")
            for j, item in enumerate(v):
                item_comma = "," if j < len(v) - 1 else ""
                if k == "entries":
                    lines.append("    {")
                    lines += [f"      {one(ek)}: {one(ev)}" + ("," if n < len(item) - 1 else "")
                              for n, (ek, ev) in enumerate(item.items())]
                    lines.append("    }" + item_comma)
                else:
                    lines.append(f"    {one(item)}{item_comma}")
            lines.append("  ]" + comma)
        else:
            lines.append(f"  {one(k)}: {one(v)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write(data: dict, path: Path) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    tmp.replace(path)


def validate(data: dict) -> list[str]:
    """Schema problems in a bank (empty list when fine)."""
    errs, seen = [], set()
    for i, e in enumerate(data.get("entries", [])):
        where = e.get("id") or f"#{i}"
        if not e.get("id") or e["id"] in seen:
            errs.append(f"{where}: id vacío o repetido")
        seen.add(e.get("id"))
        if e.get("status") not in STATUSES:
            errs.append(f"{where}: estado {e.get('status')!r}")
        if e.get("status") == "aprobado" and not e.get("approved_on"):
            errs.append(f"{where}: aprobado sin fecha")
        pats = e.get("patterns") or {}
        if not (pats.get("es") or pats.get("en")):
            errs.append(f"{where}: sin patrones")
        if e.get("match", "term") not in ("term", "exact"):
            errs.append(f"{where}: match {e.get('match')!r}")
        if e.get("applies", "general") not in ("general", "years", "any"):
            errs.append(f"{where}: applies {e.get('applies')!r}")
        if set(e.get("answer") or {}) - set(ANSWER_KEYS):
            errs.append(f"{where}: claves de respuesta desconocidas")
        if e.get("status") in FILLABLE and not any(v not in (None, "", []) for v in (e.get("answer") or {}).values()):
            errs.append(f"{where}: {e['status']} sin respuesta")
        for k in ("source", "date"):
            if not e.get(k):
                errs.append(f"{where}: falta {k}")
    return errs


# -----------------------------------------------------------------------------
# Proposals
# -----------------------------------------------------------------------------


def _resolve(entry: dict, field: dict) -> tuple[Any, str]:
    """The value to put in ``field`` from ``entry``'s answer, or ``(None, why)``."""
    a = entry.get("answer") or {}
    ftype = field.get("type")
    label = field.get("label", "")
    years = is_years_question(label)
    number = a.get("number")
    if ftype in CHOICE_TYPES:
        opts = real_options(field)
        by_key: dict[str, list[str]] = {}
        for o in opts:
            by_key.setdefault(clean(o), []).append(o)
        if _is_yes_no(opts):
            yn = a.get("yes_no")
            if yn is None and number is not None and years:
                th = _threshold(label)
                yn = ("Sí" if (number > th[0] if th[1] else number >= th[0]) else "No") if th else \
                     ("Sí" if number > 0 else "No")
            if yn is None:
                return None, "la entrada no tiene respuesta sí/no"
            cands = ["si", "yes"] if clean(yn) in _YES else ["no"]
        elif number is not None and years:
            exact = by_key.get(clean(str(int(number))), [])
            if len(exact) == 1:
                return exact[0], ""
            ranged = [o for o in opts if (r := parse_range(o)) and _in_range(number, r)]
            if len(ranged) == 1:
                return ranged[0], ""
            return None, f"{len(ranged)} opciones contienen {int(number)}"
        else:
            cands = [clean(c) for c in (a.get("choice") or [])] + ([clean(a["text"])] if a.get("text") else [])
        for c in cands:
            hits = by_key.get(c, [])
            if len(hits) == 1:
                return hits[0], ""
        return None, "ninguna opción coincide exacto con la respuesta del banco"
    if ftype == "checkbox":
        if len(field.get("options") or []) != 1:
            return None, "grupo de casillas: necesita una lista explícita"
        yn = a.get("yes_no")
        if yn is None:
            return None, "la entrada no tiene respuesta sí/no"
        return clean(yn) in _YES, ""
    if number is not None and (ftype == "number" or years):
        return str(int(number)), ""
    if a.get("text") not in (None, ""):
        return str(a["text"]), ""
    if number is not None:
        return str(int(number)), ""
    return None, "la entrada no tiene texto para este campo"


def _same(field: dict, current: Any, value: Any) -> bool:
    if field.get("type") == "checkbox":
        return bool(current) == bool(value)
    return clean(current) == clean(value) and clean(current) != ""


def ask_via(field: dict, entry: Optional[dict], decision: str) -> Optional[str]:
    """How the skill asks: ``choice`` (AskUserQuestion, 2–4 real options), ``choice_multi`` or ``chat``."""
    if decision not in ("ask", "confirm"):
        return None
    if decision == "confirm" or (entry and entry.get("ask_via") == "chat"):
        return "chat"
    ftype = field.get("type")
    if ftype in CHOICE_TYPES:
        return "choice" if 2 <= len(real_options(field)) <= 4 else "chat"
    if ftype == "checkbox":
        return "choice_multi" if 2 <= len(field.get("options") or []) <= 4 else "chat"
    return "chat"


def propose(field: dict, bank: Bank) -> dict:
    """Decide what to do with one field: ``proposed``, ``prefilled_ok``, ``confirm``, ``ask``, ``leave_empty``, ``resume``."""
    label = field.get("label", "")
    current = current_value(field)
    out: dict[str, Any] = {"label": label, "type": field.get("type"), "required": bool(field.get("required")),
                           "current": current, "decision": "ask", "value": None, "suggested": None,
                           "entry": None, "status": None, "source": None, "basis": None, "reason": ""}
    if field.get("type") == "resume":
        out.update(decision="resume")
        return out
    entry = None
    hits = bank.match(label)
    if len(hits) > 1:
        out["reason"] = "coincide con varias entradas: " + ", ".join(h[0]["id"] for h in hits)
    elif not hits:
        if current not in ("", []):
            out["reason"] = "prellenado por LinkedIn y sin entrada en el banco"
        elif not out["required"]:
            out.update(decision="leave_empty", reason="opcional y sin entrada en el banco")
        else:
            out["reason"] = "sin entrada en el banco"
    else:
        entry, start, end = hits[0]
        out.update(entry=entry["id"], section=entry.get("section"), status=entry["status"], source=entry.get("source"),
                   basis=entry.get("basis") or None)
        qual = entry.get("qualifier_terms")
        rest = clean(label)[end:]
        qm = _QUALIFIER_RE.search(rest) if qual is not None else None
        if qm and not any(re.search(rf"(?<![a-z0-9]){re.escape(clean(t))}(?![a-z0-9])", qm.group(2)) for t in qual):
            out["reason"] = f"la pregunta pide algo más específico: «{qm.group(2)}»"
        elif entry["status"] == "preguntar":
            out["reason"] = "siempre se pregunta"
        else:
            value, why = _resolve(entry, field)
            if entry["status"] == "confirmar":
                out.update(decision="confirm", suggested=value, reason=why or "derivado: Allan lo confirma una vez")
            elif value is None:
                out["reason"] = why
            elif current not in ("", []) and _same(field, current, value):
                out.update(decision="prefilled_ok", value=value)
            elif field.get("type") == "typeahead":
                out.update(suggested=value, reason="typeahead sin sondear: lo eliges tú")
            else:
                out.update(decision="proposed", value=value)
                if current not in ("", []):
                    out["replaces"] = current
    out["ask_via"] = ask_via(field, entry, out["decision"])
    return out


# -----------------------------------------------------------------------------
# Markdown view and saving approved answers
# -----------------------------------------------------------------------------


def _fmt_date(iso: Optional[str]) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def _status_md(e: dict) -> str:
    if e["status"] == "aprobado":
        return f"aprobado {_fmt_date(e.get('approved_on'))}"
    return e["status"] + (f" ({e['status_note']})" if e.get("status_note") else "")


def _answer_md(e: dict) -> str:
    if e.get("display"):
        return e["display"]
    a = e.get("answer") or {}
    for k in ("number", "text", "yes_no"):
        if a.get(k) not in (None, ""):
            return str(a[k])
    return "—"


def render_md(data: dict) -> str:
    """``respuestas-linkedin.md``: the readable view of the bank. Generated; never edited by hand."""
    entries = data.get("entries", [])
    sec = lambda name: [e for e in entries if e.get("section") == name]  # noqa: E731
    out = [
        "# Banco de respuestas para Solicitud sencilla (LinkedIn)",
        "",
        "> **Generado desde `respuestas.json`; no lo edites a mano.** Para cambiar algo, edita el JSON o usa "
        "`linkedin_answers_save`, y vuelve a generarlo con `cli.py bank-md`.",
        "",
        data.get("intro", ""),
        "",
        "Estados:",
        "- **verificado**: está en el perfil y se usa tal cual.",
        "- **aprobado <fecha>**: Allan lo aprobó en el chat ese día; se usa tal cual.",
        "- **confirmar**: se deriva de las fechas; se usa solo después de que Allan lo confirme una vez. "
        "Al confirmarlo, cambia a \"aprobado <fecha>\".",
        "- **preguntar**: nunca se infiere; se pregunta en cada vacante. Las de 2 a 4 opciones van en "
        "AskUserQuestion; el texto libre (salario, fechas) va en el chat, nunca por la opción \"Other\".",
        "",
        "## Contacto (LinkedIn suele traerlo lleno)",
        "",
        "| Pregunta | Respuesta | Estado |",
        "|---|---|---|",
    ]
    out += [f"| {e['question']} | {_answer_md(e)} | {_status_md(e)} |" for e in sec("contacto")]
    out += ["", "## Años de experiencia (número entero)", "",
            "| Pregunta típica | Respuesta | Base | Estado |", "|---|---|---|---|"]
    out += [f"| {e['question']} | {_answer_md(e)} | {e.get('basis', '')} | {_status_md(e)} |" for e in sec("anios")]
    out += ["", "Sin evidencia (respuesta sugerida 0 o \"No\"; se confirma con Allan, nunca se infiere):"]
    out += [f"- {e['question']}." + (f" {e['notes']}" if e.get("notes") else "") for e in sec("sin_evidencia")]
    out += ["", "## Sí / No frecuentes", "", "| Pregunta | Respuesta | Estado |", "|---|---|---|"]
    out += [f"| {e['question']} | {_answer_md(e)} | {_status_md(e)} |" for e in sec("si_no")]
    for e in sec("salario"):
        out += ["", "## Salario", "", f"{e['question']}: siempre **{e['status']}**. {e.get('notes', '')}".rstrip()]
    other = [e for e in entries if e.get("section") not in ("contacto", "anios", "sin_evidencia", "si_no", "salario")]
    if other:
        out += ["", "## Otras respuestas aprobadas", "", "| Pregunta | Respuesta | Estado |", "|---|---|---|"]
        out += [f"| {e['question']} | {_answer_md(e)} | {_status_md(e)} |" for e in other]
    out += ["", "## Respuestas aprobadas por Allan", "",
            "Registro, con fecha, de cada respuesta que Allan aprobó como reutilizable.", "",
            "| Fecha | Pregunta | Respuesta |", "|---|---|---|"]
    out += [f"| {_fmt_date(a['date'])} | {a['question']} | {a['answer']} |" for a in data.get("approvals", [])]
    return "\n".join(out) + "\n"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean(s)).strip("_")[:40] or "respuesta"


def _locked_hit(bank: Bank, pattern: str) -> Optional[dict]:
    """A verified/always-ask entry that a new pattern would shadow, checked as a plain and a years question."""
    for label in (pattern, f"how many years of experience do you have with {pattern}"):
        for e, _, _ in bank.match(label):
            if e["status"] in LOCKED:
                return e
    return None


def save_entries(data: dict, items: list[dict], today: str) -> tuple[dict, str, list[str]]:
    """Apply approved answers to a copy of the bank. Returns ``(new_data, unified_diff, errors)``.

    Each item either approves an existing ``confirmar``/``aprobado`` entry (``{"id", "answer"?}``) or adds
    a new one (``{"question", "patterns": {"es", "en"}, "answer", "applies"?, "notes"?}``), always in section
    "aprobadas", so it can never pass for verified contact data.
    Nothing may change or shadow a ``verificado`` or ``preguntar`` entry: salary, start date, work mode,
    relocation and the like stay "always ask". New and approved entries get ``aprobado <today>``.
    """
    new = copy.deepcopy(data)
    bank = Bank(data)
    errors: list[str] = []
    for item in items:
        answer = item.get("answer")
        if answer is not None and (not isinstance(answer, dict) or not answer or set(answer) - set(ANSWER_KEYS)):
            errors.append(f"{item.get('id') or item.get('question')}: answer debe usar {', '.join(ANSWER_KEYS)}")
            continue
        if item.get("id") and bank.get(item["id"]):
            e = next(x for x in new["entries"] if x["id"] == item["id"])
            if e["status"] in LOCKED:
                errors.append(f"{e['id']}: es '{e['status']}' y no se cambia")
                continue
            if answer is not None:
                e["answer"] = answer
                e.pop("display", None)
            e.update(status="aprobado", approved_on=today, date=today, source="aprobado por Allan en el chat")
            if item.get("notes"):
                e["notes"] = item["notes"]
            new.setdefault("approvals", []).append({"date": today, "question": item.get("question") or e["question"],
                                                    "answer": _answer_md(e), "entry": e["id"]})
            continue
        pats = item.get("patterns") or {}
        if not item.get("question") or not (pats.get("es") or pats.get("en")) or not answer:
            errors.append(f"{item.get('question') or item.get('id')}: una entrada nueva necesita question, "
                          "patterns {es, en} y answer")
            continue
        shadowed = [h for p in (pats.get("es") or []) + (pats.get("en") or []) if (h := _locked_hit(bank, p))]
        if shadowed:
            errors.append(f"{item['question']}: choca con '{shadowed[0]['id']}' ({shadowed[0]['status']}); "
                          "eso se pregunta o ya está verificado")
            continue
        ids = {x["id"] for x in new["entries"]}
        eid, n = _slug(item["question"]), 2
        while eid in ids:
            eid, n = f"{_slug(item['question'])}_{n}", n + 1
        e = {"id": eid, "section": "aprobadas", "question": item["question"],
             "patterns": {"es": list(pats.get("es") or []), "en": list(pats.get("en") or [])},
             "match": "term", "applies": item.get("applies", "general"), "answer": answer,
             "status": "aprobado", "approved_on": today, "source": "aprobado por Allan en el chat",
             "date": today, "notes": item.get("notes", "")}
        new["entries"].append(e)
        new.setdefault("approvals", []).append({"date": today, "question": item["question"],
                                                "answer": _answer_md(e), "entry": eid})
    if not errors:
        new["updated"] = today
        errors = validate(new)
    diff = "".join(difflib.unified_diff(dumps(data).splitlines(True), dumps(new).splitlines(True),
                                        "respuestas.json", "respuestas.json (nuevo)"))
    return new, diff, errors
