"""Job pages already read, by job_id, so re-reading one doesn't spend another daily view.

``<state dir>/jobs/<job_id>.json`` holds ``{"fetched_at": <epoch>, "data": <job_detail>}``. An entry is
fresh for 24 h. Writes are atomic (temp file + rename).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

TTL_SECONDS = 24 * 3600
_JOB_ID_RE = re.compile(r"\d{6,12}")


class JobCache:
    def __init__(self, state_dir: Path, ttl: float = TTL_SECONDS, now: Callable[[], float] = time.time):
        self.dir = Path(state_dir) / "jobs"
        self.ttl = ttl
        self.now = now

    def _path(self, job_id: str) -> Path:
        if not _JOB_ID_RE.fullmatch(str(job_id)):
            raise ValueError(f"job_id inválido: {job_id!r}")
        return self.dir / f"{job_id}.json"

    def _read(self, job_id: str) -> Optional[dict]:
        try:
            row = json.loads(self._path(job_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        ok = isinstance(row, dict) and isinstance(row.get("data"), dict) and isinstance(row.get("fetched_at"), (int, float))
        return row if ok else None

    def get(self, job_id: str) -> Optional[dict]:
        """``{"fetched_at", "data"}`` if fresh, else None."""
        row = self._read(job_id)
        if not row or self.now() - row["fetched_at"] > self.ttl:
            return None
        return row

    def put(self, job_id: str, data: dict) -> dict:
        row = {"fetched_at": self.now(), "data": data}
        self._write(job_id, row)
        return row

    def mark(self, job_id: str, **fields: Any) -> None:
        """Update fields of a cached job (e.g. ``apply_type="applied"`` after a confirmed submit)."""
        row = self._read(job_id)
        if row:
            row["data"].update(fields)
            self._write(job_id, row)

    def invalidate(self, job_id: str) -> None:
        try:
            self._path(job_id).unlink()
        except FileNotFoundError:
            pass

    def fresh(self) -> dict[str, dict]:
        """Every fresh entry, by job_id (triage reads their descriptions)."""
        out = {}
        for p in sorted(self.dir.glob("*.json")) if self.dir.exists() else []:
            row = self.get(p.stem) if _JOB_ID_RE.fullmatch(p.stem) else None
            if row:
                out[p.stem] = row
        return out

    def _write(self, job_id: str, row: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
