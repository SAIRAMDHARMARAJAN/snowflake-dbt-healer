#!/bin/bash
# Autonomous Pipeline Healer — runs orchestrator.py every 5 minutes
# Usage: bash scheduler.sh [interval_seconds]  (default: 300)
#
# To run as a background daemon:
#   nohup bash scheduler.sh > logs/scheduler.log 2>&1 &
#
# To stop: kill $(cat scheduler.pid)

INTERVAL=${1:-300}
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/.venv/bin/activate" ]; then
  source "$DIR/.venv/bin/activate"
fi
LOG="$DIR/logs/scheduler.log"
PID_FILE="$DIR/scheduler.pid"

mkdir -p "$DIR/logs"
echo $$ > "$PID_FILE"

echo "[$(date)] Autonomous Pipeline Healer scheduler started (interval: ${INTERVAL}s)" | tee -a "$LOG"

while true; do
  echo "" | tee -a "$LOG"
  echo "[$(date)] ═══ Healer check ═══" | tee -a "$LOG"

  # Ensure MCP server is running
  if ! curl -s http://localhost:8700/health > /dev/null 2>&1; then
    echo "[$(date)] MCP server not running — starting..." | tee -a "$LOG"
    cd "$DIR" && python3 mcp_server/server.py >> "$LOG" 2>&1 &
    sleep 3
  fi

  # Run the orchestrator
  cd "$DIR" && python3 orchestrator.py 2>&1 | tee -a "$LOG"

  echo "[$(date)] Next check in ${INTERVAL}s" | tee -a "$LOG"
  sleep "$INTERVAL"
done
