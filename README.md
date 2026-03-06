# codex-agent

Codex chat server that powers the Configuration > Codex 채팅 UI.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex`)
- API key for at least one Model Agent provider (`gemini`, `openai`, `kimi`, or `glm`)

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

Run with the helper script:
```bash
./run_model_chat_server.sh
```

### Model Agent JSON Config
`run_model_chat_server.py` reads `./model_agent_config.json` automatically.

Update this single file to manage Model Agent runtime values:
- `server.host`, `server.port`, `server.debug`, `server.use_reloader`, `server.threaded`
- `agent.workspace_dir`, `agent.secret_key`, `agent.default_provider`, `agent.provider_options`
- `agent.providers.gemini.api_key`, `agent.providers.gemini.api_base_url`, `agent.providers.gemini.default_model`, `agent.providers.gemini.model_options`
- `agent.providers.openai.api_key`, `agent.providers.openai.api_base_url`, `agent.providers.openai.default_model`, `agent.providers.openai.model_options`
- `agent.providers.kimi.api_key`, `agent.providers.kimi.api_base_url`, `agent.providers.kimi.default_model`, `agent.providers.kimi.model_options`
- `agent.providers.glm.api_key`, `agent.providers.glm.api_base_url`, `agent.providers.glm.default_model`, `agent.providers.glm.model_options`
- `agent.reasoning_options`
- `agent.max_prompt_chars`, `agent.context_max_chars`, `agent.exec_timeout_seconds`, `agent.api_timeout_seconds`, `agent.stream_ttl_seconds`
- `agent.max_title_chars`, `agent.max_provider_chars`, `agent.max_model_chars`, `agent.max_reasoning_chars`

### Keep API Keys Out Of Git
`model_agent_config.json` supports env references like `${MODEL_GEMINI_API_KEY}`.

Recommended:
1. Keep `model_agent_config.json` committed with `${...}` placeholders only.
2. Put real keys in local `.env` (already gitignored).
3. Start from the template:

```bash
cp .env.example .env
```

4. Export env vars before running:

```bash
set -a
source .env
set +a
python run_model_chat_server.py
```

Example `.env`:

```bash
MODEL_GEMINI_API_KEY=your_real_gemini_key
MODEL_OPENAI_API_KEY=your_real_openai_key
MODEL_KIMI_API_KEY=your_real_kimi_key
MODEL_GLM_API_KEY=your_real_glm_key
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
