#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

git add --all
if git diff --cached --quiet; then
  exit 0
fi

git commit -m "chore: sync local changes"
git push origin main
