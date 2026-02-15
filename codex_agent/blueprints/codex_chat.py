"""Codex chat routes."""

import time

from flask import Blueprint, jsonify, request

from ..config import (
    CODEX_MAX_MODEL_CHARS,
    CODEX_MAX_PROMPT_CHARS,
    CODEX_MAX_REASONING_CHARS,
    CODEX_MAX_TITLE_CHARS,
    CODEX_MODEL_OPTIONS,
    CODEX_REASONING_OPTIONS,
)
from ..services.codex_chat import (
    append_message,
    build_codex_prompt,
    create_session,
    create_codex_stream,
    cleanup_codex_streams,
    delete_session,
    ensure_default_title,
    execute_codex_prompt,
    finalize_codex_stream,
    get_session,
    get_settings,
    get_usage_summary,
    list_codex_streams,
    read_codex_stream,
    list_sessions,
    rename_session,
    update_settings,
    stop_codex_stream,
)
from ..services.git_ops import run_git_action

bp = Blueprint('codex_chat', __name__)


@bp.route('/api/codex/settings')
def codex_settings():
    return jsonify({
        'settings': get_settings(),
        'model_options': CODEX_MODEL_OPTIONS,
        'reasoning_options': CODEX_REASONING_OPTIONS,
        'usage': get_usage_summary()
    })


@bp.route('/api/codex/settings', methods=['PATCH'])
def codex_settings_update():
    payload = request.get_json(silent=True) or {}
    model = payload.get('model')
    reasoning = payload.get('reasoning_effort')
    if model is not None:
        model = str(model).strip()
        if len(model) > CODEX_MAX_MODEL_CHARS:
            return jsonify({'error': '모델 이름이 너무 깁니다.'}), 400
    if reasoning is not None:
        reasoning = str(reasoning).strip()
        if len(reasoning) > CODEX_MAX_REASONING_CHARS:
            return jsonify({'error': 'reasoning_effort가 너무 깁니다.'}), 400
    settings = update_settings(model=model, reasoning_effort=reasoning)
    return jsonify({
        'settings': settings,
        'model_options': CODEX_MODEL_OPTIONS,
        'reasoning_options': CODEX_REASONING_OPTIONS,
        'usage': get_usage_summary()
    })


@bp.route('/api/codex/sessions')
def codex_sessions():
    return jsonify({'sessions': list_sessions()})


@bp.route('/api/codex/sessions', methods=['POST'])
def codex_sessions_create():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    session = create_session(title=title or None)
    return jsonify({'session': session})


@bp.route('/api/codex/sessions/<session_id>')
def codex_session_detail(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/codex/sessions/<session_id>', methods=['PATCH'])
def codex_session_rename(session_id):
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()

    if not title:
        return jsonify({'error': '세션 이름이 비어 있습니다.'}), 400
    if len(title) > CODEX_MAX_TITLE_CHARS:
        return jsonify({'error': '세션 이름이 너무 깁니다.'}), 400

    session = rename_session(session_id, title)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/codex/sessions/<session_id>', methods=['DELETE'])
def codex_session_delete(session_id):
    deleted = delete_session(session_id)
    if not deleted:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'status': 'deleted'})


@bp.route('/api/codex/sessions/<session_id>/message', methods=['POST'])
def codex_session_message(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    ensure_default_title(session_id, prompt)

    prompt_with_context = build_codex_prompt(session.get('messages', []), prompt)
    user_message = append_message(session_id, 'user', prompt)
    if not user_message:
        return jsonify({'error': '메시지를 저장하지 못했습니다.'}), 500

    started_at = time.time()
    output, error = execute_codex_prompt(prompt_with_context)
    duration_ms = max(0, int((time.time() - started_at) * 1000))
    metadata = {'duration_ms': duration_ms}
    if error:
        assistant_message = append_message(session_id, 'error', error, metadata)
    else:
        assistant_message = append_message(session_id, 'assistant', output or '', metadata)

    session = get_session(session_id)
    return jsonify({
        'session': session,
        'user_message': user_message,
        'assistant_message': assistant_message
    })


@bp.route('/api/codex/sessions/<session_id>/message/stream', methods=['POST'])
def codex_session_message_stream(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    ensure_default_title(session_id, prompt)
    prompt_with_context = build_codex_prompt(session.get('messages', []), prompt)
    user_message = append_message(session_id, 'user', prompt)
    if not user_message:
        return jsonify({'error': '메시지를 저장하지 못했습니다.'}), 500

    stream_id = create_codex_stream(session_id, prompt_with_context)
    return jsonify({'stream_id': stream_id, 'user_message': user_message})


@bp.route('/api/codex/streams/<stream_id>')
def codex_stream_output(stream_id):
    cleanup_codex_streams()
    try:
        output_offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        output_offset = 0
    try:
        error_offset = int(request.args.get('error_offset', 0))
    except (TypeError, ValueError):
        error_offset = 0

    output_offset = max(output_offset, 0)
    error_offset = max(error_offset, 0)

    data = read_codex_stream(stream_id, output_offset, error_offset)
    if not data:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404

    saved_message = None
    if data.get('done') and not data.get('saved'):
        saved_message = finalize_codex_stream(stream_id)
        data = read_codex_stream(stream_id, output_offset, error_offset)
        if data:
            data['saved'] = True

    response = data or {}
    if saved_message:
        response['saved_message'] = saved_message
    return jsonify(response)


@bp.route('/api/codex/streams')
def codex_streams_list():
    cleanup_codex_streams()
    include_done = request.args.get('include_done') == '1'
    return jsonify({'streams': list_codex_streams(include_done=include_done)})


@bp.route('/api/codex/streams/<stream_id>/stop', methods=['POST'])
def codex_stream_stop(stream_id):
    result = stop_codex_stream(stream_id)
    if not result:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404
    return jsonify(result)


@bp.route('/api/codex/git/<action>', methods=['POST', 'GET'])
def codex_git_action(action):
    if request.method == 'GET' and request.args.get('confirm') != '1':
        return jsonify({'error': 'GET 요청은 confirm=1이 필요합니다.'}), 400
    result = run_git_action(action)
    if not isinstance(result, dict):
        return jsonify({'error': 'git 작업 결과를 확인할 수 없습니다.'}), 500
    if result.get('error'):
        return jsonify({'error': result['error']}), 400
    if not result.get('ok'):
        message = result.get('stderr') or result.get('stdout') or f'git {action} 작업에 실패했습니다.'
        return jsonify({'error': message, 'result': result}), 400
    return jsonify(result)
