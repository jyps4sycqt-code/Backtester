#!/usr/bin/env bash
# Install a macOS LaunchAgent that runs the weekly paper trade every
# Sunday at 18:00 local time. Idempotent: re-running replaces the agent.
set -e

REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PLIST_NAME="com.trader.weekly.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$REPO_DIR/results/logs"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$LOG_DIR"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.trader.weekly</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$REPO_DIR/automation/run-weekly.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchd.err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Replace any prior load.
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "Installed: $PLIST_PATH"
echo "Schedule:  every Sunday at 18:00 local time"
echo "Logs:      $LOG_DIR/  (launchd.{out,err}.log + automation_*.log)"
echo
echo "Verify it's loaded:"
echo "  launchctl list | grep com.trader"
echo
echo "Run it manually any time:"
echo "  bash $REPO_DIR/automation/run-weekly.sh"
echo
echo "Remove the schedule:"
echo "  bash $REPO_DIR/automation/uninstall-launchd.sh"
