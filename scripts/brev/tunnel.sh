#!/usr/bin/env bash
# Keep localhost:8000 forwarded to vLLM on a Brev instance, reconnecting when it drops.
# Usage: scripts/brev/tunnel.sh <instance-name>      (Ctrl-C to stop)
# Uses the SSH host Brev writes to ~/.brev/ssh_config; `brev port-forward` exits silently.
set -u
instance="${1:?usage: scripts/brev/tunnel.sh <instance-name>}"
while true; do
  echo "$(date '+%H:%M:%S') forwarding localhost:8000 -> $instance:8000"
  ssh -N -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    -L 8000:127.0.0.1:8000 "$instance"
  echo "$(date '+%H:%M:%S') tunnel closed (exit $?); reconnecting in 3 s"
  sleep 3
done
