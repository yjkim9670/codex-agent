"""Codex Workbench Flask application."""

from fnmatch import fnmatchcase
import os
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

from .blueprints import codex_chat
from .config import (
    CODEX_ALLOWED_ORIGINS,
    CODEX_API_ONLY_MODE,
    CODEX_ENABLE_FILES_API,
    CODEX_ENABLE_GIT_API,
    CODEX_REASONING_OPTIONS,
    CODEX_SERVICE_TIER_OPTIONS,
    SECRET_KEY,
    CODEX_INTERNAL_USER_MAP_PATH,
    CODEX_SHARED_KNOWLEDGE_DIR,
    CODEX_TRUSTED_PROXY_NETWORKS,
    is_internal_multiuser_mode,
    WORKSPACE_DIR,
    get_codex_agent_backend_options,
    get_codex_model_catalogs_by_agent_backend,
    get_codex_model_options,
    get_codex_security_policy,
)
from .services.codex_chat import (
    ensure_pending_queue_background_worker,
    ensure_usage_snapshot_background_worker,
)
from .services.codex_cli_output_filter import install_codex_cli_output_filter
from .services.file_browser import get_tmp_root_path
from .services.git_ops import get_current_branch_name
from .services.multiuser import InternalUser, activate_user, deactivate_user, load_ip_user_map, storage_key_for_ip


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


def _is_company_mode_enabled() -> bool:
    return str(os.environ.get('CODEX_COMPANY_MODE') or '').strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


def create_codex_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    app.config['SESSION_COOKIE_SECURE'] = str(
        os.environ.get('CODEX_SESSION_COOKIE_SECURE') or ''
    ).strip().lower() in {'1', 'true', 'yes', 'on'}
    allowed_origins = _get_allowed_origins()

    # Install once per server process. The filter keeps raw command/tool runtime
    # diagnostics in Codex event/raw-stderr data while keeping normal chat readable.
    install_codex_cli_output_filter()

    def _client_ip():
        remote = str(request.remote_addr or '').strip()
        # Forwarded client addresses are honored only when the TCP peer belongs
        # to a configured proxy network; otherwise this header is forgeable.
        try:
            trusted_proxy = any(__import__('ipaddress').ip_address(remote) in network for network in CODEX_TRUSTED_PROXY_NETWORKS)
        except ValueError:
            trusted_proxy = False
        if trusted_proxy:
            forwarded = str(request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
            if forwarded:
                return forwarded
        return remote

    @app.before_request
    def establish_internal_user_context():
        if not is_internal_multiuser_mode():
            return None
        client_ip = _client_ip()
        mapping = load_ip_user_map(CODEX_INTERNAL_USER_MAP_PATH)
        record = mapping.get(client_ip)
        if record is None:
            return jsonify({'error': '등록되지 않은 내부 사용자 IP입니다.', 'error_code': 'internal_user_not_registered'}), 403
        user = InternalUser(record['username'], record['role'], client_ip, storage_key_for_ip(client_ip), record.get('profile_configured', False))
        g.codex_current_user = user
        g.codex_user_context_token = activate_user(user)
        # Move pre-hash user roots created by earlier internal-mode releases
        # exactly once, preserving all existing chat, workspace and key data.
        hashed_root = Path(WORKSPACE_DIR).parent
        legacy_root = hashed_root.parent / user.username
        if not hashed_root.exists() and legacy_root.is_dir() and legacy_root != hashed_root:
            legacy_root.replace(hashed_root)
        # Provision only this user's empty workspace on first access.  The
        # scoped path prevents this from creating or exposing a shared root.
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        return None

    @app.teardown_request
    def clear_internal_user_context(_error=None):
        token = g.pop('codex_user_context_token', None)
        if token is not None:
            deactivate_user(token)

    app.register_blueprint(codex_chat.bp)
    if not is_internal_multiuser_mode():
        ensure_usage_snapshot_background_worker()
        ensure_pending_queue_background_worker()

    def _build_runtime_context():
        server_directory = Path.cwd().resolve()
        workspace_directory = WORKSPACE_DIR.resolve()
        internal_mode = is_internal_multiuser_mode()
        return {
            'server_directory_name': 'Restricted' if internal_mode else (server_directory.name or str(server_directory)),
            'server_directory_path': '' if internal_mode else str(server_directory),
            'tmp_directory_path': '' if internal_mode else str(get_tmp_root_path()),
            'workspace_directory_name': workspace_directory.name or str(workspace_directory),
            'workspace_directory_path': str(workspace_directory),
            'shared_knowledge_directory_path': str(CODEX_SHARED_KNOWLEDGE_DIR.resolve()) if internal_mode else '',
            'current_branch_name': get_current_branch_name(),
            'mode': 'api-only' if CODEX_API_ONLY_MODE else 'ui+api',
            'feature_flags': {
                'files_api_enabled': bool(CODEX_ENABLE_FILES_API),
                'git_api_enabled': bool(CODEX_ENABLE_GIT_API),
            },
            'security_policy': get_codex_security_policy(),
            'deployment_mode': 'internal-multiuser' if internal_mode else 'standalone',
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
            service_tier_options=CODEX_SERVICE_TIER_OPTIONS,
            agent_backend_options=get_codex_agent_backend_options(),
            model_catalogs_by_agent_backend=get_codex_model_catalogs_by_agent_backend(),
            security_policy=runtime_context['security_policy'],
            server_directory_name=runtime_context['server_directory_name'],
            server_directory_path=runtime_context['server_directory_path'],
            tmp_directory_path=runtime_context['tmp_directory_path'],
            workspace_directory_name=runtime_context['workspace_directory_name'],
            workspace_directory_path=runtime_context['workspace_directory_path'],
            shared_knowledge_directory_path=runtime_context['shared_knowledge_directory_path'],
            internal_multiuser_mode=is_internal_multiuser_mode(),
            current_internal_user=(
                {'username': g.codex_current_user.username, 'role': g.codex_current_user.role, 'profile_configured': g.codex_current_user.profile_configured}
                if is_internal_multiuser_mode() and getattr(g, 'codex_current_user', None) is not None
                else None
            ),
            current_branch_name=runtime_context['current_branch_name'],
            company_mode_enabled=_is_company_mode_enabled(),
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
            'security_policy': runtime_context['security_policy'],
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
        response.headers['Access-Control-Allow-Headers'] = (
            'Content-Type, Authorization, X-Codex-CSRF-Token'
        )
        response.headers['Access-Control-Max-Age'] = '600'
        return response

    return app
