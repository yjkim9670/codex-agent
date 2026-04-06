"""Claude Agent Flask application wrapper."""

import os


def apply_claude_agent_defaults():
    os.environ.setdefault('MODEL_AGENT_UI_TITLE', 'Claude Agent')
    os.environ.setdefault('MODEL_AGENT_UI_SHORT_NAME', 'Claude')
    os.environ.setdefault('MODEL_AGENT_UI_DESCRIPTION', 'Manage Claude Agent sessions.')
    os.environ.setdefault('MODEL_AGENT_HEALTH_SERVICE', 'claude-agent')
    os.environ.setdefault('MODEL_AGENT_STORAGE_NAMESPACE', 'claude')


def create_claude_app():
    apply_claude_agent_defaults()

    from model_agent.model_app import create_model_app

    return create_model_app()
