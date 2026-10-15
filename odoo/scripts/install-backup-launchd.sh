#!/usr/bin/env bash
# Instala (o reinstala) el respaldo diario de Odoo como LaunchAgent: todos los días a las 03:15, hora de la Mac.
# Si la Mac está dormida a esa hora, launchd lo corre al despertar. Log: ~/.local/var/log/gatherings-backup.log
# Quitar: launchctl bootout gui/$(id -u)/com.gatheringsgt.odoo-backup && rm ~/Library/LaunchAgents/com.gatheringsgt.odoo-backup.plist
set -euo pipefail
AQUI="$(cd "$(dirname "$0")/.." && pwd)"
ETQ="com.gatheringsgt.odoo-backup"
PLIST="$HOME/Library/LaunchAgents/$ETQ.plist"
LOG="$HOME/.local/var/log/gatherings-backup.log"
mkdir -p "$HOME/Library/LaunchAgents" "$(dirname "$LOG")"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ETQ</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$AQUI/scripts/backup.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>15</integer></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
  <key>Nice</key><integer>10</integer>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$ETQ" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Instalado $ETQ (03:15 diario). Probar ahora: launchctl kickstart -k gui/$(id -u)/$ETQ ; tail $LOG"
