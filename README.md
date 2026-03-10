# codex-agent

Codex chat server that powers the Configuration > Codex 채팅 UI.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex`)
- API key for at least one Model Agent provider (`gemini` or `dtgpt`)

## Setup
```bash
pip install -r requirements.txt
```

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

## Run Model Agent
```bash
python run_model_chat_server.py
```

Model Agent listens on `http://localhost:3100` by default.

If a model response includes a unified diff block (for example, fenced with `diff` or `patch`), Model Agent will attempt to apply it to `agent.workspace_dir` automatically via `git apply`.
Paths configured in `agent.workspace_blocked_paths` are excluded from Patch Apply and git stage/commit actions.

Run with the helper script:
```bash
./run_model_chat_server.sh
```

## Generate Model Agent Bundle Script
If you need a single shell script that recreates `model_agent/`, `run_model_chat_server.py`, `run_model_chat_server.sh`, and `model_agent_config.json` using per-file `gzip + base64` payloads:

```bash
python generate_model_agent_bundle.py --output /tmp/model_agent_bundle.sh
```

By default, the generated shell script is also copied to your clipboard (if a supported clipboard command is available).  
To skip clipboard copy:

```bash
python generate_model_agent_bundle.py --no-clipboard
```

Run the generated installer script:

```bash
bash /tmp/model_agent_bundle.sh /path/to/target/root
```

### Model Agent JSON Config
`run_model_chat_server.py` reads `./model_agent_config.json` automatically.

Update this single file to manage Model Agent runtime values:
- `server.host`, `server.port`, `server.debug`, `server.use_reloader`, `server.threaded`
- `agent.workspace_dir`, `agent.workspace_blocked_paths`, `agent.secret_key`, `agent.default_provider`, `agent.provider_options`
- `agent.providers.gemini.api_key`, `agent.providers.gemini.api_base_url`, `agent.providers.gemini.default_model`, `agent.providers.gemini.model_options`
- `agent.providers.dtgpt.api_key`, `agent.providers.dtgpt.api_key_env`, `agent.providers.dtgpt.api_key_header`, `agent.providers.dtgpt.api_key_prefix`, `agent.providers.dtgpt.api_base_url`, `agent.providers.dtgpt.api_base_urls`, `agent.providers.dtgpt.default_model`, `agent.providers.dtgpt.model_options`
- `agent.max_prompt_chars`, `agent.context_max_chars`, `agent.exec_timeout_seconds`, `agent.api_timeout_seconds`, `agent.stream_ttl_seconds`
- `agent.max_title_chars`, `agent.max_provider_chars`, `agent.max_model_chars`

### API Key Options
`model_agent_config.json` supports both:
- direct key values (plain text)
- env references like `${MODEL_GEMINI_API_KEY}`

If you want env-based loading, start from the template:

```bash
cp .env.example .env
```

Export env vars before running:

```bash
set -a
source .env
set +a
python run_model_chat_server.py
```

Example `.env`:

```bash
MODEL_GEMINI_API_KEY=your_real_gemini_key
MODEL_DTGPT_API_KEY=your_real_dtgpt_key
DTGPT_API_KEY=your_real_dtgpt_key
```

If you need another config path, set `MODEL_AGENT_CONFIG_PATH`.

## Git Sync Script
`z00_sync_git.py` is included for branch sync/mirror workflows.

Run:
```bash
python z00_sync_git.py
```

Default repository choices include:
- `https://github.com/yjkim9670/CommonTG-Verification-Platform`
- `https://github.com/yjkim9670/GL-FW-DV-Constraint-Review`
- `https://github.com/yjkim9670/codex-agent`

Protection rules are read from `sync_protect.list`.

## GUI
- `http://localhost:<port>/` serves the chat UI.
- `http://localhost:<port>/health` returns JSON status.
