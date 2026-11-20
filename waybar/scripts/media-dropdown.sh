#!/usr/bin/env bash

LOG_FILE="/tmp/media-dropdown.log"
exec >> "$LOG_FILE" 2>&1
echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] media-dropdown.sh triggered (PID: $$) ==="

PID_FILE="/tmp/media-dropdown.pid"

# Toggle behavior: if an instance is currently running, close it
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && [ "$OLD_PID" != "$$" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Active external menu instance found with PID $OLD_PID. Toggling off..."
        kill "$OLD_PID" 2>/dev/null
        rm -f "$PID_FILE"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
echo "Starting python3 $DIR/media-dropdown.py..."
python3 "$DIR/media-dropdown.py" "$@" &
echo "Spawned python process with PID $!"
