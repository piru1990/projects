#!/bin/bash
# Plan B: registra los MCP locales "linkedin" y "safari" en la config de Claude.app
# (claude_desktop_config.json), para que también los vea el chat de la app.
#
# El registro normal es el ámbito usuario de Claude Code (~/.claude.json, ver README). No uses
# los dos a la vez: duplicarían los servidores. Por eso el script se niega si ya están allí.
#
# Córrelo solo con Claude.app cerrada (Cmd+Q). La app guarda esta config desde la copia que
# tiene en memoria cada vez que cambia una preferencia, así que pisa cualquier cambio hecho
# mientras está abierta (main.log: "Config file written").
#
#   bash ~/Documents/linkedin-mcp/registrar-mcp.sh
set -euo pipefail

app_running() {
  ps -axo comm= | grep -Eq '^/Applications/Claude\.app/Contents/(MacOS/Claude|Helpers/disclaimer)$'
}

for _ in $(seq 1 15); do
  app_running || break
  sleep 1
done
if app_running; then
  echo "Claude.app sigue abierta. Ciérrala con Cmd+Q y vuelve a correr el script." >&2
  exit 1
fi

exec /usr/bin/python3 - <<'PY'
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

CONFIG = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
CODE_CONFIG = os.path.expanduser("~/.claude.json")
LI = "/Users/admin/Documents/linkedin-mcp"
SA = "/Users/admin/Library/CloudStorage/OneDrive-FAPCO/intensegroup-claude-tools/safari-mcp"
WANT = {
    "linkedin": {"command": f"{LI}/.venv/bin/python", "args": [f"{LI}/server.py"]},
    "safari": {"command": f"{SA}/.venv/bin/python", "args": [f"{SA}/server.py"],
               "env": {"SAFARI_MCP_ALLOW_EVAL": "true"}},
}
APP_RE = re.compile(r"^/Applications/Claude\.app/Contents/(MacOS/Claude|Helpers/disclaimer)$")


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def app_running():
    out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True).stdout
    return any(APP_RE.match(line.strip()) for line in out.splitlines())


for spec in WANT.values():
    for path in [spec["command"], *spec["args"]]:
        if not os.path.exists(path):
            die(f"Falta {path}")

try:
    with open(CODE_CONFIG, encoding="utf-8") as fh:
        code_servers = json.load(fh).get("mcpServers") or {}
except FileNotFoundError:
    code_servers = {}
dup = [name for name in WANT if name in code_servers]
if dup:
    die(f"Ya están en ~/.claude.json (ámbito usuario de Code): {', '.join(dup)}. "
        "Quítalos de allí antes de registrarlos aquí, para no duplicarlos.")

with open(CONFIG, encoding="utf-8") as fh:
    raw = fh.read()
original = json.loads(raw)  # si el JSON está roto, se detiene aquí sin tocar nada
data = json.loads(raw)
servers = data.setdefault("mcpServers", {})

missing = {}
for name, spec in WANT.items():
    if name not in servers:
        missing[name] = spec
    elif servers[name] != spec:
        die(f"'{name}' ya existe con otra configuración; revísalo a mano.")
    else:
        print(f"{name}: ya existe, no se toca.")
if not missing:
    print("Nada que hacer.")
    sys.exit(0)

backup = f"{CONFIG}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(CONFIG, backup)
servers.update(missing)
text = json.dumps(data, ensure_ascii=False, indent=2)
json.loads(text)

if app_running():
    die("Claude.app se abrió mientras corría el script; no cambié nada.")
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CONFIG), prefix=".claude_desktop_config.")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, CONFIG)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)

with open(CONFIG, encoding="utf-8") as fh:
    after = json.load(fh)
rest = json.loads(json.dumps(after))
for name in missing:
    rest["mcpServers"].pop(name, None)
if "mcpServers" not in original and not rest["mcpServers"]:
    del rest["mcpServers"]
if rest != original or any(after["mcpServers"].get(k) != v for k, v in missing.items()):
    shutil.copy2(backup, CONFIG)
    die(f"La verificación falló; restauré {backup}.")

print(f"Respaldo: {backup}")
print(f"Agregados: {', '.join(missing)}")
print(f"Servidores ahora: {', '.join(after['mcpServers'])}")
print("Abre Claude.app y comprueba que aparezcan las tools mcp__linkedin__* y mcp__safari__*.")
PY
