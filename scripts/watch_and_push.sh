#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Watching $PROJECT_DIR for changes. Press Ctrl-C to stop."

while true; do
  if ! git diff --quiet || [ -n "$(git status --porcelain)" ]; then
    ./scripts/sync_to_github.sh
  fi
  sleep "${SYNC_INTERVAL_SECONDS:-10}"
done
