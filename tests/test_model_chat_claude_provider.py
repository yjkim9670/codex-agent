from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_agent.services import model_chat


def test_build_claude_command_uses_only_p_option():
    cmd = model_chat._build_claude_command('hello world')
    assert cmd == ['claude', '-p', 'hello world']


def test_execute_claude_prompt_uses_only_p_option(monkeypatch, tmp_path):
    captured = {}

    class _FakeResult:
        returncode = 0
        stdout = 'ok'
        stderr = ''

    def _fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        captured['kwargs'] = kwargs
        return _FakeResult()

    monkeypatch.setattr(model_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(model_chat.subprocess, 'run', _fake_run)

    output, error = model_chat._execute_claude_prompt('stream test')

    assert output == 'ok'
    assert error is None
    assert captured['cmd'] == ['claude', '-p', 'stream test']


def test_execute_model_prompt_routes_to_claude(monkeypatch):
    called = {}

    def _fake_execute_claude(prompt):
        called['prompt'] = prompt
        return 'claude-output', None

    monkeypatch.setattr(model_chat, 'get_settings', lambda: {'provider': 'claude', 'model': 'unused'})
    monkeypatch.setattr(model_chat, '_execute_claude_prompt', _fake_execute_claude)

    output, error = model_chat.execute_model_prompt('routing test')

    assert output == 'claude-output'
    assert error is None
    assert called['prompt'] == 'routing test'


def test_get_provider_options_always_includes_claude(monkeypatch):
    monkeypatch.setattr(model_chat, 'MODEL_PROVIDER_OPTIONS', ['gemini', 'dtgpt'])
    monkeypatch.setattr(model_chat, 'MODEL_DEFAULT_PROVIDER', 'gemini')

    options = model_chat.get_provider_options()

    assert options == ['gemini', 'dtgpt', 'claude']


def test_get_model_options_for_claude_returns_default_only(monkeypatch):
    monkeypatch.setattr(model_chat, 'MODEL_CLAUDE_DEFAULT_MODEL', 'claude')
    monkeypatch.setattr(
        model_chat,
        'MODEL_PROVIDER_MODEL_OPTIONS',
        {
            'gemini': ['gemini-flash-latest'],
            'dtgpt': ['Kimi-K2.5'],
            'claude': ['claude', 'claude-sonnet-4-5'],
        },
    )

    options = model_chat.get_model_options('claude')

    assert options == ['claude']
