"""Deterministic triage of a LinkedIn job list against Allan's verified profile. Pure: it opens no job.

Rules live in the skill's ``references/triage.json`` (``config.triage_json()``):

- ``positive`` criteria, each quoting in ``evidence`` a text that must appear verbatim in the Experiencia,
  Docencia or Formación sections of perfil.md (not in the integrity rules, which list what Allan does NOT
  have); a criterion whose quote is missing, or that is malformed, is skipped and reported.
- ``terms`` are matched in the title; ``desc_terms``, more specific phrases, in a fresh cached description,
  which adds at most +2 in total. A match nested inside a longer match of another criterion doesn't count, and
  general leadership doesn't add on top of an IT-management or project title (it is implied).
- ``flags`` mark experience with no evidence: ``terms`` in title or company cap an "alto" at "medio";
  ``desc_terms`` in the description are only shown. ``exclude`` phrases cancel a match.

Gender-inclusive titles ("Jefe(a)", "Coordinador/a") are folded first. A fit read from the title alone is
"provisional", and the type from the list card is "según tarjeta" (cbc's card said Solicitud sencilla but the
job was an ATS "Continuar").
"""

from __future__ import annotations

import re
from typing import Any, Optional

import answers as A

FIT_ORDER = {"alto": 0, "medio": 1, "bajo": 2}
DESC_CAP = 2
_MODALITY = (("remoto", "En remoto"), ("remote", "En remoto"), ("hibrido", "Híbrido"), ("hybrid", "Híbrido"),
             ("presencial", "Presencial"), ("on-site", "Presencial"), ("onsite", "Presencial"))
_GENDER_RE = re.compile(r"\s*\((?:a|o|as|os|la|el)\)|/(?:a|o|as|os|la)(?![A-Za-zÁÉÍÓÚáéíóúñÑ])", re.I)
_IMPLIES_LEADERSHIP = ("gerencia_ti", "proyectos")


def fold(text: Any) -> str:
    """``answers.clean`` after dropping gender markers: "Jefe(a) de Proyectos" → "jefe de proyectos"."""
    return A.clean(_GENDER_RE.sub("", "" if text is None else str(text)))


def _spans(text: str, terms: list[str]) -> list[tuple[int, int, str]]:
    out = []
    for t in terms:
        ct = A.clean(t)
        if ct:
            out += [(m.start(), m.end(), t) for m in re.finditer(rf"(?<![a-z0-9#]){re.escape(ct)}(?![a-z0-9#])", text)]
    return out


def _excluded(text: str, rule: dict) -> bool:
    return any(_spans(text, [x]) for x in rule.get("exclude") or [])


def _valid(rule: Any, positive: bool) -> bool:
    if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not isinstance(rule.get("label"), str):
        return False
    if not all(isinstance(rule.get(k, []), list) for k in ("terms", "desc_terms", "exclude")):
        return False
    return not positive or (isinstance(rule.get("weight", 1), int) and isinstance(rule.get("evidence"), str))


def evidence_text(perfil_text: str, sections: list[str]) -> str:
    """Only the perfil.md sections that describe what Allan has done (``## Experiencia``, ``## Docencia``…)."""
    parts, keep = [], False
    for line in perfil_text.splitlines():
        if line.startswith("## "):
            keep = any(line[3:].strip().startswith(s) for s in sections)
        if keep:
            parts.append(line)
    return "\n".join(parts)


def load_rules(data: Any, perfil_text: str) -> tuple[dict, list[str]]:
    """The usable rules, and the ids skipped (missing evidence in the allowed sections, or malformed)."""
    if not isinstance(data, dict):
        return {"positive": [], "flags": [], "thresholds": {"alto": 5, "medio": 2}}, ["(triage.json no es un objeto)"]
    allowed = evidence_text(perfil_text, data.get("evidence_sections") or ["Experiencia", "Docencia", "Formación"])
    kept, flags, skipped = [], [], []
    for g in data.get("positive") or []:
        if _valid(g, True) and g["evidence"] and g["evidence"] in allowed:
            kept.append(g)
        else:
            skipped.append(g.get("id") if isinstance(g, dict) else repr(g)[:40])
    for f in data.get("flags") or []:
        (flags.append(f) if _valid(f, False) else skipped.append(f.get("id") if isinstance(f, dict) else repr(f)[:40]))
    th = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    return {"positive": kept, "flags": flags,
            "thresholds": {"alto": int(th.get("alto", 5)), "medio": int(th.get("medio", 2))}}, skipped


def modality(job: dict, cached: Optional[dict]) -> Optional[str]:
    texts = [A.clean(c) for c in ((cached or {}).get("chips") or [])] + [A.clean(job.get("location"))]
    for t in texts:
        for key, name in _MODALITY:
            if re.search(rf"(?<![a-z]){key}(?![a-z])", t):
                return name
    return None


def _title_hits(title: str, rules: list[dict]) -> dict[str, list[str]]:
    """Criterion id → terms found in the title, dropping matches nested in a longer match of another criterion."""
    found = []
    for g in rules:
        if _excluded(title, g):
            continue
        found += [(s, e, t, g["id"]) for s, e, t in _spans(title, g.get("terms", []))]
    kept: dict[str, list[str]] = {}
    for s, e, t, gid in found:
        nested = any(o[3] != gid and o[0] <= s and e <= o[1] and o[1] - o[0] > e - s for o in found)
        if not nested:
            kept.setdefault(gid, []).append(t)
    if any(g in kept for g in _IMPLIES_LEADERSHIP):
        kept.pop("liderazgo", None)
    return kept


def score_job(job: dict, rules: dict, cached: Optional[dict] = None) -> dict:
    """One job card (plus its cached page, if fresh) scored against the rules."""
    title, company = fold(job.get("title")), fold(job.get("company"))
    desc = fold((cached or {}).get("description"))
    basis = "descripcion" if desc else "titulo"
    hits = _title_hits(title, rules["positive"])
    score, reasons, from_desc = 0, [], 0
    for g in rules["positive"]:
        if g["id"] in hits:
            score += int(g.get("weight", 1))
            reasons.append(f"{g['label']} (título: {', '.join(dict.fromkeys(hits[g['id']]))})")
        elif desc and from_desc < DESC_CAP and not _excluded(desc, g):
            found = [t for _, _, t in _spans(desc, g.get("desc_terms", []))]
            if found:
                score, from_desc = score + 1, from_desc + 1
                reasons.append(f"{g['label']} (descripción: {', '.join(dict.fromkeys(found))[:60]})")
    flags, capping = [], False
    for f in rules["flags"]:
        where = []
        for name, text, terms in (("título", title, f.get("terms", [])), ("empresa", company, f.get("terms", [])),
                                  ("descripción", desc, f.get("desc_terms", []))):
            if text and not _excluded(text, f):
                found = [t for _, _, t in _spans(text, terms)]
                if found:
                    where.append(f"{name}: {', '.join(dict.fromkeys(found))}")
                    capping = capping or name != "descripción"
        if where:
            flags.append(f"{f['label']} ({'; '.join(where)})")
    th = rules["thresholds"]
    fit = "alto" if score >= th["alto"] else "medio" if score >= th["medio"] else "bajo"
    if capping and fit == "alto":
        fit = "medio"
    cached_type = (cached or {}).get("apply_type")
    if cached_type and cached_type != "unknown":
        kind, kind_source = cached_type, "vacante"
    else:
        kind, kind_source = ("easy_apply" if job.get("easy_apply") else "externa_o_ats"), "tarjeta"
    state = ("ya solicitada" if job.get("applied") or cached_type == "applied" else
             "cerrada" if cached_type == "closed" else
             "en el registro local" if job.get("in_local_log") else
             "guardada" if job.get("saved") else "vista" if job.get("viewed") else "nueva")
    return {"job_id": job.get("job_id"), "title": job.get("title"), "company": job.get("company"),
            "location": job.get("location"), "modalidad": modality(job, cached), "tipo": kind,
            "tipo_segun": kind_source, "estado": state, "encaje": fit,
            "encaje_provisional": basis == "titulo", "basis": basis, "puntaje": score,
            "motivos": reasons, "banderas": flags, "posted": job.get("posted") or None}


def triage(jobs: list[dict], rules: dict, cache: dict[str, dict]) -> list[dict]:
    """Every card scored and sorted: open jobs by fit, unflagged first, then score; closed or applied last."""
    rows = []
    for i, job in enumerate(jobs):
        cached = (cache.get(str(job.get("job_id"))) or {}).get("data")
        r = score_job(job, rules, cached)
        r["_i"] = i
        rows.append(r)
    done = ("ya solicitada", "en el registro local", "cerrada")
    rows.sort(key=lambda r: (r["estado"] in done, FIT_ORDER[r["encaje"]], bool(r["banderas"]), -r["puntaje"], r["_i"]))
    for r in rows:
        del r["_i"]
    return rows
