#!/bin/bash
# Schedule `snap-assistant sync` on this Mac with launchd.
#
#   scripts/install-launchd.sh            # every 6 hours (and once now)
#   scripts/install-launchd.sh 3          # every 3 hours
#   scripts/install-launchd.sh --uninstall
#
# Runs from this checkout's .venv, so keep the repo where it is. Reports go to
# ~/Library/Application Support/snap-assistant/reports/latest.md and a macOS
# notification appears when cards change, new conflicts appear, or a source fails.
set -euo pipefail

LABEL="com.snap-assistant.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO/.venv/bin/snap-assistant"
HOME_DIR="${SNAP_ASSISTANT_HOME:-$HOME/Library/Application Support/snap-assistant}"
DOMAIN="gui/$(id -u)"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed $LABEL. Synced data is kept in: $HOME_DIR"
  exit 0
fi

HOURS="${1:-6}"
if [[ ! -x "$BIN" ]]; then
  echo "Missing $BIN. Set up the venv first:" >&2
  echo "  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev]'" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME_DIR/logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN</string>
    <string>sync</string>
    <string>--notify</string>
    <string>--quiet</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>SNAP_ASSISTANT_HOME</key><string>$HOME_DIR</string></dict>
  <key>StartInterval</key><integer>$((HOURS * 3600))</integer>
  <key>RunAtLoad</key><true/>
  <key>LowPriorityIO</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$HOME_DIR/logs/sync.log</string>
  <key>StandardErrorPath</key><string>$HOME_DIR/logs/sync.log</string>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed $LABEL: sync every $HOURS h (running once now)."
echo "  Report:  $HOME_DIR/reports/latest.md"
echo "  Log:     $HOME_DIR/logs/sync.log"
echo "  Status:  launchctl print $DOMAIN/$LABEL | grep -E 'state|last exit'"
