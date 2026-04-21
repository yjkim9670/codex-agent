# codex-agent

Codex chat server that powers the Configuration > Codex 채팅 UI.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex`)

## Setup
```bash
source ./activate_venv.sh
```

`activate_venv.sh` creates or reuses the shared virtual environment at `../.venv` and installs `requirements.txt`.

## Run
```bash
python run_codex_chat_server.py
```

The server listens on `http://localhost:3000`.

Run with a custom port:
```bash
python run_codex_chat_server.py --port 3100
```

Or with the helper script:
```bash
./run_codex_chat_server.sh --port 3100
```

The helper launcher also uses `../.venv`.

## Git Sync Script
`z00_sync_git.py` is included for branch sync/mirror workflows.

Run:
```bash
python z00_sync_git.py
```

Protection rules are read from `sync_protect.list`.

## GUI
- `http://localhost:<port>/` serves the chat UI.
- `http://localhost:<port>/health` returns JSON status.

## Tailscale Code Server Access
The deployment split artifacts were removed. The remaining remote-access helper is:

- `deploy/tailscale/expose_code_server.sh`

Expose `code-server` on the tailnet:

```bash
./deploy/tailscale/expose_code_server.sh 8080
curl -I https://<machine>.<tailnet>.ts.net:8080/
```

If `serve config denied` appears:

```bash
sudo tailscale set --operator=$USER
```

Keep `8080` reserved for `code-server`. A successful remote check typically returns `302` with `location: ./login`.

## Codex Token Monitoring
- Codex usage tracks prompt/response tokens separately (`input_tokens`, `output_tokens`) plus `cached_input_tokens`.
- Aggregated counters are stored at `<repo>/workspace/.agent_state/codex_token_usage.json` (default parent-workspace mode).
- `GET /api/codex/usage` returns both rate-limit info and `token_usage` summary (`today`, `all_time`, `recent_days`).
