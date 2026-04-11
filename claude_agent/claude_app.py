"""Claude Agent Flask application wrapper."""

import os


def apply_claude_agent_defaults():
    os.environ.setdefault('MODEL_AGENT_UI_TITLE', 'Claude Agent')
    os.environ.setdefault('MODEL_AGENT_UI_SHORT_NAME', 'Claude')
    os.environ.setdefault('MODEL_AGENT_UI_DESCRIPTION', 'Manage Claude Agent sessions.')
    os.environ.setdefault('MODEL_AGENT_HEALTH_SERVICE', 'claude-agent')
    os.environ.setdefault('MODEL_AGENT_STORAGE_NAMESPACE', 'claude')
    os.environ.setdefault('MODEL_DEFAULT_PROVIDER', 'claude')
    os.environ.setdefault('MODEL_PROVIDER_OPTIONS', 'claude')
    os.environ.setdefault('MODEL_REASONING_OPTIONS', 'low,medium,high,max')


def create_claude_app():
    apply_claude_agent_defaults()

    from claude_agent.model_app import create_claude_app as _create_claude_app

    return _create_claude_app()
