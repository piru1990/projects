"""One step of the Easy Apply dialog, planned: what to fill, what to keep and what needs Allan. Pure.

Fields are keyed ``"<job_id>:<step>|<label>|<n>"`` (the label as ``answers.clean`` folds it, ``n`` its
occurrence on that step), so an answer can never land on a same-named question of another step or another
job. ``linkedin_apply_prepare`` returns these keys; ``linkedin_apply_fill_all`` takes answers by them.

Rules (README, "prepare y fill_all"):
- A field with an answer from Allan gets exactly that answer; for options it must equal one option.
- Without an answer: ``prefilled_ok`` is kept and an empty optional field with no entry stays empty.
- On a step ``prepare`` never saw, only verified contact data is filled from the bank; anything else stops.
- A field LinkedIn marks with an error is asked, whatever the bank says.
- Typeahead fields are never typed by the tool (not probed yet): Allan fills them in Safari.
- A label that repeats on the same step is never filled by the tool (modal_fill fills by label): Allan fills
  it in Safari, and an answer equal to what is on screen is then kept.
"""

from __future__ import annotations

from typing import Any, Optional

import answers as A

KEEP = ("prefilled_ok", "leave_empty")
_ITEM_KEYS = ("key", "step", "label", "type", "required", "options", "max_length", "current", "decision", "value",
              "suggested", "entry", "status", "source", "basis", "reason", "ask_via", "error", "replaces")


def field_keys(fields: list[dict], step: int, prefix: str = "") -> list[str]:
    seen: dict[str, int] = {}
    keys = []
    for f in fields:
        lab = A.clean(f.get("label"))
        n = seen.get(lab, 0)
        seen[lab] = n + 1
        keys.append(f"{prefix}{step}|{lab}|{n}")
    return keys


def _label_of(key: str) -> str:
    return key.rsplit("|", 2)[-2]


def resume_item(field: dict, resume_name: str) -> dict:
    """The resume picker as a questionnaire row: keep, select the chosen file, or it must be uploaded first."""
    rs = field.get("resumes") or []
    sel = next((r for r in rs if r.get("selected")), None)
    hits = [r for r in rs if r.get("name") == resume_name]  # LinkedIn lists the most recent first: hits[0]
    item: dict[str, Any] = {"label": field.get("label") or "Currículum", "type": "resume",
                            "required": bool(field.get("required")), "chosen": resume_name,
                            "selected": {k: sel.get(k) for k in ("index", "name", "date")} if sel else None,
                            "available": [{k: r.get(k) for k in ("index", "name", "date")} for r in hits],
                            "resumes_total": len(rs)}
    if sel and hits and sel.get("index") == hits[0].get("index"):  # an older same-name upload doesn't count
        item.update(decision="prefilled_ok", value=resume_name)
    elif hits:
        item.update(decision="select", value=resume_name, reason="el CV elegido no está seleccionado")
    else:
        item.update(decision="upload_needed", reason="el CV elegido no está en LinkedIn: hay que subirlo con tu ok",
                    ask_via="chat")
    return item


def questionnaire(fields: list[dict], step: int, bank: A.Bank, resume_name: str, prefix: str = "") -> list[dict]:
    """Every field of a step with the bank's proposal, keyed. Repeated labels and LinkedIn errors are asked."""
    keys = field_keys(fields, step, prefix)
    labels = [_label_of(k) for k in keys]
    items = []
    for key, f in zip(keys, fields):
        if f.get("type") == "resume":
            it = resume_item(f, resume_name)
        else:
            it = A.propose(f, bank)
            if labels.count(_label_of(key)) > 1:
                it.update(decision="ask", value=None, reason="la etiqueta se repite en este paso",
                          ask_via=A.ask_via(f, None, "ask"))
            elif f.get("error") and it["decision"] != "ask":
                it.update(decision="ask", suggested=it.get("value") or it.get("suggested"), value=None,
                          reason=f"LinkedIn marca: {f['error']}", ask_via=A.ask_via(f, None, "ask"))
            if f.get("options"):
                it["options"] = A.real_options(f)
            if f.get("max_length"):
                it["max_length"] = f["max_length"]
            if f.get("error"):
                it["error"] = f["error"]
        it.update(key=key, step=step)
        items.append(it)
    return items


def public_item(it: dict) -> dict:
    """A questionnaire row without empty keys, for the tool output."""
    out = {k: it[k] for k in _ITEM_KEYS if it.get(k) not in (None, "", [])}
    for k in ("chosen", "selected", "available", "resumes_total"):
        if k in it:
            out[k] = it[k]
    if "required" in it:
        out["required"] = it["required"]
    return out


def needs_decision(items: list[dict]) -> list[dict]:
    return [it for it in items if it["decision"] not in KEEP]


def check_answer(field: dict, value: Any) -> tuple[bool, Any]:
    """``(True, value to fill)`` or ``(False, why)``: options by exact text, lengths, checkbox shapes."""
    ftype = field.get("type")
    if ftype in A.CHOICE_TYPES:
        hits = [o for o in A.real_options(field) if A.clean(o) == A.clean(value)]
        return (True, hits[0]) if len(hits) == 1 else (False, f"«{value}» no es una de las opciones")
    if ftype == "checkbox":
        opts = field.get("options") or []
        if len(opts) == 1 and isinstance(value, bool):
            return True, value
        if isinstance(value, list):
            exact = [next((o for o in opts if A.clean(o) == A.clean(v)), None) for v in value]
            if all(exact):
                return True, exact
        return False, "las casillas necesitan sí/no (una sola) o la lista exacta de opciones"
    if ftype == "typeahead":
        return False, "campo con sugerencias (typeahead): lo llenas tú en Safari"
    text = "" if value is None else str(value)
    if field.get("max_length") and len(text) > field["max_length"]:
        return False, f"pasa de {field['max_length']} caracteres ({len(text)})"
    return True, text


def same(field: dict, current: Any, value: Any) -> bool:
    if field.get("type") == "checkbox":
        if isinstance(value, bool):
            return bool(current) == value
        return sorted(A.clean(v) for v in current or []) == sorted(A.clean(v) for v in value or [])
    return A.clean(current) == A.clean(value) and (A.clean(value) != "" or current in ("", None))


def plan_step(fields: list[dict], step: int, answers: dict[str, Any], resume_name: str,
              prepared_keys: set[str], bank: A.Bank, prefix: str = "") -> dict:
    """What fill_all does on this step: ``fill`` {exact label: value}, ``select_resume``, ``kept``, ``stop``."""
    items = questionnaire(fields, step, bank, resume_name, prefix)
    plan: dict[str, Any] = {"items": items, "fill": {}, "fill_keys": {}, "select_resume": None, "kept": {}, "stop": []}
    for it, f in zip(items, fields):
        key = it["key"]
        if it["type"] == "resume":
            if it["decision"] == "prefilled_ok":
                plan["kept"][key] = it["selected"]
            elif it["decision"] == "select":
                plan["select_resume"] = {**it["available"][0], "key": key}
            else:
                plan["stop"].append(it)
            continue
        repeated = it.get("reason") == "la etiqueta se repite en este paso"
        if key in answers and repeated:
            if same(f, A.current_value(f), answers[key]):
                plan["kept"][key] = A.current_value(f)  # Allan filled it by hand
            else:
                plan["stop"].append({**it, "reason": "la etiqueta se repite en este paso: llénalo tú en Safari"})
            continue
        if key in answers:
            ok, value = check_answer(f, answers[key])
            current = A.current_value(f)
            if not ok:
                if f.get("type") == "typeahead" and same(f, current, answers[key]):
                    plan["kept"][key] = current  # Allan already filled it by hand
                else:
                    plan["stop"].append({**it, "decision": "ask", "reason": value})
            elif same(f, current, value):
                plan["kept"][key] = value
            else:
                plan["fill"][f.get("label")] = value
                plan["fill_keys"][key] = value
            continue
        dec = it["decision"]
        if dec == "prefilled_ok":
            plan["kept"][key] = it["value"]
        elif dec == "leave_empty":
            continue
        elif (dec == "proposed" and key not in prepared_keys and it.get("section") == "contacto"
              and it.get("status") == "verificado"):
            plan["fill"][f.get("label")] = it["value"]
            plan["fill_keys"][key] = it["value"]
        else:
            plan["stop"].append(it)
    return plan


def verify(fields: list[dict], step: int, expected: dict[str, Any], prefix: str = "") -> list[dict]:
    """Fields whose value (re-read after filling) is not exactly what was filled."""
    by_key = dict(zip(field_keys(fields, step, prefix), fields))
    bad = []
    for key, value in expected.items():
        f = by_key.get(key)
        if f is None or not same(f, A.current_value(f), value):
            bad.append({"key": key, "expected": value, "got": A.current_value(f) if f else None})
    return bad


def step_values(fields: list[dict], step: int, prefix: str = "") -> dict[str, dict]:
    """``{key: {label, value}}`` of a step as it stands (the record of what was actually in the form)."""
    out = {}
    for key, f in zip(field_keys(fields, step, prefix), fields):
        if f.get("type") == "resume":
            sel = next((r for r in f.get("resumes") or [] if r.get("selected")), None)
            value: Any = sel and {"name": sel.get("name"), "date": sel.get("date")}
        else:
            value = A.current_value(f)
        out[key] = {"label": f.get("label"), "type": f.get("type"), "value": value}
    return out


def page_fingerprint(state: dict) -> str:
    """Which page this is (labels, types and buttons, not values): tells pages apart when LinkedIn shows no counter."""
    import json
    return json.dumps([[(f.get("label"), f.get("type")) for f in state.get("fields") or []], state.get("buttons")],
                      ensure_ascii=False)


def signature(state: dict) -> str:
    """What a step looks like (step, fields with values, buttons): equal signatures mean nothing changed."""
    import json
    rows = [(f.get("label"), f.get("type"), A.current_value(f) if f.get("type") != "resume"
             else next((r.get("index") for r in f.get("resumes") or [] if r.get("selected")), None))
            for f in state.get("fields") or []]
    return json.dumps([state.get("step"), rows, state.get("buttons"), bool(state.get("is_review"))],
                      ensure_ascii=False, default=str)
