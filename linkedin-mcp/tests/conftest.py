import os
import sys
import tempfile
from pathlib import Path

# Importing server builds Guard() from LINKEDIN_MCP_STATE_DIR, so point it at a throwaway folder before
# any test imports it: tests never read or write the real ~/.cache/linkedin-mcp.
os.environ["LINKEDIN_MCP_STATE_DIR"] = tempfile.mkdtemp(prefix="linkedin-mcp-tests-")
# And no test (nor a cli.py subprocess it starts) may drive the real Safari: safari_bridge.osa refuses.
os.environ["LINKEDIN_MCP_NO_SAFARI"] = "1"
# Nor write Allan's real logs: the two Markdown tables a submit appends to are throwaway copies.
_logs = Path(os.environ["LINKEDIN_MCP_STATE_DIR"]) / "logs"
_logs.mkdir()
_TEMPLATES = {
    "Postulaciones-LinkedIn.md": "# Postulaciones (copia de prueba)\n\n"
    "| Fecha y hora | Empresa | Puesto | job_id | Enlace | CV (SHA-256) | Respuestas dadas | Estado comprobado |\n"
    "|---|---|---|---|---|---|---|---|\n",
    "perfil.md": "# Perfil (copia de prueba)\n\n## Estado de postulaciones\n| Organización / puesto | Estado | Fecha |\n"
    "|---|---|---|\n\n## Otra sección\n",
}
os.environ["LINKEDIN_MCP_POSTULACIONES"] = str(_logs / "Postulaciones-LinkedIn.md")
os.environ["LINKEDIN_MCP_PERFIL"] = str(_logs / "perfil.md")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atexit  # noqa: E402
import shutil  # noqa: E402

atexit.register(shutil.rmtree, os.environ["LINKEDIN_MCP_STATE_DIR"], ignore_errors=True)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_logs():
    """Every test starts with empty copies of the two Markdown logs."""
    for name, text in _TEMPLATES.items():
        (_logs / name).write_text(text, encoding="utf-8")
