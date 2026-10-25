"""CommonTG documentation dashboard within the Workbench request boundary."""
from flask import Blueprint, g, jsonify, render_template, request
import subprocess
from ..config import CODEX_API_ONLY_MODE, is_internal_multiuser_mode
from ..services import metadata_sync

bp = Blueprint('metadata_sync', __name__)


@bp.before_request
def authorize():
    if is_internal_multiuser_mode() and getattr(g.get('codex_current_user'), 'role', '') != 'admin':
        return jsonify({'error': '관리자만 TG Platform 문서 동기화를 사용할 수 있습니다.'}), 403


@bp.get('/metadata-sync')
def page():
    if CODEX_API_ONLY_MODE:
        return jsonify({'error': 'UI disabled'}), 404
    return render_template('metadata_sync.html')


@bp.get('/api/codex/metadata-sync')
def history():
    return jsonify(metadata_sync.history())


@bp.get('/api/codex/metadata-sync/runs/<run_id>')
def detail(run_id):
    try:
        return jsonify(metadata_sync.detail(run_id))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except FileNotFoundError:
        return jsonify({'error': '실행 기록을 찾을 수 없습니다.'}), 404


@bp.get('/api/codex/metadata-sync/preview')
def preview():
    try:
        return jsonify(metadata_sync.preview())
    except subprocess.TimeoutExpired:
        return jsonify({'error': '변경 영향 분석 시간이 초과되었습니다. 다시 조회하세요.'}), 504
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 503


@bp.post('/api/codex/metadata-sync/run')
def run():
    if not request.is_json or request.headers.get('X-Workbench-Request') != 'metadata-sync':
        return jsonify({'error': 'Invalid request'}), 400
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        return jsonify({'error': 'Invalid origin'}), 403
    try:
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError('잘못된 요청입니다.')
        result = metadata_sync.start(payload.get('scope'))
        return jsonify(result), 202 if result['started'] else 409
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except (FileNotFoundError, OSError) as exc:
        return jsonify({'error': str(exc)}), 503
