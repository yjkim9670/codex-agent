"""Codex chat Flask application."""

from flask import Flask, jsonify, render_template, request

from .blueprints import codex_chat
from .config import CODEX_MODEL_OPTIONS, CODEX_REASONING_OPTIONS, SECRET_KEY


def _get_allowed_origins():
    return {
        'http://localhost:4000',
        'http://127.0.0.1:4000'
    }


def create_codex_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    app.config['SECRET_KEY'] = SECRET_KEY

    app.register_blueprint(codex_chat.bp)

    @app.route('/')
    def codex_root():
        return render_template(
            'index.html',
            model_options=CODEX_MODEL_OPTIONS,
            reasoning_options=CODEX_REASONING_OPTIONS
        )

    @app.route('/health')
    def codex_health():
        return jsonify({
            'service': 'codex-agent',
            'status': 'ok',
            'api': '/api/codex/sessions'
        })

    @app.route('/api/<path:_>', methods=['OPTIONS'])
    def codex_preflight(_):
        return ('', 204)

    @app.errorhandler(404)
    def codex_not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'API endpoint not found.'}), 404
        return error

    @app.errorhandler(405)
    def codex_method_not_allowed(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Method not allowed.'}), 405
        return error

    @app.errorhandler(500)
    def codex_server_error(error):
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
