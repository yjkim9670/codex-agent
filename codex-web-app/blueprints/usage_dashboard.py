"""Usage dashboard shares the app's existing request/user boundary."""
from flask import Blueprint, jsonify, render_template, request
from ..config import CODEX_API_ONLY_MODE
from ..services.usage_dashboard import dashboard

bp = Blueprint('usage_dashboard', __name__)


@bp.get('/usage')
def usage_page():
    if CODEX_API_ONLY_MODE:
        return jsonify({'error': 'UI disabled'}), 404
    return render_template('usage_dashboard.html')


@bp.get('/api/codex/usage/dashboard')
def usage_data():
    try:
        days = int(request.args.get('days', 30))
        if not 1 <= days <= 90:
            raise ValueError('기간은 1~90일이어야 합니다.')
        effort = request.args.get('effort', 'medium')
        if effort not in {'all', 'unknown', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}:
            raise ValueError('알 수 없는 effort입니다.')
        result = dashboard(request.args.get('account_id'), days, effort, request.args.get('environment', 'all'))
        return jsonify(result)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
