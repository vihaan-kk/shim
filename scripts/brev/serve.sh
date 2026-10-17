#!/usr/bin/env bash
# Run ON the Brev instance (not on your laptop): serve Nemotron with tool calling.
# Usage: scripts/brev/serve.sh
# Needs a recent vLLM that has the qwen3_coder and nemotron_v3 parsers; if vLLM
# rejects a parser name at startup, upgrade vLLM or use the Red Hat vLLM image.
# Gated weights: run `huggingface-cli login` on the instance first (never commit a token).
set -euo pipefail

model="${MODEL:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16}"
port="${PORT:-8000}"

exec vllm serve "$model" \
  --served-model-name NVIDIA-Nemotron-3.5-Lightning-30B-A3B \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser nemotron_v3 \
  --host 127.0.0.1 \
  --port "$port"
