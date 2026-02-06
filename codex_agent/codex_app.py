"""Codex chat Flask application."""

from flask import Flask, request

from .blueprints import codex_chat
from .config import SECRET_KEY


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

    @app.route('/api/<path:_>', methods=['OPTIONS'])
    def codex_preflight(_):
        return ('', 204)

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
