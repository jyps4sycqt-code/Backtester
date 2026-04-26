#!/usr/bin/env bash
# Remove the weekly LaunchAgent. Safe to run even if not installed.
set -e
PLIST_PATH="$HOME/Library/LaunchAgents/com.trader.weekly.plist"
if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "Removed $PLIST_PATH"
else
    echo "No LaunchAgent at $PLIST_PATH (nothing to remove)."
fi
