# codex-agent

Codex chat server that powers the Configuration > Codex 채팅 UI.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex`)
- API key for at least one Model Agent provider (`gemini` or `openai`)

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
- `agent.reasoning_options`
- `agent.max_prompt_chars`, `agent.context_max_chars`, `agent.exec_timeout_seconds`, `agent.api_timeout_seconds`, `agent.stream_ttl_seconds`
- `agent.max_title_chars`, `agent.max_provider_chars`, `agent.max_model_chars`, `agent.max_reasoning_chars`

If you need another config path, set `MODEL_AGENT_CONFIG_PATH`.

## GUI
- `http://localhost:<port>/` serves the chat UI.
- `http://localhost:<port>/health` returns JSON status.
