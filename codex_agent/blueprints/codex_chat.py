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
    cleanup_codex_streams,
    delete_session,
    ensure_default_title,
    execute_codex_prompt,
    finalize_codex_stream,
    get_active_stream_id_for_session,
    get_session,
    get_settings,
    get_usage_summary,
    list_codex_streams,
    read_codex_stream,
    list_sessions,
    rename_session,
    start_codex_stream_for_session,
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


@bp.route('/api/codex/usage')
def codex_usage():
    return jsonify({'usage': get_usage_summary()})


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

    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify({
            'error': '세션 응답이 실행 중일 때는 이름을 변경할 수 없습니다.',
            'active_stream_id': active_stream_id,
            'already_running': True
        }), 409

    session = rename_session(session_id, title)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/codex/sessions/<session_id>', methods=['DELETE'])
def codex_session_delete(session_id):
    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify({
            'error': '세션 응답이 실행 중일 때는 삭제할 수 없습니다.',
            'active_stream_id': active_stream_id,
            'already_running': True
        }), 409
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
    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify({
            'error': '이미 실행 중인 응답이 있습니다. 완료 후 다시 시도해 주세요.',
            'active_stream_id': active_stream_id,
            'already_running': True
        }), 409

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
    start_result = start_codex_stream_for_session(session_id, prompt, prompt_with_context)
    if not start_result.get('ok'):
        if start_result.get('already_running'):
            return jsonify({
                'error': '이미 실행 중인 응답이 있습니다. 기존 응답을 모니터링합니다.',
                'active_stream_id': start_result.get('active_stream_id'),
                'already_running': True
            }), 409
        return jsonify({'error': start_result.get('error') or '메시지를 저장하지 못했습니다.'}), 500

    return jsonify({
        'stream_id': start_result.get('stream_id'),
        'user_message': start_result.get('user_message')
    })


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
    payload = request.get_json(silent=True) or {}
    if request.method == 'GET':
        if action == 'push':
            if request.args.get('confirm') != '1':
                return jsonify({'error': 'push GET 요청은 confirm=1이 필요합니다.'}), 400
            payload = {'confirm': True}
        elif action == 'sync':
            payload = {'repo_target': request.args.get('repo_target') or 'codex_agent'}
        else:
            return jsonify({'error': 'GET 요청은 push(confirm=1) 또는 sync에서만 허용됩니다.'}), 400
    if not isinstance(payload, dict):
        payload = {}
    if action == 'sync' and not str(payload.get('repo_target') or '').strip():
        # Keep top-right sync pinned to codex_agent even if legacy clients omit payload.
        payload['repo_target'] = 'codex_agent'
    result = run_git_action(action, payload=payload)
    if not isinstance(result, dict):
        return jsonify({'error': 'git 작업 결과를 확인할 수 없습니다.'}), 500
    if result.get('error'):
        response_payload = {'error': result['error']}
        for key in (
            'error_code',
            'repo_target',
            'active_repo_target',
            'active_action',
            'active_elapsed_seconds',
            'cancel_requested',
            'cancelled_action'
        ):
            if key in result:
                response_payload[key] = result[key]
        return jsonify(response_payload), 400
    if not result.get('ok'):
        message = result.get('stderr') or result.get('stdout') or f'git {action} 작업에 실패했습니다.'
        response_payload = {'error': message, 'result': result}
        if result.get('error_code'):
            response_payload['error_code'] = result.get('error_code')
        return jsonify(response_payload), 400
    return jsonify(result)
