# Running Shim

How to start every piece and check that it works. Shim has five parts. Only the model runs on Brev; everything else runs on your laptop.

| Part | Where | Port | Started by |
|---|---|---|---|
| Nemotron 3.5 Lightning (vLLM) | Brev H100 instance | 8000 on the instance | `docker run` in tmux on the instance |
| Tunnel to the model | laptop | 8000 | `scripts/brev/tunnel.sh` |
| OctoPrint with the Virtual Printer | laptop | 5001 | `scripts/octoprint/start.sh` |
| Web API (agent and tools) | laptop | 8001 | `uvicorn agent.web_api:app` |
| Web page | laptop | 3000 | `npm run dev` in `agent/ui/web` |

Start them in this order. Each laptop command runs from the repository root, in its own terminal that stays open.

## One-time setup

1. Install the Python dependencies: `uv sync`.
2. Install the web dependencies: `npm --prefix agent/ui/web install`.
3. Copy `sample.env` to `.env`. Set `OCTOPRINT_API_KEY` to a key you generate yourself. Never commit `.env`.
4. Install OctoPrint as a uv tool: `uv tool install octoprint`.
5. Install PrusaSlicer 2.9 into `/Applications`. It is only needed for real slicing (`FAKE_TOOLS=0`).
6. Install the Brev CLI and run `brev login`.

## 1. Model on Brev

Start the instance in the Brev console (H100 80GB), then open a shell on it:

```bash
brev shell shim-hardware1
```

On the instance, run vLLM inside tmux, so it keeps running when your SSH session drops:

```bash
tmux new -s vllm
```

```bash
sudo docker run --rm --gpus all --ipc=host -p 127.0.0.1:8000:8000 -v ~/.cache/huggingface:/root/.cache/huggingface vllm/vllm-openai:v0.27.1 --model nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 --served-model-name NVIDIA-Nemotron-3.5-Lightning-30B-A3B --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3 --max-model-len 65536 --max-num-seqs 256
```

- It is ready when the log shows `Application startup complete`. The first start downloads about 60 GB, and later starts take a few minutes.
- `--max-num-seqs 256` is required on an H100; without it vLLM exits with "max_num_seqs exceeds available Mamba cache blocks".
- Detach from tmux with **Ctrl-b**, then **d**. Don't use Ctrl-C, which stops vLLM. Reattach later with `tmux attach -t vllm`.
- If Docker says the port is already allocated, an old container is still running. Find it with `sudo docker ps`, then run `sudo docker rm -f <id>`.
- `scripts/brev/serve.sh` is the non-Docker version. It needs vLLM installed on the instance, and it is missing the `--max-num-seqs 256` flag.

Stop the instance in the Brev console when you're done; it bills while running.

## 2. Tunnel to the model (laptop)

```bash
scripts/brev/tunnel.sh shim-hardware1
```

This forwards `localhost:8000` to vLLM on the instance and reconnects whenever Brev drops the connection. Check it:

```bash
curl -s localhost:8000/v1/models
```

- If the tunnel reports the port is in use, a leftover `ssh` is still holding it. Run `lsof -nP -iTCP:8000 -sTCP:LISTEN`, then `kill <PID>`.
- If SSH fails, run `brev refresh` and try again.

## 3. OctoPrint (laptop)

```bash
scripts/octoprint/start.sh
```

- Open http://localhost:5001 and sign in.
- Connect to the **VIRTUAL** port. The printer state should read **Operational**.
- OctoPrint uses 5001 because macOS AirPlay takes 5000.
- Errors about `pip` in the log are harmless: OctoPrint's uv environment has no pip.

You can skip OctoPrint when you run the API with `FAKE_TOOLS=1`.

## 4. Web API (laptop)

To use the fake printer, which is instant and needs no OctoPrint or slicer:

```bash
FAKE_TOOLS=1 uv run uvicorn agent.web_api:app --port 8001
```

To use real PrusaSlicer slicing and print on OctoPrint's Virtual Printer:

```bash
FAKE_TOOLS=0 uv run uvicorn agent.web_api:app --port 8001
```

- The CAD tools are real in both modes. `FAKE_TOOLS` only swaps the printer tools.
- The API reads `.env`. A variable you set on the command line wins over `.env`.
- Restarting the API clears every browser session.
- Check that it's running with `curl -s localhost:8001/api/printer`.

## 5. Web page (laptop)

```bash
NEXT_PUBLIC_USE_MOCK=0 npm --prefix agent/ui/web run dev
```

Open http://localhost:3000.

- `NEXT_PUBLIC_USE_MOCK=0` sends the page to the real API. Without it, the page runs on mock data with no backend.
- The API accepts pages on ports 3000 and 3001 by default. For any other port, set `WEB_ORIGINS` on the API.
- In Claude Code, the `.claude/launch.json` entries `api` and `web-real-api` (on port 3001) start the same servers.

## Trying the flow

1. **Limb page:** the measurement profile is read-only. Ask in chat to change a value, for example "make the proximal circumference 300". Then click **Confirm limb**. Building the socket takes about 20 s.
2. **Socket page:** try "make the wall 6 mm", "engrave SHIM-04 on the front", then "validate it", then click **Confirm socket**.
3. **Printer page:** say "print it with the draft profile", or "make a 40% preview and print that" for a print of about 70 minutes, and approve both confirmations. With `FAKE_TOOLS=0` the live layer view follows the printer layer by layer.

To start over, open the page in a private window, or restart the API.

With `FAKE_TOOLS=0`, a socket takes about 11 h on the Virtual Printer, which runs at real speed. Cancel the job in chat or in OctoPrint when you're done. A new print is refused while an older job is still running.

## Without the web page

- Terminal chat with the same agent: `uv run python -m agent.ui.cli`
- Model and tool-calling smoke test: `set -a && . ./.env && set +a && PYTHONPATH=. uv run python scripts/smoke_tool_call.py`
- Tests, which need no model: `uv run pytest`. The CAD tests take about 2 minutes.

## Quick health check

```bash
curl -s localhost:8000/v1/models >/dev/null && echo model ok; curl -s localhost:8001/api/printer >/dev/null && echo api ok; curl -s -o /dev/null localhost:3000 && echo page ok; curl -s -o /dev/null localhost:5001 && echo octoprint ok
```

If the chat hangs or errors, check the model first, then the API's terminal.
