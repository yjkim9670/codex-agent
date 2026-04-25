"""Codex Workbench Flask application."""

from fnmatch import fnmatchcase
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .blueprints import codex_chat
from .config import (
    CODEX_ALLOWED_ORIGINS,
    CODEX_API_ONLY_MODE,
    CODEX_ENABLE_FILES_API,
    CODEX_ENABLE_GIT_API,
    CODEX_REASONING_OPTIONS,
    SECRET_KEY,
    WORKSPACE_DIR,
    get_codex_model_options,
)
from .services.codex_chat import (
    ensure_pending_queue_background_worker,
    ensure_usage_snapshot_background_worker,
)
from .services.git_ops import get_current_branch_name


def _get_allowed_origins():
    return {
        origin
        for origin in CODEX_ALLOWED_ORIGINS
        if isinstance(origin, str) and origin.strip()
    }


def _is_origin_allowed(origin: str, allowed_origins) -> bool:
    if not origin:
        return False
    for allowed in allowed_origins:
        if allowed == '*':
            return True
        if origin == allowed:
            return True
        if any(token in allowed for token in ('*', '?', '[')) and fnmatchcase(origin, allowed):
            return True
    return False


def create_codex_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    app.config['SECRET_KEY'] = SECRET_KEY
    allowed_origins = _get_allowed_origins()

    app.register_blueprint(codex_chat.bp)
    ensure_usage_snapshot_background_worker()
    ensure_pending_queue_background_worker()

    def _build_runtime_context():
        server_directory = Path.cwd().resolve()
        workspace_directory = WORKSPACE_DIR.resolve()
        return {
            'server_directory_name': server_directory.name or str(server_directory),
            'server_directory_path': str(server_directory),
            'workspace_directory_name': workspace_directory.name or str(workspace_directory),
            'workspace_directory_path': str(workspace_directory),
            'current_branch_name': get_current_branch_name(),
            'mode': 'api-only' if CODEX_API_ONLY_MODE else 'ui+api',
            'feature_flags': {
                'files_api_enabled': bool(CODEX_ENABLE_FILES_API),
                'git_api_enabled': bool(CODEX_ENABLE_GIT_API),
            },
        }

    @app.route('/')
    def codex_root():
        runtime_context = _build_runtime_context()
        if CODEX_API_ONLY_MODE:
            return jsonify({
                'service': 'codex-workbench',
                'status': 'ok',
                'mode': runtime_context['mode'],
                'api': '/api/codex/sessions',
                'health': '/health',
                'runtime': runtime_context,
            })
        return render_template(
            'index.html',
            model_options=get_codex_model_options(),
            reasoning_options=CODEX_REASONING_OPTIONS,
            server_directory_name=runtime_context['server_directory_name'],
            server_directory_path=runtime_context['server_directory_path'],
            workspace_directory_name=runtime_context['workspace_directory_name'],
            workspace_directory_path=runtime_context['workspace_directory_path'],
            current_branch_name=runtime_context['current_branch_name'],
        )

    @app.route('/health')
    def codex_health():
        runtime_context = _build_runtime_context()
        return jsonify({
            'service': 'codex-workbench',
            'status': 'ok',
            'mode': runtime_context['mode'],
            'api': '/api/codex/sessions',
            'feature_flags': runtime_context['feature_flags'],
        })

    @app.route('/api/<path:_>', methods=['OPTIONS'])
    def codex_preflight(_):
        return ('', 204)

    @app.errorhandler(404)
    def codex_not_found(error):
        if request.path.startswith('/api/') or CODEX_API_ONLY_MODE:
            return jsonify({'error': 'API endpoint not found.'}), 404
        return error

    @app.errorhandler(405)
    def codex_method_not_allowed(error):
        if request.path.startswith('/api/') or CODEX_API_ONLY_MODE:
            return jsonify({'error': 'Method not allowed.'}), 405
        return error

    @app.errorhandler(500)
    def codex_server_error(error):
        if request.path.startswith('/api/') or CODEX_API_ONLY_MODE:
            return jsonify({'error': 'Internal server error.'}), 500
        return error

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get('Origin')
        if '*' in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = '*'
        elif _is_origin_allowed(origin or '', allowed_origins):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PATCH,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '600'
        return response

    return app
