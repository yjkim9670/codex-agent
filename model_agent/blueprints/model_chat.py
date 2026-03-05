"""Model chat routes."""

import time

from flask import Blueprint, jsonify, request

from ..config import (
    MODEL_MAX_MODEL_CHARS,
    MODEL_MAX_PROMPT_CHARS,
    MODEL_MAX_PROVIDER_CHARS,
    MODEL_MAX_REASONING_CHARS,
    MODEL_MAX_TITLE_CHARS,
)
from ..services.model_chat import (
    append_message,
    build_model_prompt,
    cleanup_model_streams,
    create_session,
    delete_session,
    ensure_default_title,
    execute_model_prompt,
    finalize_model_stream,
    get_active_stream_id_for_session,
    get_model_options,
    get_provider_options,
    get_reasoning_options,
    get_session,
    get_settings,
    get_usage_summary,
    list_model_streams,
    list_sessions,
    read_model_stream,
    rename_session,
    start_model_stream_for_session,
    stop_model_stream,
    update_settings,
)
from ..services.git_ops import run_git_action

bp = Blueprint('model_chat', __name__)


def _build_settings_response():
    settings = get_settings()
    provider = settings.get('provider')
    return {
        'settings': settings,
        'provider_options': get_provider_options(),
        'model_options': get_model_options(provider),
        'reasoning_options': get_reasoning_options(),
        'usage': get_usage_summary(),
    }


@bp.route('/api/model/settings')
def model_settings():
    return jsonify(_build_settings_response())


@bp.route('/api/model/usage')
def model_usage():
    return jsonify({'usage': get_usage_summary()})


@bp.route('/api/model/settings', methods=['PATCH'])
def model_settings_update():
    payload = request.get_json(silent=True) or {}
    provider = payload.get('provider')
    model = payload.get('model')
    reasoning = payload.get('reasoning_effort')

    if provider is not None:
        provider = str(provider).strip()
        if len(provider) > MODEL_MAX_PROVIDER_CHARS:
            return jsonify({'error': 'provider 값이 너무 깁니다.'}), 400
    if model is not None:
        model = str(model).strip()
        if len(model) > MODEL_MAX_MODEL_CHARS:
            return jsonify({'error': '모델 이름이 너무 깁니다.'}), 400
    if reasoning is not None:
        reasoning = str(reasoning).strip()
        if len(reasoning) > MODEL_MAX_REASONING_CHARS:
            return jsonify({'error': 'reasoning mode 값이 너무 깁니다.'}), 400

    update_settings(provider=provider, model=model, reasoning_effort=reasoning)
    return jsonify(_build_settings_response())


@bp.route('/api/model/sessions')
def model_sessions():
    return jsonify({'sessions': list_sessions()})


@bp.route('/api/model/sessions', methods=['POST'])
def model_sessions_create():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    session = create_session(title=title or None)
    return jsonify({'session': session})


@bp.route('/api/model/sessions/<session_id>')
def model_session_detail(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/model/sessions/<session_id>', methods=['PATCH'])
def model_session_rename(session_id):
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()

    if not title:
        return jsonify({'error': '세션 이름이 비어 있습니다.'}), 400
    if len(title) > MODEL_MAX_TITLE_CHARS:
        return jsonify({'error': '세션 이름이 너무 깁니다.'}), 400

    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify(
            {
                'error': '세션 응답이 실행 중일 때는 이름을 변경할 수 없습니다.',
                'active_stream_id': active_stream_id,
                'already_running': True,
            }
        ), 409

    session = rename_session(session_id, title)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/model/sessions/<session_id>', methods=['DELETE'])
def model_session_delete(session_id):
    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify(
            {
                'error': '세션 응답이 실행 중일 때는 삭제할 수 없습니다.',
                'active_stream_id': active_stream_id,
                'already_running': True,
            }
        ), 409
    deleted = delete_session(session_id)
    if not deleted:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'status': 'deleted'})


@bp.route('/api/model/sessions/<session_id>/message', methods=['POST'])
def model_session_message(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > MODEL_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify(
            {
                'error': '이미 실행 중인 응답이 있습니다. 완료 후 다시 시도해 주세요.',
                'active_stream_id': active_stream_id,
                'already_running': True,
            }
        ), 409

    ensure_default_title(session_id, prompt)

    prompt_with_context = build_model_prompt(session.get('messages', []), prompt)
    user_message = append_message(session_id, 'user', prompt)
    if not user_message:
        return jsonify({'error': '메시지를 저장하지 못했습니다.'}), 500

    started_at = time.time()
    output, error = execute_model_prompt(prompt_with_context)
    duration_ms = max(0, int((time.time() - started_at) * 1000))
    metadata = {'duration_ms': duration_ms}
    if error:
        assistant_message = append_message(session_id, 'error', error, metadata)
    else:
        assistant_message = append_message(session_id, 'assistant', output or '', metadata)

    session = get_session(session_id)
    return jsonify(
        {
            'session': session,
            'user_message': user_message,
            'assistant_message': assistant_message,
        }
    )


@bp.route('/api/model/sessions/<session_id>/message/stream', methods=['POST'])
def model_session_message_stream(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > MODEL_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    ensure_default_title(session_id, prompt)
    prompt_with_context = build_model_prompt(session.get('messages', []), prompt)
    start_result = start_model_stream_for_session(session_id, prompt, prompt_with_context)
    if not start_result.get('ok'):
        if start_result.get('already_running'):
            return jsonify(
                {
                    'error': '이미 실행 중인 응답이 있습니다. 기존 응답을 모니터링합니다.',
                    'active_stream_id': start_result.get('active_stream_id'),
                    'already_running': True,
                }
            ), 409
        return jsonify({'error': start_result.get('error') or '메시지를 저장하지 못했습니다.'}), 500

    return jsonify({'stream_id': start_result.get('stream_id'), 'user_message': start_result.get('user_message')})


@bp.route('/api/model/streams/<stream_id>')
def model_stream_output(stream_id):
    cleanup_model_streams()
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

    data = read_model_stream(stream_id, output_offset, error_offset)
    if not data:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404

    saved_message = None
    if data.get('done') and not data.get('saved'):
        saved_message = finalize_model_stream(stream_id)
        data = read_model_stream(stream_id, output_offset, error_offset)
        if data:
            data['saved'] = True

    response = data or {}
    if saved_message:
        response['saved_message'] = saved_message
    return jsonify(response)


@bp.route('/api/model/streams')
def model_streams_list():
    cleanup_model_streams()
    include_done = request.args.get('include_done') == '1'
    return jsonify({'streams': list_model_streams(include_done=include_done)})


@bp.route('/api/model/streams/<stream_id>/stop', methods=['POST'])
def model_stream_stop(stream_id):
    result = stop_model_stream(stream_id)
    if not result:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404
    return jsonify(result)


@bp.route('/api/model/git/<action>', methods=['POST', 'GET'])
def model_git_action(action):
    payload = request.get_json(silent=True) or {}
    if request.method == 'GET':
        if action == 'push':
            if request.args.get('confirm') != '1':
                return jsonify({'error': 'push GET 요청은 confirm=1이 필요합니다.'}), 400
            payload = {'confirm': True}
        elif action == 'sync':
            payload = {'repo_target': request.args.get('repo_target') or 'model_agent'}
        else:
            return jsonify({'error': 'GET 요청은 push(confirm=1) 또는 sync에서만 허용됩니다.'}), 400
    if not isinstance(payload, dict):
        payload = {}
    if action == 'sync' and not str(payload.get('repo_target') or '').strip():
        # Keep top-right sync pinned to model_agent even if legacy clients omit payload.
        payload['repo_target'] = 'model_agent'
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
            'cancelled_action',
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
