"""Gemini chat Flask application."""

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .blueprints import gemini_chat
from .config import GEMINI_MODEL_OPTIONS, GEMINI_REASONING_OPTIONS, SECRET_KEY, WORKSPACE_DIR
from .services.git_ops import get_current_branch_name


def _get_allowed_origins():
    return {
        'http://localhost:4000',
        'http://127.0.0.1:4000'
    }


def create_gemini_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    app.config['SECRET_KEY'] = SECRET_KEY

    app.register_blueprint(gemini_chat.bp)

    @app.route('/')
    def gemini_root():
        server_directory = Path.cwd().resolve()
        server_directory_name = server_directory.name or str(server_directory)
        workspace_directory = WORKSPACE_DIR.resolve()
        workspace_directory_name = workspace_directory.name or str(workspace_directory)
        current_branch_name = get_current_branch_name()
        return render_template(
            'index.html',
            model_options=GEMINI_MODEL_OPTIONS,
            reasoning_options=GEMINI_REASONING_OPTIONS,
            server_directory_name=server_directory_name,
            server_directory_path=str(server_directory),
            workspace_directory_name=workspace_directory_name,
            workspace_directory_path=str(workspace_directory),
            current_branch_name=current_branch_name
        )

    @app.route('/health')
    def gemini_health():
        return jsonify({
            'service': 'gemini-agent',
            'status': 'ok',
            'api': '/api/gemini/sessions'
        })

    @app.route('/api/<path:_>', methods=['OPTIONS'])
    def gemini_preflight(_):
        return ('', 204)

    @app.errorhandler(404)
    def gemini_not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'API endpoint not found.'}), 404
        return error

    @app.errorhandler(405)
    def gemini_method_not_allowed(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Method not allowed.'}), 405
        return error

    @app.errorhandler(500)
    def gemini_server_error(error):
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
