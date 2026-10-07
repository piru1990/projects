"""Classify where a non-Easy-Apply job sends Allan: a form, a company ATS, a job board or the company's site.

Pure: no network. ``account_hint`` is a hint from the domain, not a check: "si" (usually asks for an
account), "no" (usually a plain form), "a_veces" or "desconocido". Creating accounts and signing in
is always Allan's job.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

# (external_kind, site, host suffixes, account_hint)
_TABLE: list[tuple[str, str, tuple[str, ...], str]] = [
    ("google_forms", "Google Forms", ("forms.gle",), "no"),
    ("microsoft_forms", "Microsoft Forms", ("forms.office.com", "forms.microsoft.com", "forms.cloud.microsoft"), "no"),
    ("ats:smartrecruiters", "SmartRecruiters", ("smartrecruiters.com",), "a_veces"),
    ("ats:viterbit", "Viterbit", ("viterbit.net", "viterbit.site", "viterbit.com"), "no"),
    ("ats:workday", "Workday", ("myworkdayjobs.com", "myworkdaysite.com", "workday.com"), "si"),
    ("ats:taleo", "Taleo", ("taleo.net",), "si"),
    ("ats:successfactors", "SAP SuccessFactors", ("successfactors.com", "successfactors.eu", "jobs.sap.com"), "si"),
    ("ats:oracle", "Oracle Recruiting Cloud", ("oraclecloud.com",), "si"),
    ("ats:icims", "iCIMS", ("icims.com",), "si"),
    ("ats:greenhouse", "Greenhouse", ("greenhouse.io",), "no"),
    ("ats:lever", "Lever", ("lever.co",), "no"),
    ("ats:deel", "Deel", ("deel.com",), "a_veces"),
    ("ats:bamboohr", "BambooHR", ("bamboohr.com",), "no"),
    ("ats:workable", "Workable", ("workable.com",), "no"),
    ("ats:teamtailor", "Teamtailor", ("teamtailor.com",), "no"),
    ("ats:ashby", "Ashby", ("ashbyhq.com",), "no"),
    ("ats:jobvite", "Jobvite", ("jobvite.com",), "no"),
    ("ats:recruitee", "Recruitee", ("recruitee.com",), "no"),
    ("ats:breezy", "Breezy HR", ("breezy.hr",), "no"),
    ("ats:personio", "Personio", ("personio.com", "personio.de"), "no"),
    ("ats:zoho", "Zoho Recruit", ("zohorecruit.com",), "a_veces"),
    ("ats:hiringroom", "HiringRoom", ("hiringroom.com",), "a_veces"),
    ("ats:pandape", "Pandapé", ("pandape.com",), "a_veces"),
    ("ats:buk", "Buk", ("buk.cl", "buk.co", "buk.mx", "buk.pe"), "a_veces"),
    ("ats:magneto", "Magneto", ("magneto365.com",), "si"),
    ("job_board", "Un Mejor Empleo", ("unmejorempleo.com.gt", "unmejorempleo.com"), "si"),
    ("job_board", "Trabajos Diarios", ("trabajosdiarios.com",), "desconocido"),
    ("job_board", "Computrabajo", ("computrabajo.com",), "si"),
    ("job_board", "Tecoloco", ("tecoloco.com.gt", "tecoloco.com"), "si"),
    ("job_board", "Indeed", ("indeed.com",), "si"),
    ("job_board", "Glassdoor", ("glassdoor.com",), "si"),
    ("job_board", "Bumeran", ("bumeran.com",), "si"),
    ("job_board", "OCC Mundial", ("occ.com.mx",), "si"),
    ("job_board", "elempleo", ("elempleo.com",), "si"),
    ("job_board", "Get on Board", ("getonbrd.com",), "si"),
    ("job_board", "Opcion Empleo", ("opcionempleo.com.gt", "opcionempleo.com"), "desconocido"),
    ("job_board", "Jooble", ("jooble.org",), "desconocido"),
    ("job_board", "Talent.com", ("talent.com",), "desconocido"),
]
_PATH_RULES = [  # host + path pattern, checked before the host table
    ("google_forms", "Google Forms", "docs.google.com", re.compile(r"^(/a/[^/]+)?/forms/"), "no"),
]
_ENCODED_URL = re.compile(r"^https?%3a", re.I)
_BARE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/|$)", re.I)
_TRACKING = re.compile(r"^(utm_.*|trk|trkinfo|trackingid|refid|lipi|gclid|fbclid|mc_cid|mc_eid)$", re.I)


def unwrap(url: str) -> str:
    """``linkedin.com/safety/go/?url=<x>`` → ``<x>`` (also double-encoded); anything else unchanged."""
    url = (url or "").strip()
    for _ in range(3):
        while _ENCODED_URL.match(url):
            url = unquote(url)
        try:
            u = urlsplit(url)
        except ValueError:
            return url
        host = (u.hostname or "").lower()
        inner = dict(parse_qsl(u.query)).get("url")
        if not (inner and (host == "linkedin.com" or host.endswith(".linkedin.com"))
                and u.path.rstrip("/") == "/safety/go"):
            break
        url = inner
    while _ENCODED_URL.match(url):
        url = unquote(url)
    if _BARE_HOST.match(url):
        url = "https://" + url
    return url


def clean_url(url: str) -> str:
    """Drop tracking parameters (``utm_*``, ``trk``, ``trackingId``, ``refId``…) and keep the rest."""
    try:
        u = urlsplit(url)
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q, doseq=True), u.fragment))


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _by_ats_name(ats: str) -> Optional[tuple[str, str, str]]:
    key = re.sub(r"[^a-z0-9]", "", ats.lower())
    for kind, site, _, hint in _TABLE:
        if kind.startswith("ats:") and (kind[4:] == key or re.sub(r"[^a-z0-9]", "", site.lower()) == key):
            return kind, site, hint
    return None


def classify(url: Optional[str] = None, ats: Optional[str] = None) -> Optional[dict]:
    """``{external_kind, site, account_hint, clean_url}``, or None when there is nothing to classify.

    ``ats`` is the ``applicantTrackingSystemName`` of an ``ats_continue`` job (its only URL points back to
    linkedin.com, so the domain says nothing).
    """
    if ats and not url:
        hit = _by_ats_name(ats)
        kind, site, hint = hit or (f"ats:{re.sub(r'[^a-z0-9]', '', ats.lower())}", ats, "desconocido")
        return {"external_kind": kind, "site": site, "account_hint": hint, "clean_url": None}
    if not url:
        return None
    real = clean_url(unwrap(url))
    try:
        parts = urlsplit(real)
        host = (parts.hostname or "").lower()
    except ValueError:
        host = ""
    if not host:
        return {"external_kind": "unknown", "site": "", "account_hint": "desconocido", "clean_url": None}
    for kind, site, rule_host, path_re, hint in _PATH_RULES:
        if _host_matches(host, rule_host) and path_re.match(parts.path):
            return {"external_kind": kind, "site": site, "account_hint": hint, "clean_url": real}
    for kind, site, suffixes, hint in _TABLE:
        if any(_host_matches(host, s) for s in suffixes):
            return {"external_kind": kind, "site": site, "account_hint": hint, "clean_url": real}
    if ats:
        hit = _by_ats_name(ats)
        if hit:
            return {"external_kind": hit[0], "site": hit[1], "account_hint": hit[2], "clean_url": real}
    return {"external_kind": "company_site", "site": host, "account_hint": "desconocido", "clean_url": real}
