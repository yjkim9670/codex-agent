"""Codex chat routes."""

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ..config import (
    CODEX_API_ONLY_MODE,
    CODEX_ENABLE_FILES_API,
    CODEX_ENABLE_GIT_API,
    CODEX_MAX_ATTACHMENT_BYTES,
    CODEX_MAX_ATTACHMENTS_PER_TURN,
    CODEX_MAX_MODEL_CHARS,
    CODEX_MAX_PROMPT_CHARS,
    CODEX_MAX_REASONING_CHARS,
    CODEX_MAX_TITLE_CHARS,
    CODEX_REASONING_OPTIONS,
    REPO_ROOT,
    WORKSPACE_DIR,
    get_codex_model_catalog,
    get_codex_model_options,
)
from ..services.codex_chat import (
    append_message,
    build_codex_prompt,
    CodexAttachmentError,
    get_session_storage_summary,
    create_session,
    cleanup_codex_streams,
    delete_session,
    ensure_default_title,
    ensure_usage_snapshot_background_worker,
    execute_codex_prompt,
    finalize_codex_stream,
    get_active_stream_id_for_session,
    get_usage_history_summary,
    get_session,
    get_settings,
    get_usage_summary,
    list_codex_streams,
    read_codex_stream,
    list_sessions,
    normalize_codex_attachments,
    rename_session,
    record_usage_snapshot_if_due,
    record_token_usage_for_message,
    save_codex_attachment,
    start_codex_stream_for_session,
    enqueue_codex_stream_for_session,
    format_assistant_response_content,
    update_settings,
    resolve_response_mode_label,
    resolve_response_model_name,
    stop_codex_stream,
)
from ..services.file_browser import (
    FileBrowserError,
    build_download_payload,
    create_file,
    delete_directory,
    delete_files,
    list_directory,
    move_files,
    read_file,
    read_file_raw,
    upload_files,
    write_file,
)
from ..services.git_ops import get_current_branch_name, run_git_action
from ..services.terminal_sessions import (
    TerminalSessionError,
    close_terminal_session,
    create_terminal_session,
    iter_terminal_session_events,
    list_terminal_sessions,
    read_terminal_session,
    resize_terminal_session,
    write_terminal_input,
)

bp = Blueprint('codex_chat', __name__)

_PLAN_MODE_TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
_PLAN_MODE_FALSY_VALUES = {'0', 'false', 'no', 'off'}
_PLAN_MODE_PROMPT_SUFFIX = (
    "## Plan Mode Guardrails\n"
    "- Plan mode is enabled for this turn.\n"
    "- Do not modify files.\n"
    "- Do not run commands that create, edit, move, or delete files.\n"
    "- Provide analysis and an implementation plan only.\n"
    "- If changes are needed, describe proposed patches without applying them."
)
_PROC_MANAGER_JOBS_PATH = Path.home() / 'proc_manager_jobs.json'
_CODEX_JOB_COMMAND_HINTS = ('run_codex_chat_server.sh', 'run_codex_chat_server.py')
_CODEX_CHAT_DEBUG_ASSIGN_PATTERN = re.compile(
    r'(?:^|\s)(?:export\s+)?CODEX_CHAT_DEBUG\s*=\s*([^\s;#]+)',
    re.IGNORECASE,
)
_DEBUG_FLAG_PATTERN = re.compile(r'(^|\s)--debug(\s|$)', re.IGNORECASE)


def _format_sse_payload(data, *, event=None):
    payload = json.dumps(data or {}, ensure_ascii=False)
    lines = []
    if event and event != 'message':
        lines.append(f'event: {event}')
    for line in payload.splitlines() or ['']:
        lines.append(f'data: {line}')
    return ''.join(f'{line}\n' for line in lines) + '\n'


def _parse_plan_mode(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _PLAN_MODE_TRUTHY_VALUES
    return False


def _parse_attachments(payload):
    if not isinstance(payload, dict):
        return []
    return normalize_codex_attachments(payload.get('attachments') or [])


def _attachment_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    return jsonify({
        'error': str(error),
        'error_code': 'invalid_attachment',
    }), status_code


def _append_plan_mode_guardrails(prompt_text):
    normalized = str(prompt_text or '').strip()
    if not normalized:
        normalized = '(empty)'
    return f'{normalized}\n\n{_PLAN_MODE_PROMPT_SUFFIX}'


def _normalize_path_text(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return str(Path(text).expanduser().resolve())
    except Exception:  # noqa: BLE001
        return ''


def _to_optional_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _PLAN_MODE_TRUTHY_VALUES:
            return True
        if lowered in _PLAN_MODE_FALSY_VALUES:
            return False
    return None


def _extract_job_commands(job_config):
    if not isinstance(job_config, dict):
        return []
    raw_commands = job_config.get('commands')
    if raw_commands is None and 'cmd' in job_config:
        raw_commands = job_config.get('cmd')

    if isinstance(raw_commands, str):
        parts = raw_commands.splitlines()
    elif isinstance(raw_commands, list):
        parts = []
        for entry in raw_commands:
            if isinstance(entry, str):
                parts.extend(entry.splitlines())
    else:
        parts = []

    commands = []
    for part in parts:
        text = str(part).strip()
        if text:
            commands.append(text)
    return commands


def _is_codex_chat_job_config(job_config):
    commands = _extract_job_commands(job_config)
    if commands:
        merged = ' '.join(commands).lower()
        for hint in _CODEX_JOB_COMMAND_HINTS:
            if hint in merged:
                return True
    name = str(job_config.get('name') or '').lower()
    return 'codex' in name and 'run_codex_chat_server' in name


def _resolve_codex_use_reloader(job_config):
    if not isinstance(job_config, dict):
        return None

    explicit_use_reloader = _to_optional_bool(job_config.get('use_reloader'))
    if explicit_use_reloader is not None:
        return explicit_use_reloader

    env_debug_value = None
    has_debug_flag = False
    commands = _extract_job_commands(job_config)
    has_codex_entrypoint = False
    for command in commands:
        command_text = str(command or '')
        match = _CODEX_CHAT_DEBUG_ASSIGN_PATTERN.search(command_text)
        if match:
            parsed_value = _to_optional_bool(match.group(1))
            env_debug_value = parsed_value if parsed_value is not None else True

        lowered = command_text.lower()
        if 'run_codex_chat_server' in lowered:
            has_codex_entrypoint = True
            if _DEBUG_FLAG_PATTERN.search(command_text):
                has_debug_flag = True

    if has_debug_flag:
        return True
    if env_debug_value is not None:
        return env_debug_value
    if has_codex_entrypoint:
        return False
    return None


def _read_codex_restart_policy():
    repo_root = str(REPO_ROOT.resolve())
    result = {
        'known': False,
        'restart_on_exit': None,
        'use_reloader': None,
        'workdir': repo_root,
        'job_name': None,
        'matched_jobs': 0,
        'source_path': str(_PROC_MANAGER_JOBS_PATH),
        'source': 'proc_manager_jobs_json',
    }
    if not _PROC_MANAGER_JOBS_PATH.is_file():
        result['error'] = 'jobs_file_not_found'
        return result

    try:
        with _PROC_MANAGER_JOBS_PATH.open('r', encoding='utf-8') as fp:
            payload = json.load(fp)
    except Exception:  # noqa: BLE001
        result['error'] = 'jobs_file_unreadable'
        return result

    if isinstance(payload, dict):
        raw_jobs = payload.get('jobs', [])
    elif isinstance(payload, list):
        raw_jobs = payload
    else:
        result['error'] = 'jobs_payload_invalid'
        return result

    if not isinstance(raw_jobs, list):
        result['error'] = 'jobs_payload_invalid'
        return result

    matches = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        workdir = _normalize_path_text(raw_job.get('workdir'))
        if workdir != repo_root:
            continue
        if not _is_codex_chat_job_config(raw_job):
            continue
        matches.append(raw_job)

    result['matched_jobs'] = len(matches)
    if not matches:
        result['error'] = 'job_not_found'
        return result

    target_job = matches[0]
    restart_on_exit = _to_optional_bool(target_job.get('restart_on_exit'))
    use_reloader = _resolve_codex_use_reloader(target_job)
    result['restart_on_exit'] = restart_on_exit
    result['use_reloader'] = use_reloader
    result['known'] = use_reloader is not None
    result['job_name'] = str(target_job.get('name') or '').strip() or None
    if not result['known']:
        result['error'] = 'use_reloader_missing'
    return result


def _resolve_model_override(plan_mode=False):
    if not plan_mode:
        return None
    settings = get_settings()
    plan_mode_model = str(settings.get('plan_mode_model') or '').strip()
    if plan_mode_model:
        return plan_mode_model
    default_model = str(settings.get('model') or '').strip()
    return default_model or None


def _resolve_reasoning_override(plan_mode=False):
    settings = get_settings()
    if plan_mode:
        plan_mode_reasoning = str(settings.get('plan_mode_reasoning_effort') or '').strip()
        if plan_mode_reasoning:
            return plan_mode_reasoning
    default_reasoning = str(settings.get('reasoning_effort') or '').strip()
    return default_reasoning or None


def _feature_disabled_response(feature_key):
    return jsonify({
        'error': f'{feature_key} API가 서버 정책으로 비활성화되어 있습니다.',
        'error_code': f'{feature_key}_api_disabled',
    }), 403


def _build_runtime_info():
    server_directory = Path.cwd().resolve()
    workspace_directory = WORKSPACE_DIR.resolve()
    return {
        'service': 'codex-workbench',
        'mode': 'api-only' if CODEX_API_ONLY_MODE else 'ui+api',
        'server_directory_name': server_directory.name or str(server_directory),
        'server_directory_path': str(server_directory),
        'workspace_directory_name': workspace_directory.name or str(workspace_directory),
        'workspace_directory_path': str(workspace_directory),
        'current_branch_name': get_current_branch_name(),
        'model_options': get_codex_model_options(),
        'model_catalog': get_codex_model_catalog(),
        'reasoning_options': CODEX_REASONING_OPTIONS,
        'feature_flags': {
            'files_api_enabled': bool(CODEX_ENABLE_FILES_API),
            'git_api_enabled': bool(CODEX_ENABLE_GIT_API),
            'image_attachments_enabled': CODEX_MAX_ATTACHMENTS_PER_TURN > 0,
        },
        'attachments': {
            'max_per_turn': int(CODEX_MAX_ATTACHMENTS_PER_TURN),
            'max_bytes': int(CODEX_MAX_ATTACHMENT_BYTES),
        },
    }


@bp.route('/api/codex/runtime/info')
def codex_runtime_info():
    return jsonify(_build_runtime_info())


@bp.route('/api/codex/attachments', methods=['POST'])
def codex_attachment_upload():
    files = request.files.getlist('files')
    single_file = request.files.get('file')
    if single_file and single_file not in files:
        files.append(single_file)
    files = [item for item in files if item is not None]
    if not files:
        return jsonify({'error': '업로드할 이미지가 없습니다.', 'error_code': 'missing_attachment'}), 400
    if len(files) > CODEX_MAX_ATTACHMENTS_PER_TURN:
        return jsonify({
            'error': f'이미지는 한 번에 최대 {CODEX_MAX_ATTACHMENTS_PER_TURN}개까지 첨부할 수 있습니다.',
            'error_code': 'too_many_attachments',
        }), 400
    try:
        attachments = [save_codex_attachment(file_storage) for file_storage in files]
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)
    return jsonify({'attachments': attachments})


@bp.route('/api/codex/settings')
def codex_settings():
    ensure_usage_snapshot_background_worker()
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    return jsonify({
        'settings': get_settings(),
        'model_options': get_codex_model_options(),
        'model_catalog': get_codex_model_catalog(),
        'reasoning_options': CODEX_REASONING_OPTIONS,
        'usage': usage,
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/usage')
def codex_usage():
    ensure_usage_snapshot_background_worker()
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    return jsonify({
        'usage': usage,
        'usage_history': get_usage_history_summary(),
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/usage/history')
def codex_usage_history():
    ensure_usage_snapshot_background_worker()
    hours = request.args.get('hours')
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    return jsonify({
        'usage': usage,
        'usage_history': get_usage_history_summary(hours=hours),
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/runtime/restart-policy')
def codex_runtime_restart_policy():
    return jsonify(_read_codex_restart_policy())


@bp.route('/api/codex/settings', methods=['PATCH'])
def codex_settings_update():
    payload = request.get_json(silent=True) or {}
    model = payload.get('model')
    reasoning = payload.get('reasoning_effort')
    plan_mode_model = payload.get('plan_mode_model')
    plan_mode_reasoning = payload.get('plan_mode_reasoning_effort')
    if model is not None:
        model = str(model).strip()
        if len(model) > CODEX_MAX_MODEL_CHARS:
            return jsonify({'error': '모델 이름이 너무 깁니다.'}), 400
    if reasoning is not None:
        reasoning = str(reasoning).strip()
        if len(reasoning) > CODEX_MAX_REASONING_CHARS:
            return jsonify({'error': 'reasoning_effort가 너무 깁니다.'}), 400
    if plan_mode_model is not None:
        plan_mode_model = str(plan_mode_model).strip()
        if len(plan_mode_model) > CODEX_MAX_MODEL_CHARS:
            return jsonify({'error': 'plan_mode_model이 너무 깁니다.'}), 400
    if plan_mode_reasoning is not None:
        plan_mode_reasoning = str(plan_mode_reasoning).strip()
        if len(plan_mode_reasoning) > CODEX_MAX_REASONING_CHARS:
            return jsonify({'error': 'plan_mode_reasoning_effort가 너무 깁니다.'}), 400
    settings = update_settings(
        model=model,
        reasoning_effort=reasoning,
        plan_mode_model=plan_mode_model,
        plan_mode_reasoning_effort=plan_mode_reasoning,
    )
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    return jsonify({
        'settings': settings,
        'model_options': get_codex_model_options(),
        'model_catalog': get_codex_model_catalog(),
        'reasoning_options': CODEX_REASONING_OPTIONS,
        'usage': usage,
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/sessions')
def codex_sessions():
    return jsonify({
        'sessions': list_sessions(),
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/sessions', methods=['POST'])
def codex_sessions_create():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    session = create_session(title=title or None)
    return jsonify({
        'session': session,
        'session_storage': get_session_storage_summary(),
    })


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
    return jsonify({
        'status': 'deleted',
        'session_storage': get_session_storage_summary(),
    })


@bp.route('/api/codex/sessions/<session_id>/message', methods=['POST'])
def codex_session_message(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    ensure_default_title(session_id, prompt)

    prompt_with_context = build_codex_prompt(session.get('messages', []), prompt)
    if plan_mode:
        prompt_with_context = _append_plan_mode_guardrails(prompt_with_context)
    model_override = _resolve_model_override(plan_mode=plan_mode)
    reasoning_override = _resolve_reasoning_override(plan_mode=plan_mode)
    response_mode = resolve_response_mode_label(plan_mode=plan_mode)
    response_model = resolve_response_model_name(model_override=model_override)
    user_metadata = {'attachments': attachments} if attachments else None
    user_message = append_message(session_id, 'user', prompt, user_metadata)
    if not user_message:
        return jsonify({'error': '메시지를 저장하지 못했습니다.'}), 500

    started_at = time.time()
    output, error, token_usage, timing = execute_codex_prompt(
        prompt_with_context,
        model_override=model_override,
        reasoning_override=reasoning_override,
        attachments=attachments,
    )
    saved_at = time.time()
    duration_ms = max(0, int((saved_at - started_at) * 1000))
    metadata = {
        'duration_ms': duration_ms,
        'response_mode': response_mode,
        'response_model': response_model,
    }
    if isinstance(timing, dict):
        queue_wait_ms = int(timing.get('queue_wait_ms') or 0)
        cli_runtime_ms = int(timing.get('cli_runtime_ms') or 0)
        finalize_lag_ms = max(0, duration_ms - queue_wait_ms - cli_runtime_ms)
        metadata['queue_wait_ms'] = queue_wait_ms
        metadata['cli_runtime_ms'] = cli_runtime_ms
        metadata['finalize_lag_ms'] = finalize_lag_ms
    if isinstance(token_usage, dict):
        metadata['token_usage'] = token_usage
        metadata['token_count'] = int(token_usage.get('total_tokens') or 0)
        metadata['total_tokens'] = int(token_usage.get('total_tokens') or 0)
        metadata['input_tokens'] = int(token_usage.get('input_tokens') or 0)
        metadata['cached_input_tokens'] = int(token_usage.get('cached_input_tokens') or 0)
        metadata['output_tokens'] = int(token_usage.get('output_tokens') or 0)
        metadata['reasoning_output_tokens'] = int(token_usage.get('reasoning_output_tokens') or 0)
    if error:
        assistant_message = append_message(session_id, 'error', error, metadata)
    else:
        formatted_output = format_assistant_response_content(
            output or '',
            mode_label=response_mode,
            model_name=response_model,
        )
        assistant_message = append_message(session_id, 'assistant', formatted_output, metadata)
    if assistant_message:
        record_token_usage_for_message(
            session_id=session_id,
            message_id=assistant_message.get('id'),
            token_usage=token_usage,
            source='sync_message'
        )

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
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
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
    prompt_with_context = build_codex_prompt(session.get('messages', []), prompt)
    if plan_mode:
        prompt_with_context = _append_plan_mode_guardrails(prompt_with_context)
    model_override = _resolve_model_override(plan_mode=plan_mode)
    reasoning_override = _resolve_reasoning_override(plan_mode=plan_mode)
    start_result = start_codex_stream_for_session(
        session_id,
        prompt,
        prompt_with_context,
        model_override=model_override,
        reasoning_override=reasoning_override,
        plan_mode=plan_mode,
        attachments=attachments,
    )
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

    return jsonify({
        'stream_id': start_result.get('stream_id'),
        'started_at': start_result.get('started_at'),
        'user_message': start_result.get('user_message'),
        'assistant_message': start_result.get('assistant_message'),
        'assistant_message_id': start_result.get('assistant_message_id'),
        'response_mode': start_result.get('response_mode'),
        'response_model': start_result.get('response_model'),
    })


@bp.route('/api/codex/sessions/<session_id>/message/queue', methods=['POST'])
def codex_session_message_queue(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    result = enqueue_codex_stream_for_session(
        session_id,
        prompt,
        plan_mode=plan_mode,
        attachments=attachments,
    )
    if not result.get('ok'):
        return jsonify({'error': result.get('error') or '큐 등록에 실패했습니다.'}), 500

    response = {
        'queued': bool(result.get('queued', not result.get('started'))),
        'started': bool(result.get('started')),
        'queue_count': int(result.get('queue_count') or 0),
    }
    if result.get('active_stream_id'):
        response['active_stream_id'] = result.get('active_stream_id')
    if result.get('stream_id'):
        response['stream_id'] = result.get('stream_id')
        response['started_at'] = result.get('started_at')
        response['user_message'] = result.get('user_message')
        response['assistant_message'] = result.get('assistant_message')
        response['assistant_message_id'] = result.get('assistant_message_id')
        response['response_mode'] = result.get('response_mode')
        response['response_model'] = result.get('response_model')
    return jsonify(response)


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
    try:
        event_offset = int(request.args.get('event_offset', 0))
    except (TypeError, ValueError):
        event_offset = 0

    output_offset = max(output_offset, 0)
    error_offset = max(error_offset, 0)
    event_offset = max(event_offset, 0)

    data = read_codex_stream(stream_id, output_offset, error_offset, event_offset)
    if not data:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404

    saved_message = None
    if data.get('done') and not data.get('saved'):
        saved_message = finalize_codex_stream(stream_id)
        data = read_codex_stream(stream_id, output_offset, error_offset, event_offset)
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


@bp.route('/api/codex/files/list', methods=['POST'])
def codex_files_list():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = list_directory(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/read', methods=['POST'])
def codex_files_read():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = read_file(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/write', methods=['POST'])
def codex_files_write():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = write_file(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
            content=payload.get('content', ''),
            expected_modified_ns=payload.get('expected_modified_ns'),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/create', methods=['POST'])
def codex_files_create():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = create_file(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
            content=payload.get('content', ''),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/upload', methods=['POST'])
def codex_files_upload():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    files = request.files.getlist('files')
    single_file = request.files.get('file')
    if single_file and single_file not in files:
        files.append(single_file)
    try:
        result = upload_files(
            root_key=request.form.get('root'),
            relative_path=request.form.get('path', ''),
            file_storages=files,
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/raw/<root_key>/<path:relative_path>')
def codex_files_raw(root_key, relative_path):
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    try:
        result = read_file_raw(
            root_key=root_key,
            relative_path=relative_path,
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code

    mime_type = result.get('mime_type') or 'application/octet-stream'
    response = Response(result.get('content') or b'', mimetype=mime_type)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.route('/api/codex/files/download', methods=['POST'])
def codex_files_download():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = build_download_payload(
            root_key=payload.get('root'),
            relative_paths=payload.get('paths'),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code

    response = Response(
        result.get('content') or b'',
        mimetype=result.get('mime_type') or 'application/octet-stream',
    )
    download_name = str(result.get('download_name') or 'download.bin').strip() or 'download.bin'
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(download_name)}"
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.route('/api/codex/files/delete', methods=['POST'])
def codex_files_delete():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = delete_files(
            root_key=payload.get('root'),
            relative_paths=payload.get('paths'),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/delete-directory', methods=['POST'])
def codex_files_delete_directory():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = delete_directory(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/files/move', methods=['POST'])
def codex_files_move():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = move_files(
            root_key=payload.get('root'),
            relative_paths=payload.get('paths'),
            destination_path=payload.get('destination_path'),
            destination_directory=payload.get('destination_directory'),
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals')
def codex_terminals_list():
    try:
        result = list_terminal_sessions()
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals', methods=['POST'])
def codex_terminals_create():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = create_terminal_session(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
            cols=payload.get('cols'),
            rows=payload.get('rows'),
        )
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals/<session_id>')
def codex_terminals_read(session_id):
    try:
        result = read_terminal_session(
            session_id,
            offset=request.args.get('offset'),
        )
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals/<session_id>/events')
def codex_terminals_events(session_id):
    try:
        events = iter_terminal_session_events(
            session_id,
            offset=request.args.get('offset'),
        )
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code

    @stream_with_context
    def generate():
        yield 'retry: 1000\n\n'
        for item in events:
            yield _format_sse_payload(
                item.get('data'),
                event=item.get('event'),
            )

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@bp.route('/api/codex/terminals/<session_id>/input', methods=['POST'])
def codex_terminals_input(session_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = write_terminal_input(
            session_id,
            data=payload.get('data', ''),
        )
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals/<session_id>/resize', methods=['POST'])
def codex_terminals_resize(session_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = resize_terminal_session(
            session_id,
            cols=payload.get('cols'),
            rows=payload.get('rows'),
        )
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/terminals/<session_id>/close', methods=['POST'])
def codex_terminals_close(session_id):
    try:
        result = close_terminal_session(session_id)
    except TerminalSessionError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    return jsonify(result)


@bp.route('/api/codex/git/<action>', methods=['POST', 'GET'])
def codex_git_action(action):
    if not CODEX_ENABLE_GIT_API:
        return _feature_disabled_response('git')
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
        # Keep top-right sync pinned to the Workbench repo even if legacy clients omit payload.
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
            'cancelled_action',
            'windows_invalid_files',
            'windows_invalid_count',
            'has_windows_path_issues'
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
