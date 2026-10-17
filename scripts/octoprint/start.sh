#!/usr/bin/env bash
# Start a local OctoPrint with the Virtual Printer for development.
# Usage: scripts/octoprint/start.sh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
basedir="$repo_root/workspace/octoprint"
port=5001   # 5000 is taken by the macOS AirPlay Receiver

if [[ ! -f "$repo_root/.env" ]]; then
  echo "Missing .env. Copy sample.env to .env and set OCTOPRINT_API_KEY." >&2
  exit 1
fi
api_key="$(grep -E '^OCTOPRINT_API_KEY=' "$repo_root/.env" | cut -d= -f2-)"
if [[ -z "$api_key" || "$api_key" == "replace-with-a-generated-key" ]]; then
  echo "Set OCTOPRINT_API_KEY in .env first." >&2
  exit 1
fi

if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $port is already in use. OctoPrint may already be running:" >&2
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2
  echo "Stop it with: kill <PID>" >&2
  exit 1
fi

mkdir -p "$basedir"
cp "$repo_root/scripts/octoprint/config.yaml" "$basedir/config.yaml"
printf 'api:\n  key: %s\n' "$api_key" >> "$basedir/config.yaml"

exec octoprint serve --basedir "$basedir" --host 127.0.0.1 --port "$port"
