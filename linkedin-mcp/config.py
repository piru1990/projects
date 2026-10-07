"""Paths linkedin-mcp reads and writes outside its own folder, each overridable by env (tests use tmp_path).

Read at call time, not import time, so a test (or the MCP registration's "env" block) can point
them elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from guard import default_state_dir

DEFAULT_RESUME = "CV-Allan-Rosales-Tecnologia-ERP.pdf"


def _env_path(var: str, default: Path) -> Path:
    return Path(os.environ.get(var) or default).expanduser()


def skill_dir() -> Path:
    return _env_path("LINKEDIN_MCP_SKILL_DIR", Path.home() / ".claude" / "skills" / "postular-linkedin")


def bank_json() -> Path:
    return skill_dir() / "references" / "respuestas.json"


def bank_md() -> Path:
    return skill_dir() / "references" / "respuestas-linkedin.md"


def triage_json() -> Path:
    return skill_dir() / "references" / "triage.json"


def perfil_md() -> Path:
    return _env_path("LINKEDIN_MCP_PERFIL",
                     Path.home() / ".claude" / "skills" / "llenar-formulario-postulacion" / "references" / "perfil.md")


def cv_dir() -> Path:
    return _env_path("LINKEDIN_MCP_CV_DIR", Path.home() / "Documents" / "CV")


def postulaciones_md() -> Path:
    return _env_path("LINKEDIN_MCP_POSTULACIONES", cv_dir() / "Postulaciones-LinkedIn.md")


def state_dir() -> Path:
    return default_state_dir()
