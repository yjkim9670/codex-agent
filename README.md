# codex-agent

Codex chat server that powers the Configuration > Codex 채팅 UI.

## Requirements
- Python 3.10+
- Codex CLI available on PATH (`codex`)
- Gemini CLI available on PATH (`gemini`) for Gemini Agent

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

## Run Gemini Agent
```bash
python run_gemini_chat_server.py
```

Gemini Agent listens on `http://localhost:3100` by default.

Run with the helper script:
```bash
./run_gemini_chat_server.sh
```

## GUI
- `http://localhost:<port>/` serves the chat UI.
- `http://localhost:<port>/health` returns JSON status.
