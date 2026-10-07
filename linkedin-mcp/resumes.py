"""Which resume files went to LinkedIn, with their SHA-256, so the application record names the real file.

LinkedIn's list keeps many uploads with the same name (``resume.pdf`` ×7, ``CV-Allan Rosales.pdf`` ×3…)
and a local CV can be regenerated under the same name later. So the hash recorded for an application
comes from ``<state dir>/resumes.json`` (written by ``linkedin_apply_upload_resume``) when the selected
resume's name and LinkedIn date match exactly one upload; otherwise from the local file, marked as not
checked against LinkedIn; otherwise none.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

SOURCE_LEDGER = "registro de CV subidos"
SOURCE_LOCAL = "archivo local en ~/Documents/CV, no comprobado contra LinkedIn"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ResumeLedger:
    def __init__(self, state_dir: Path):
        self.path = Path(state_dir) / "resumes.json"

    def entries(self) -> list[dict]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def add(self, name: str, linkedin_date: str, sha256: str, source_path: str = "", note: str = "") -> dict:
        row = {"name": name, "linkedin_date": linkedin_date, "sha256": sha256, "source_path": source_path, "note": note}
        rows = self.entries()
        if not any((r.get("name"), r.get("linkedin_date"), r.get("sha256")) == (name, linkedin_date, sha256) for r in rows):
            rows.append(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        return row

    def newest(self, name: str) -> Optional[dict]:
        """The most recent upload with this file name (by LinkedIn's d/m/yyyy date), or None."""
        def key(r: dict) -> tuple:
            try:
                d, m, y = (int(x) for x in r.get("linkedin_date", "").split("/"))
                return (y, m, d)
            except ValueError:
                return (0, 0, 0)
        rows = [r for r in self.entries() if r.get("name") == name]
        return max(rows, key=key) if rows else None

    def lookup(self, name: str, linkedin_date: str) -> Optional[dict]:
        """The one upload with this name and date; None if there is none or several different files."""
        hits = {r["sha256"]: r for r in self.entries()
                if r.get("name") == name and r.get("linkedin_date") == linkedin_date and r.get("sha256")}
        return next(iter(hits.values())) if len(hits) == 1 else None


def resume_hash(name: Optional[str], linkedin_date: Optional[str], ledger: ResumeLedger, cv_dir: Path) -> dict:
    """``{"sha256", "sha256_source"}`` for the selected resume (both None when nothing is known)."""
    if not name:
        return {"sha256": None, "sha256_source": None}
    hit = ledger.lookup(name, linkedin_date or "")
    if hit:
        return {"sha256": hit["sha256"], "sha256_source": SOURCE_LEDGER}
    local = Path(cv_dir) / name
    if local.is_file() and local.parent == Path(cv_dir):
        return {"sha256": sha256_file(local), "sha256_source": SOURCE_LOCAL}
    return {"sha256": None, "sha256_source": None}
