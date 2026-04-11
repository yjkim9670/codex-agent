"""Claude chat Flask application."""

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .blueprints import model_chat
from .config import SECRET_KEY, WORKSPACE_DIR
from .services.git_ops import get_current_branch_name
from .services.model_chat import (
    ensure_pending_queue_background_worker,
    ensure_usage_snapshot_background_worker,
    get_model_options,
    get_reasoning_options,
    get_settings,
)


def _get_allowed_origins():
    return {'http://localhost:4000', 'http://127.0.0.1:4000'}


def _read_ui_value(env_name, default):
    value = str(os.environ.get(env_name) or '').strip()
    if value:
        return value
    return default


def create_claude_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    app.config['SECRET_KEY'] = SECRET_KEY

    app_name = _read_ui_value('MODEL_AGENT_UI_TITLE', 'Claude Agent')
    app_short_name = _read_ui_value('MODEL_AGENT_UI_SHORT_NAME', app_name)
    app_description = _read_ui_value(
        'MODEL_AGENT_UI_DESCRIPTION',
        f'Manage {app_name} sessions.',
    )
    health_service = _read_ui_value('MODEL_AGENT_HEALTH_SERVICE', 'claude-agent')
    chat_input_placeholder = _read_ui_value(
        'MODEL_AGENT_CHAT_INPUT_PLACEHOLDER',
        f'Type a prompt for {app_short_name}. (Shift+Enter for newline)',
    )
    server_directory_label = _read_ui_value(
        'MODEL_AGENT_SERVER_DIRECTORY_LABEL',
        f'{app_short_name} 서버 디렉터리',
    )

    app.register_blueprint(model_chat.bp)
    ensure_usage_snapshot_background_worker()
    ensure_pending_queue_background_worker()

    @app.route('/')
    def claude_root():
        server_directory = Path.cwd().resolve()
        server_directory_name = server_directory.name or str(server_directory)
        workspace_directory = WORKSPACE_DIR.resolve()
        workspace_directory_name = workspace_directory.name or str(workspace_directory)
        current_branch_name = get_current_branch_name()
        current_settings = get_settings()
        current_provider = current_settings.get('provider')
        return render_template(
            'index.html',
            reasoning_options=get_reasoning_options(),
            model_options=get_model_options(current_provider),
            server_directory_name=server_directory_name,
            server_directory_path=str(server_directory),
            workspace_directory_name=workspace_directory_name,
            workspace_directory_path=str(workspace_directory),
            current_branch_name=current_branch_name,
            app_name=app_name,
            app_short_name=app_short_name,
            app_description=app_description,
            chat_input_placeholder=chat_input_placeholder,
            server_directory_label=server_directory_label,
        )

    @app.route('/health')
    def claude_health():
        return jsonify({'service': health_service, 'status': 'ok', 'api': '/api/claude/sessions'})

    @app.route('/api/<path:_>', methods=['OPTIONS'])
    def claude_preflight(_):
        return ('', 204)

    @app.errorhandler(404)
    def claude_not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'API endpoint not found.'}), 404
        return error

    @app.errorhandler(405)
    def claude_method_not_allowed(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Method not allowed.'}), 405
        return error

    @app.errorhandler(500)
    def claude_server_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error.'}), 500
        return error

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get('Origin')
        allowed_origins = _get_allowed_origins()
        if origin in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PATCH,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    return app


def create_model_app():
    """Backward-compatible alias."""
    return create_claude_app()
