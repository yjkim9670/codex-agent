# DTGPT Agent (Tkinter)

Desktop chat agent focused on:
- Session list management (create, rename, delete)
- Chat messaging per session
- Provider/model switching between `gemini`, `dtgpt`, and `claude_code`
- Bubble-style chat UI with Markdown rendering and per-message/code copy buttons

Out-of-scope in this implementation:
- Location settings
- Weather lookup
- Git automation

## File layout

- `dtgpt_agent/app.py`: Tkinter UI
- `dtgpt_agent/chat_service.py`: chat workflow and prompt composition
- `dtgpt_agent/providers.py`: Gemini/DTGPT/Claude Code provider calls
- `dtgpt_agent/storage.py`: session/settings JSON persistence
- `dtgpt_agent/config.py`: environment/config values
- `dtgpt_agent/__main__.py`: app launcher (`python -m dtgpt_agent`)
- `dtgpt_agent/run_dtgpt_agent.sh`: quiet shell launcher (suppresses GUI noise logs by default, auto-loads `model_agent_env.local.sh` if present)

## Run

```bash
cd /home/dinya/codex_agent
python -m dtgpt_agent
```

Or run through shell wrapper:

```bash
./dtgpt_agent/run_dtgpt_agent.sh
```

To show every GUI stderr line (disable noise filtering):

```bash
DTGPT_AGENT_SHOW_GUI_NOISE=1 ./dtgpt_agent/run_dtgpt_agent.sh
```

Input note:
- Korean IME input is enabled in the Tk app (`tk useinputmethods` when supported).

## Environment variables

Core paths:
- `DTGPT_AGENT_WORKSPACE_DIR` (default: `./workspace`)
- `DTGPT_AGENT_CHAT_STORE_PATH` (default: `<workspace>/dtgpt_chat_sessions.json`)
- `DTGPT_AGENT_SETTINGS_PATH` (default: `<workspace>/dtgpt_settings.json`)

Provider settings:
- `MODEL_DEFAULT_PROVIDER` or `DTGPT_AGENT_DEFAULT_PROVIDER`
- `MODEL_GEMINI_API_KEY` (or fallback `MODEL_API_KEY`)
- `MODEL_GEMINI_API_BASE_URL`
- `MODEL_DTGPT_API_KEY`
- `MODEL_DTGPT_API_BASE_URL`
- `MODEL_DTGPT_API_BASE_URLS` (comma-separated)
- `MODEL_DTGPT_API_KEY_HEADER` (default: `Authorization`)
- `MODEL_DTGPT_API_KEY_PREFIX` (default: `Bearer`)
- `MODEL_DTGPT_API_KEY_ENV` (default: `DTGPT_API_KEY`)
- `MODEL_CLAUDE_CODE_COMMAND` (default: `claude`)
- `MODEL_CLAUDE_CODE_DEFAULT_MODEL` (default: `sonnet`)
- `MODEL_CLAUDE_CODE_MODEL_OPTIONS` (comma-separated)
- `MODEL_CLAUDE_CODE_PERMISSION_MODE` (default: `default`)
- `MODEL_CLAUDE_CODE_TOOLS` (default: empty string, disables tools in `--print` mode)

Claude Code note:
- Non-interactive execution uses `claude -p --output-format json`.
- Claude authentication must be valid (`claude` login/session). If expired, provider responses return the CLI error text.

Behavior tuning:
- `DTGPT_AGENT_MAX_PROMPT_CHARS`
- `DTGPT_AGENT_MAX_TITLE_CHARS`
- `DTGPT_AGENT_CONTEXT_MAX_CHARS`
- `DTGPT_AGENT_API_TIMEOUT_SECONDS`

## Bundle generator

Generate a single installer shell script that restores:
- `dtgpt_agent/`
- `model_agent_env.local.sh` (contains your DTGPT/Gemini API keys)

The generated installer is copied to clipboard by default:

```bash
python generate_dtgpt_agent_bundle.py --output /tmp/dtgpt_agent_bundle.sh
```

`model_agent_env.local.sh` is bundled as-is. Handle the generated bundle script as a secret file.

Skip clipboard copy:

```bash
python generate_dtgpt_agent_bundle.py --no-clipboard
```
