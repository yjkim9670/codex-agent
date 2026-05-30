# codex-workbench

Codex Workbench server for Codex chat sessions, workspace files, terminal sessions, Git sync, and usage monitoring.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex` on macOS/Linux, `codex.cmd` on Windows)

Set `CODEX_CLI_BIN=/absolute/path/to/codex` when the CLI is installed outside
`PATH`. The company launchers also probe common npm prefix paths, Windows
`%APPDATA%\npm\codex.cmd`, and the macOS Codex app bundle path.

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

## Codex CLI Stability Options
Workbench does not serialize `codex exec` child processes by default. Company
launchers explicitly force the exec lock off so stale launcher environments do
not make every Workbench share one global queue.

For temporary debugging only, set `CODEX_CLI_EXEC_LOCK=1` to serialize `codex
exec` child processes with a lock file. This can reduce CLI event-stream queue
pressure, but it also makes all Workbench instances that share the same lock
wait for one another. The older `CODEX_CLI_SERIALIZE_EXEC` variable is ignored
by current server code.

If the provider is slow to produce a final response after retries, increase
`CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS` from the default.

## Codex CLI Self Protection
Set `CODEX_CLI_SELF_PROTECT=1` to run only the Codex CLI child process with
Workbench/agent paths mounted read-only. Other Workbench APIs remain unchanged.

On Linux this uses `bwrap`. Linux hosts must have bubblewrap installed or
available on `PATH`; otherwise Codex CLI startup fails fast. On non-Linux hosts
the flag is ignored with a warning because bubblewrap is Linux-only.

By default it protects this Workbench checkout and an adjacent `codex_agent`
directory when present. Add comma-separated extra paths with
`CODEX_CLI_PROTECTED_PATHS=/path/to/codex_agent,/path/to/other`. Set
`CODEX_CLI_SELF_PROTECT_GIT_RW=1` to keep those protections but re-bind
protected `.git` directories read-write for Codex CLI git operations.

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

## File Download And Mail Limits
- File preview downloads are limited by `CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES`
  for one file and `CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES` for multi-file or
  folder zip downloads. Defaults are 64MB and 128MB; each can be raised up to
  512MB.
- Mail delivery uses `CODEX_MAIL_MAX_ARCHIVE_BYTES` for the generated zip
  attachment. The default is 20MB and the application cap is 128MB, but the
  SMTP provider can still reject attachments below that value.
- These limits exist because the current download and mail paths build the
  response/archive in server memory before the browser or SMTP server receives
  it. Going beyond these caps should use a streaming download or temporary-file
  archive flow instead of only raising environment variables.

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
