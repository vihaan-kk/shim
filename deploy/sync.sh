#!/usr/bin/env bash
# Copy this checkout to the Brev instance (run on your laptop, from the repo root).
# Usage: deploy/sync.sh [ssh-host]          default host: shim-hardware1
# Copies .env too (it holds the OctoPrint and vLLM keys; the instance is yours).
# Leaves out git data, installed packages, build output and the runtime workspace.
set -euo pipefail
host="${1:-shim-hardware1}"
cd "$(dirname "$0")/.."
rsync -az --delete \
  --exclude .git --exclude .venv --exclude node_modules --exclude .next \
  --exclude '__pycache__' --exclude .pytest_cache --exclude '/workspace/*' \
  ./ "$host:shim/"
ssh "$host" 'mkdir -p ~/shim/workspace'
echo "Synced to $host:~/shim"
