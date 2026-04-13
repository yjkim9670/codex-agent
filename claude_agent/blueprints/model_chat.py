"""Model chat routes."""

import json
import re
import time
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

from ..config import (
    MODEL_MAX_MODEL_CHARS,
    MODEL_MAX_PROMPT_CHARS,
    MODEL_MAX_REASONING_CHARS,
    MODEL_MAX_TITLE_CHARS,
    REPO_ROOT,
    WORKSPACE_DIR,
)
from ..services.model_chat import (
    append_message,
    build_model_prompt,
    cleanup_model_streams,
    create_session,
    delete_session,
    ensure_default_title,
    ensure_usage_snapshot_background_worker,
    execute_model_prompt,
    finalize_assistant_output,
    finalize_model_stream,
    get_active_stream_id_for_session,
    get_claude_monitor_usage,
    get_monitor_rate_limits,
    get_model_options,
    get_reasoning_options,
    get_session_storage_summary,
    get_session,
    get_settings,
    get_usage_history_summary,
    get_usage_summary,
    list_model_streams,
    list_sessions,
    read_model_stream,
    record_usage_snapshot_if_due,
    rename_session,
    resolve_execution_profile,
    resolve_settings_preview,
    enqueue_model_stream_for_session,
    start_model_stream_for_session,
    stop_model_stream,
    update_settings,
)
from ..services.file_browser import (
    BROWSER_ROOT_SERVER,
    BROWSER_ROOT_WORKSPACE,
    FileBrowserError,
    list_directory,
    read_file,
    read_file_raw,
)
from ..services.git_ops import run_git_action

bp = Blueprint('model_chat', __name__)

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
_LAYOUT_ROOT_KEYS = {BROWSER_ROOT_SERVER, BROWSER_ROOT_WORKSPACE}
_LAYOUT_MAX_PATH_CHARS = 1024
_PROC_MANAGER_JOBS_PATH = Path.home() / 'proc_manager_jobs.json'
_MODEL_CHAT_JOB_COMMAND_HINTS = ('run_claude_chat_server.sh', 'run_claude_chat_server.py')
_MODEL_CHAT_DEBUG_ASSIGN_PATTERN = re.compile(
    r'(?:^|\s)(?:export\s+)?MODEL_CHAT_DEBUG\s*=\s*([^\s;#]+)',
    re.IGNORECASE,
)
_MODEL_CHAT_USE_RELOADER_ASSIGN_PATTERN = re.compile(
    r'(?:^|\s)(?:export\s+)?MODEL_CHAT_USE_RELOADER\s*=\s*([^\s;#]+)',
    re.IGNORECASE,
)
_DEBUG_FLAG_PATTERN = re.compile(r'(^|\s)--debug(\s|$)', re.IGNORECASE)


def _parse_plan_mode(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _PLAN_MODE_TRUTHY_VALUES
    return False


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


def _is_model_chat_job_config(job_config):
    commands = _extract_job_commands(job_config)
    if commands:
        merged = ' '.join(commands).lower()
        for hint in _MODEL_CHAT_JOB_COMMAND_HINTS:
            if hint in merged:
                return True
    name = str(job_config.get('name') or '').lower()
    return 'claude' in name and 'run_claude_chat_server' in name


def _resolve_model_chat_use_reloader(job_config):
    if not isinstance(job_config, dict):
        return None

    explicit_use_reloader = _to_optional_bool(job_config.get('use_reloader'))
    if explicit_use_reloader is not None:
        return explicit_use_reloader

    env_use_reloader_value = None
    env_debug_value = None
    has_debug_flag = False
    commands = _extract_job_commands(job_config)
    has_model_chat_entrypoint = False
    for command in commands:
        command_text = str(command or '')

        use_reloader_match = _MODEL_CHAT_USE_RELOADER_ASSIGN_PATTERN.search(command_text)
        if use_reloader_match:
            parsed_value = _to_optional_bool(use_reloader_match.group(1))
            env_use_reloader_value = parsed_value if parsed_value is not None else True

        debug_match = _MODEL_CHAT_DEBUG_ASSIGN_PATTERN.search(command_text)
        if debug_match:
            parsed_value = _to_optional_bool(debug_match.group(1))
            env_debug_value = parsed_value if parsed_value is not None else True

        lowered = command_text.lower()
        if 'run_claude_chat_server' in lowered:
            has_model_chat_entrypoint = True
            if _DEBUG_FLAG_PATTERN.search(command_text):
                has_debug_flag = True

    if env_use_reloader_value is not None:
        return env_use_reloader_value
    if has_debug_flag:
        return True
    if env_debug_value is not None:
        return env_debug_value
    if has_model_chat_entrypoint:
        return False
    return None


def _read_model_restart_policy():
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
        if not _is_model_chat_job_config(raw_job):
            continue
        matches.append(raw_job)

    result['matched_jobs'] = len(matches)
    if not matches:
        result['error'] = 'job_not_found'
        return result

    target_job = matches[0]
    restart_on_exit = _to_optional_bool(target_job.get('restart_on_exit'))
    use_reloader = _resolve_model_chat_use_reloader(target_job)
    result['restart_on_exit'] = restart_on_exit
    result['use_reloader'] = use_reloader
    result['known'] = use_reloader is not None
    result['job_name'] = str(target_job.get('name') or '').strip() or None
    if not result['known']:
        result['error'] = 'use_reloader_missing'
    return result


def _normalize_layout_root(value):
    normalized = str(value or '').strip().lower()
    if normalized in _LAYOUT_ROOT_KEYS:
        return normalized
    return BROWSER_ROOT_WORKSPACE


def _normalize_layout_relative_path(value):
    source = str(value or '').strip().replace('\\', '/')
    if not source or source == '.':
        return ''
    if len(source) > _LAYOUT_MAX_PATH_CHARS:
        source = source[:_LAYOUT_MAX_PATH_CHARS]
    if source.startswith('/') or source.startswith('~'):
        return ''
    normalized = source.strip('/')
    if not normalized:
        return ''
    if ':' in normalized:
        return ''
    parts = []
    for part in normalized.split('/'):
        if not part or part == '.':
            continue
        if part == '..' or '\x00' in part:
            return ''
        parts.append(part)
    return '/'.join(parts)


def _resolve_layout_root_path(root_key):
    normalized_root = _normalize_layout_root(root_key)
    if normalized_root == BROWSER_ROOT_SERVER:
        return Path.cwd().resolve()
    return WORKSPACE_DIR.resolve()


def _normalize_layout_context(value):
    payload = value if isinstance(value, dict) else {}
    context = {
        'work_mode_enabled': _parse_plan_mode(payload.get('work_mode_enabled')),
        'file_browser_open': _parse_plan_mode(payload.get('file_browser_open')),
        'active_root': _normalize_layout_root(payload.get('active_root')),
        'active_directory_path': _normalize_layout_relative_path(payload.get('active_directory_path')),
        'active_file_path': _normalize_layout_relative_path(payload.get('active_file_path')),
        'work_mode_root': _normalize_layout_root(payload.get('work_mode_root')),
        'work_mode_directory_path': _normalize_layout_relative_path(payload.get('work_mode_directory_path')),
        'work_mode_file_path': _normalize_layout_relative_path(payload.get('work_mode_file_path')),
    }

    if context['work_mode_enabled']:
        if not context['active_directory_path'] and context['work_mode_directory_path']:
            context['active_directory_path'] = context['work_mode_directory_path']
        if not context['active_file_path'] and context['work_mode_file_path']:
            context['active_file_path'] = context['work_mode_file_path']
    return context


def _resolve_layout_execution_cwd(layout_context):
    context = _normalize_layout_context(layout_context)
    root_path = _resolve_layout_root_path(context.get('active_root'))
    directory_path = context.get('active_directory_path') or ''
    file_path = context.get('active_file_path') or ''

    candidate = root_path
    if directory_path:
        candidate = root_path / directory_path
    elif file_path:
        candidate = (root_path / file_path).parent

    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_path)
    except Exception:
        resolved = root_path

    if not resolved.exists() or not resolved.is_dir():
        return str(root_path)
    return str(resolved)


def _resolve_layout_allowed_dirs(layout_context):
    context = _normalize_layout_context(layout_context)
    workspace_root = WORKSPACE_DIR.resolve()
    server_root = Path.cwd().resolve()
    active_root = _resolve_layout_root_path(context.get('active_root'))
    allowed = []
    for candidate in (workspace_root, server_root, active_root):
        normalized = str(candidate)
        if normalized and normalized not in allowed:
            allowed.append(normalized)
    return allowed


def _append_layout_context_prompt(prompt_text, layout_context):
    context = _normalize_layout_context(layout_context)
    active_root_key = context.get('active_root') or BROWSER_ROOT_WORKSPACE
    active_root_path = _resolve_layout_root_path(active_root_key)
    active_directory = context.get('active_directory_path') or ''
    active_file = context.get('active_file_path') or ''

    if active_directory:
        active_cwd = str((active_root_path / active_directory).resolve(strict=False))
    elif active_file:
        active_cwd = str(((active_root_path / active_file).resolve(strict=False)).parent)
    else:
        active_cwd = str(active_root_path)

    workspace_root = str(WORKSPACE_DIR.resolve())
    server_root = str(Path.cwd().resolve())
    work_mode_state = 'on' if context.get('work_mode_enabled') else 'off'
    browser_state = 'open' if context.get('file_browser_open') else 'closed'

    context_lines = [
        '## Current Layout Context',
        f'- Work mode: {work_mode_state}',
        f'- File browser: {browser_state}',
        f'- Active root: {active_root_key}',
        f'- Active directory: {active_directory or "/"}',
        f'- Active file: {active_file or "(none)"}',
        f'- Suggested working directory: {active_cwd}',
        f'- Root paths: workspace={workspace_root}, server={server_root}',
        '- Prefer these paths when running file and shell operations.',
    ]

    normalized_prompt = str(prompt_text or '').strip()
    if not normalized_prompt:
        normalized_prompt = '(empty)'
    return f'{normalized_prompt}\n\n' + '\n'.join(context_lines)


def _build_settings_response(
        model=None,
        reasoning_effort=None,
        plan_mode_model=None,
        plan_mode_reasoning_effort=None):
    settings = get_settings()
    settings_payload = dict(settings) if isinstance(settings, dict) else {}
    settings_payload.setdefault('model', settings_payload.get('model'))
    settings_payload.setdefault('plan_mode_model', settings_payload.get('plan_mode_model'))
    settings_payload.setdefault('reasoning_effort', settings_payload.get('reasoning_effort'))
    settings_payload.setdefault(
        'plan_mode_reasoning_effort',
        settings_payload.get('plan_mode_reasoning_effort'),
    )
    preview = resolve_settings_preview(
        model=model,
        reasoning_effort=reasoning_effort,
        plan_mode_model=plan_mode_model,
        plan_mode_reasoning_effort=plan_mode_reasoning_effort,
    )
    preview_payload = dict(preview) if isinstance(preview, dict) else {}
    preview_provider = preview.get('provider')
    usage = get_usage_summary()
    if isinstance(usage, dict) and (usage.get('five_hour') is None or usage.get('weekly') is None):
        try:
            rate_limits = get_monitor_rate_limits()
            if rate_limits:
                usage = dict(usage)
                if usage.get('five_hour') is None:
                    usage['five_hour'] = rate_limits.get('five_hour')
                if usage.get('weekly') is None:
                    usage['weekly'] = rate_limits.get('weekly')
        except Exception:
            pass
    return {
        'settings': settings_payload,
        'preview': preview_payload,
        'reasoning_options': get_reasoning_options(),
        'model_options': get_model_options(preview_provider),
        'usage': usage,
        'session_storage': get_session_storage_summary(),
    }


@bp.route('/api/claude/settings')
def model_settings():
    record_usage_snapshot_if_due()
    return jsonify(
        _build_settings_response(
            model=request.args.get('model'),
            reasoning_effort=request.args.get('reasoning_effort') or request.args.get('provider'),
            plan_mode_model=request.args.get('plan_mode_model'),
            plan_mode_reasoning_effort=(
                request.args.get('plan_mode_reasoning_effort')
                or request.args.get('plan_mode_provider')
            ),
        )
    )


@bp.route('/api/claude/usage')
def model_usage():
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    if isinstance(usage, dict) and (usage.get('five_hour') is None or usage.get('weekly') is None):
        try:
            rate_limits = get_monitor_rate_limits()
            if rate_limits:
                usage = dict(usage)
                if usage.get('five_hour') is None:
                    usage['five_hour'] = rate_limits.get('five_hour')
                if usage.get('weekly') is None:
                    usage['weekly'] = rate_limits.get('weekly')
        except Exception:
            pass
    return jsonify(
        {
            'usage': usage,
            'session_storage': get_session_storage_summary(),
        }
    )


@bp.route('/api/claude/usage/history')
def model_usage_history():
    hours = request.args.get('hours')
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    return jsonify(
        {
            'usage': usage,
            'usage_history': get_usage_history_summary(hours=hours),
            'session_storage': get_session_storage_summary(),
        }
    )


@bp.route('/api/claude/usage/monitor')
def model_usage_monitor():
    plan = request.args.get('plan', 'pro')
    hours_back = request.args.get('hours_back', 96)
    try:
        hours_back = int(hours_back)
    except (TypeError, ValueError):
        hours_back = 96
    result = get_claude_monitor_usage(plan=plan, hours_back=hours_back)
    if result.get('error'):
        return jsonify(result), 500
    return jsonify(result)


@bp.route('/api/claude/runtime/restart-policy')
def model_runtime_restart_policy():
    return jsonify(_read_model_restart_policy())


@bp.route('/api/claude/settings', methods=['PATCH'])
def model_settings_update():
    payload = request.get_json(silent=True) or {}
    reasoning_effort = payload.get('reasoning_effort')
    if reasoning_effort is None:
        # Compatibility fallback for older provider-based payloads.
        reasoning_effort = payload.get('provider')
    model = payload.get('model')
    plan_mode_reasoning_effort = payload.get('plan_mode_reasoning_effort')
    if plan_mode_reasoning_effort is None:
        plan_mode_reasoning_effort = payload.get('plan_mode_provider')
    plan_mode_model = payload.get('plan_mode_model')

    if reasoning_effort is not None:
        reasoning_effort = str(reasoning_effort).strip()
        if len(reasoning_effort) > MODEL_MAX_REASONING_CHARS:
            return jsonify({'error': 'reasoning_effort 값이 너무 깁니다.'}), 400
    if plan_mode_reasoning_effort is not None:
        plan_mode_reasoning_effort = str(plan_mode_reasoning_effort).strip()
        if len(plan_mode_reasoning_effort) > MODEL_MAX_REASONING_CHARS:
            return jsonify({'error': 'plan_mode_reasoning_effort 값이 너무 깁니다.'}), 400
    if model is not None:
        model = str(model).strip()
        if len(model) > MODEL_MAX_MODEL_CHARS:
            return jsonify({'error': '모델 이름이 너무 깁니다.'}), 400
    if plan_mode_model is not None:
        plan_mode_model = str(plan_mode_model).strip()
        if len(plan_mode_model) > MODEL_MAX_MODEL_CHARS:
            return jsonify({'error': 'plan_mode_model 값이 너무 깁니다.'}), 400

    update_settings(
        model=model,
        reasoning_effort=reasoning_effort,
        plan_mode_model=plan_mode_model,
        plan_mode_reasoning_effort=plan_mode_reasoning_effort,
    )
    return jsonify(_build_settings_response())


@bp.route('/api/claude/sessions')
def model_sessions():
    return jsonify(
        {
            'sessions': list_sessions(),
            'session_storage': get_session_storage_summary(),
        }
    )


@bp.route('/api/claude/sessions', methods=['POST'])
def model_sessions_create():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    session = create_session(title=title or None)
    return jsonify(
        {
            'session': session,
            'session_storage': get_session_storage_summary(),
        }
    )


@bp.route('/api/claude/sessions/<session_id>')
def model_session_detail(session_id):
    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'session': session})


@bp.route('/api/claude/sessions/<session_id>', methods=['PATCH'])
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


@bp.route('/api/claude/sessions/<session_id>', methods=['DELETE'])
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
    return jsonify(
        {
            'status': 'deleted',
            'session_storage': get_session_storage_summary(),
        }
    )


@bp.route('/api/claude/sessions/<session_id>/message', methods=['POST'])
def model_session_message(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    layout_context = _normalize_layout_context(payload.get('layout_context'))

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

    prompt_for_model = _append_layout_context_prompt(prompt, layout_context)
    prompt_with_context = build_model_prompt(session.get('messages', []), prompt_for_model)
    if plan_mode:
        prompt_with_context = _append_plan_mode_guardrails(prompt_with_context)

    execution_profile = resolve_execution_profile(plan_mode=plan_mode)
    execution_cwd = _resolve_layout_execution_cwd(layout_context)
    allowed_dirs = _resolve_layout_allowed_dirs(layout_context)
    user_message = append_message(session_id, 'user', prompt)
    if not user_message:
        return jsonify({'error': '메시지를 저장하지 못했습니다.'}), 500

    started_at = time.time()
    output, error = execute_model_prompt(
        prompt_with_context,
        provider_override=execution_profile.get('provider'),
        model_override=execution_profile.get('model'),
        reasoning_override=execution_profile.get('reasoning_effort'),
        plan_mode=plan_mode,
        execution_cwd=execution_cwd,
        allowed_dirs=allowed_dirs,
    )
    duration_ms = max(0, int((time.time() - started_at) * 1000))
    metadata = {'duration_ms': duration_ms}
    if error:
        assistant_message = append_message(session_id, 'error', error, metadata)
    else:
        final_output, patch_metadata = finalize_assistant_output(
            output or '',
            apply_side_effects=not plan_mode,
        )
        if isinstance(patch_metadata, dict):
            metadata.update(patch_metadata)
        assistant_message = append_message(session_id, 'assistant', final_output, metadata)

    session = get_session(session_id)
    return jsonify(
        {
            'session': session,
            'user_message': user_message,
            'assistant_message': assistant_message,
        }
    )


@bp.route('/api/claude/sessions/<session_id>/message/stream', methods=['POST'])
def model_session_message_stream(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    layout_context = _normalize_layout_context(payload.get('layout_context'))

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > MODEL_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    ensure_default_title(session_id, prompt)
    prompt_for_model = _append_layout_context_prompt(prompt, layout_context)
    prompt_with_context = build_model_prompt(session.get('messages', []), prompt_for_model)
    if plan_mode:
        prompt_with_context = _append_plan_mode_guardrails(prompt_with_context)
    execution_profile = resolve_execution_profile(plan_mode=plan_mode)
    execution_cwd = _resolve_layout_execution_cwd(layout_context)
    allowed_dirs = _resolve_layout_allowed_dirs(layout_context)
    start_result = start_model_stream_for_session(
        session_id,
        prompt,
        prompt_with_context,
        provider_override=execution_profile.get('provider'),
        model_override=execution_profile.get('model'),
        reasoning_override=execution_profile.get('reasoning_effort'),
        apply_side_effects=not plan_mode,
        plan_mode=plan_mode,
        execution_cwd=execution_cwd,
        allowed_dirs=allowed_dirs,
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

    return jsonify(
        {
            'stream_id': start_result.get('stream_id'),
            'started_at': start_result.get('started_at'),
            'user_message': start_result.get('user_message'),
        }
    )


@bp.route('/api/claude/sessions/<session_id>/message/queue', methods=['POST'])
def model_session_message_queue(session_id):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    layout_context = _normalize_layout_context(payload.get('layout_context'))

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > MODEL_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404

    result = enqueue_model_stream_for_session(
        session_id,
        prompt,
        plan_mode=plan_mode,
        layout_context=layout_context,
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
    return jsonify(response)


@bp.route('/api/claude/streams/<stream_id>')
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


@bp.route('/api/claude/streams')
def model_streams_list():
    cleanup_model_streams()
    include_done = request.args.get('include_done') == '1'
    return jsonify({'streams': list_model_streams(include_done=include_done)})


@bp.route('/api/claude/streams/<stream_id>/stop', methods=['POST'])
def model_stream_stop(stream_id):
    result = stop_model_stream(stream_id)
    if not result:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404
    return jsonify(result)


@bp.route('/api/claude/files/list', methods=['POST'])
def model_files_list():
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


@bp.route('/api/claude/files/read', methods=['POST'])
def model_files_read():
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


@bp.route('/api/claude/files/raw/<root_key>/<path:relative_path>')
def model_files_raw(root_key, relative_path):
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


@bp.route('/api/claude/git/<action>', methods=['POST', 'GET'])
def model_git_action(action):
    payload = request.get_json(silent=True) or {}
    if request.method == 'GET':
        if action == 'push':
            if request.args.get('confirm') != '1':
                return jsonify({'error': 'push GET 요청은 confirm=1이 필요합니다.'}), 400
            payload = {'confirm': True}
        elif action == 'sync':
            payload = {'repo_target': request.args.get('repo_target') or 'claude_agent'}
        else:
            return jsonify({'error': 'GET 요청은 push(confirm=1) 또는 sync에서만 허용됩니다.'}), 400
    if not isinstance(payload, dict):
        payload = {}
    if action == 'sync' and not str(payload.get('repo_target') or '').strip():
        # Keep top-right sync pinned to claude_agent even if legacy clients omit payload.
        payload['repo_target'] = 'claude_agent'
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
