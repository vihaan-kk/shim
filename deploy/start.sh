#!/usr/bin/env bash
# Build the page and start every service on the Brev instance in one tmux session, "shim".
# Usage, on the instance: ~/shim/deploy/start.sh https://8080-<id>.gobrev.dev
# The site asks for a login: user "shim", password "shim" (hardcoded; override with SHIM_PASSWORD).
# Services: OctoPrint :5001, API :8001, Next.js :3000, Caddy :8080 (the only one to expose).
# vLLM is expected on localhost:8000 already (the Docker container).
# Stop everything with: tmux kill-session -t shim
set -euo pipefail
public_url="${1:?usage: deploy/start.sh https://8080-<id>.gobrev.dev}"
public_url="${public_url%/}"
root="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/bin:$HOME/opt/node/bin:$PATH"

# Server values win over the laptop .env (load_env never overrides a set variable).
cat > "$root/deploy/server.env" <<EOF
export VLLM_BASE_URL=http://localhost:8000/v1
export OCTOPRINT_URL=http://localhost:5001
export FAKE_TOOLS=0
export PRUSASLICER_BIN=$HOME/opt/prusaslicer/AppRun
export API_PUBLIC_BASE=$public_url/api
export WEB_ORIGINS=$public_url
EOF

# The page calls the API on its own origin, so the session cookie needs no cross-site settings.
(cd "$root/agent/ui/web" && NEXT_PUBLIC_USE_MOCK=0 NEXT_PUBLIC_API_BASE=/api npm run build)

hash="$(caddy hash-password --plaintext "${SHIM_PASSWORD:-shim}")"
auth="basic_auth {
    shim $hash
  }"
cat > "$root/deploy/Caddyfile" <<EOF
:8080 {
  $auth
  handle /api/* {
    # The agent streams its turn as server-sent events; do not buffer them.
    reverse_proxy 127.0.0.1:8001 {
      flush_interval -1
    }
  }
  handle {
    reverse_proxy 127.0.0.1:3000
  }
}
EOF

# Closing the tmux session does not always stop a service (Caddy kept serving the old config),
# so also stop anything still listening on our ports. Never 8000: that is vLLM.
tmux kill-session -t shim 2>/dev/null || true
for port in 5001 8001 3000 8080; do
  for pid in $(ss -ltnp 2>/dev/null | grep ":$port " | grep -o "pid=[0-9]*" | cut -d= -f2 | sort -u); do
    kill "$pid" 2>/dev/null || true
  done
done
sleep 2
tmux new-session -d -s shim -n octoprint -c "$root" "scripts/octoprint/start.sh; bash"
tmux new-window -t shim -n api -c "$root" \
  "source deploy/server.env && uv run uvicorn agent.web_api:app --host 127.0.0.1 --port 8001; bash"
tmux new-window -t shim -n web -c "$root/agent/ui/web" "npm run start -- --hostname 127.0.0.1 --port 3000; bash"
tmux new-window -t shim -n caddy -c "$root" "caddy run --config deploy/Caddyfile --adapter caddyfile; bash"

echo "Started tmux session 'shim' (attach: tmux attach -t shim). Expose port 8080 in Brev, then open $public_url"
