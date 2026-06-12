"""Codex chat routes."""

from fnmatch import fnmatchcase
from ipaddress import ip_address, ip_network
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ..config import (
    CODEX_ALLOW_TRUSTED_HTTP_CRYPTO_FALLBACK,
    CODEX_API_ONLY_MODE,
    CODEX_ENABLE_FILES_API,
    CODEX_ENABLE_GIT_API,
    CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES,
    CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES,
    CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS,
    CODEX_REQUIRE_ENCRYPTED_FILE_WRITES,
    CODEX_SHOW_USAGE_LIMITS,
    CODEX_TRUSTED_HTTP_CRYPTO_FALLBACK_HOSTS,
    CODEX_MAIL_FROM,
    CODEX_MAIL_MAX_ARCHIVE_BYTES,
    CODEX_MAIL_MAX_ARCHIVE_ENTRIES,
    CODEX_MAIL_PASSWORD,
    CODEX_MAIL_SMTP_HOST,
    CODEX_MAIL_SMTP_PORT,
    CODEX_MAIL_USERNAME,
    CODEX_MAX_ATTACHMENT_BYTES,
    CODEX_MAX_ATTACHMENTS_PER_TURN,
    CODEX_MAX_AGENT_BACKEND_CHARS,
    CODEX_MAX_MODEL_CHARS,
    CODEX_MAX_PROMPT_CHARS,
    CODEX_MAX_REASONING_CHARS,
    CODEX_MAX_SERVICE_TIER_CHARS,
    CODEX_MAX_TITLE_CHARS,
    CODEX_SERVICE_TIER_OPTIONS,
    REPO_ROOT,
    WORKSPACE_DIR,
    get_codex_model_catalog_for_backend,
    get_codex_model_catalog_source,
    get_codex_model_catalogs_by_agent_backend,
    get_codex_model_options_for_backend,
    get_codex_reasoning_options_for_backend,
    get_codex_security_policy,
    normalize_codex_agent_backend,
    normalize_codex_service_tier,
)
from ..services.codex_chat import (
    append_message,
    branch_session_from_message,
    build_codex_prompt,
    build_codex_app_server_thread_lifecycle_preview,
    build_repo_skill_preview,
    build_subagent_cockpit_preview,
    build_structured_report_prompt,
    CodexAppServerError,
    CodexAttachmentError,
    CodexToolingError,
    CodexWorktreeError,
    cleanup_git_worktree_task,
    create_repo_skill_from_preview,
    create_git_worktree_task,
    get_codex_project_safety_preview,
    get_session_storage_summary,
    get_selected_agent_backend,
    create_session,
    cleanup_codex_streams,
    delete_session,
    delete_session_message,
    ensure_default_title,
    ensure_usage_snapshot_background_worker,
    execute_codex_prompt,
    finalize_codex_stream,
    get_active_stream_id_for_session,
    get_codex_app_server_status,
    get_execution_policy_presets,
    get_agent_backend_options,
    get_usage_history_summary,
    get_session,
    get_settings,
    get_structured_report_preset,
    get_git_worktree_task,
    get_github_action_template_preview,
    get_mcp_setup_preview,
    get_usage_summary,
    handoff_git_worktree_task,
    fork_codex_app_server_thread,
    list_codex_app_server_features,
    list_codex_app_server_models,
    list_codex_app_server_threads,
    list_codex_app_server_thread_turns,
    list_structured_report_presets,
    list_subagent_cockpit_presets,
    list_codex_streams,
    list_git_worktree_tasks,
    read_codex_stream,
    list_sessions,
    normalize_codex_attachments,
    normalize_structured_report_preset_id,
    read_codex_app_server_thread,
    rename_session,
    record_usage_snapshot_if_due,
    record_token_usage_for_message,
    resume_codex_app_server_thread,
    save_codex_attachment,
    save_codex_project_safety_template,
    save_github_action_template_preview,
    save_mcp_setup_preview,
    start_codex_stream_for_session,
    start_codex_app_server_remote_control,
    start_subagent_cockpit_preset_for_session,
    start_codex_subjob_for_session,
    enqueue_codex_stream_for_session,
    format_assistant_response_content,
    update_settings,
    resolve_response_mode_label,
    resolve_response_model_name,
    resolve_response_reasoning_effort,
    stop_codex_app_server_remote_control,
    stop_codex_stream,
)
from ..services.file_browser import (
    FileBrowserError,
    build_download_payload,
    build_mail_archive_payload,
    create_file,
    delete_directory,
    delete_files,
    list_directory,
    move_files,
    read_file,
    read_file_raw,
    upload_files,
    write_file,
    write_file_patch,
)
from ..services.file_crypto import (
    FileCryptoError,
    create_chat_crypto_session,
    create_file_crypto_session,
    decrypt_chat_payload,
    decrypt_file_payload,
    encrypt_chat_payload,
    encrypt_file_payload,
    is_encrypted_chat_payload,
    is_encrypted_file_payload,
    validate_chat_crypto_session,
)
from ..services.git_ops import get_current_branch_name, run_git_action
from ..services.mail_sender import MailSendError, send_mail_with_archive
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
_CODEX_COMPANY_RUNNER_HINT = 'run_codex_chat_server_company.ps1'
_CODEX_JOB_COMMAND_HINTS = (
    'run_codex_chat_server.sh',
    'run_codex_chat_server.py',
    _CODEX_COMPANY_RUNNER_HINT,
)
_CODEX_CHAT_DEBUG_ASSIGN_PATTERN = re.compile(
    r'(?:^|\s)(?:export\s+)?CODEX_CHAT_DEBUG\s*=\s*([^\s;#]+)',
    re.IGNORECASE,
)
_DEBUG_FLAG_PATTERN = re.compile(r'(^|\s)--debug(\s|$)', re.IGNORECASE)
_RELOAD_FLAG_PATTERN = re.compile(r'(^|\s)--reload(\s|$)', re.IGNORECASE)
_TRUSTED_HTTP_CRYPTO_FALLBACK_HEADER = 'X-Codex-Trusted-Http-Fallback'
_CHAT_RESPONSE_CRYPTO_SESSION_HEADER = 'X-Codex-Chat-Crypto-Session'


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


def _parse_worktree_mode(payload):
    if not isinstance(payload, dict):
        return False
    value = payload.get('worktree_mode')
    if value is None:
        value = payload.get('worktree_task_mode')
    return _parse_plan_mode(value)


def _parse_attachments(payload):
    if not isinstance(payload, dict):
        return []
    return normalize_codex_attachments(payload.get('attachments') or [])


def _parse_structured_report_preset(payload):
    if not isinstance(payload, dict):
        return ''
    raw_value = payload.get('structured_report_preset')
    if raw_value is None or str(raw_value).strip() == '':
        return ''
    preset_id = normalize_structured_report_preset_id(raw_value)
    if not preset_id or not get_structured_report_preset(preset_id):
        raise ValueError('지원하지 않는 structured report preset입니다.')
    return preset_id


def _attachment_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    return jsonify({
        'error': str(error),
        'error_code': 'invalid_attachment',
    }), status_code


def _file_crypto_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    return jsonify({
        'error': str(error),
        'error_code': getattr(error, 'error_code', 'file_crypto_error'),
    }), status_code


def _normalize_http_host(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if text.startswith('['):
        closing_bracket = text.find(']')
        if closing_bracket > 0:
            text = text[1:closing_bracket]
        else:
            text = text.strip('[]')
    elif text.count(':') == 1:
        text = text.rsplit(':', 1)[0]
    return text.strip().strip('.').lower()


def _trusted_http_fallback_host_matches(host):
    normalized_host = _normalize_http_host(host)
    if not normalized_host:
        return False
    for raw_pattern in CODEX_TRUSTED_HTTP_CRYPTO_FALLBACK_HOSTS:
        pattern = _normalize_http_host(raw_pattern)
        if not pattern:
            continue
        if '/' in pattern:
            try:
                if ip_address(normalized_host) in ip_network(pattern, strict=False):
                    return True
            except ValueError:
                pass
        if normalized_host == pattern or fnmatchcase(normalized_host, pattern):
            return True
    return False


def _is_http_request_context():
    forwarded_proto = str(request.headers.get('X-Forwarded-Proto') or '')
    proto = forwarded_proto.split(',', 1)[0].strip().lower()
    if not proto:
        proto = str(request.scheme or '').strip().lower()
    return proto == 'http'


def _is_trusted_http_crypto_fallback_allowed():
    if not CODEX_ALLOW_TRUSTED_HTTP_CRYPTO_FALLBACK:
        return False
    if request.headers.get(_TRUSTED_HTTP_CRYPTO_FALLBACK_HEADER) != '1':
        return False
    if not _is_http_request_context():
        return False

    forwarded_host = str(request.headers.get('X-Forwarded-Host') or '')
    host_candidates = [
        forwarded_host.split(',', 1)[0].strip(),
        request.host,
    ]
    return any(_trusted_http_fallback_host_matches(host) for host in host_candidates)


def _decrypt_optional_file_payload(payload):
    if is_encrypted_file_payload(payload):
        return decrypt_file_payload(payload)
    return payload if isinstance(payload, dict) else {}, ''


def _jsonify_file_payload(result, crypto_session_id=''):
    if crypto_session_id:
        return jsonify(encrypt_file_payload(crypto_session_id, result))
    return jsonify(result)


def _decrypt_chat_prompt_payload(payload):
    if is_encrypted_chat_payload(payload):
        return decrypt_chat_payload(payload)
    if CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS and not _is_trusted_http_crypto_fallback_allowed():
        raise FileCryptoError(
            '채팅 프롬프트 요청은 암호화되어야 합니다.',
            error_code='encrypted_chat_prompt_required',
            status_code=400,
        )
    return payload if isinstance(payload, dict) else {}, ''


def _jsonify_chat_payload(result, crypto_session_id=''):
    if crypto_session_id:
        return jsonify(encrypt_chat_payload(crypto_session_id, result))
    return jsonify(result)


def _get_chat_response_crypto_session_id():
    crypto_session_id = str(request.headers.get(_CHAT_RESPONSE_CRYPTO_SESSION_HEADER) or '').strip()
    if crypto_session_id:
        return validate_chat_crypto_session(crypto_session_id)
    if CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS and not _is_trusted_http_crypto_fallback_allowed():
        raise FileCryptoError(
            '채팅 응답 요청은 암호화 세션이 필요합니다.',
            error_code='crypto_session_required',
            status_code=400,
        )
    return ''


def _jsonify_chat_payload_or_crypto_error(result, crypto_session_id=''):
    try:
        return _jsonify_chat_payload(result, crypto_session_id)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)


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
    has_reloader_flag = False
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
            if _CODEX_COMPANY_RUNNER_HINT in lowered:
                has_reloader_flag = True
            if _DEBUG_FLAG_PATTERN.search(command_text) or _RELOAD_FLAG_PATTERN.search(command_text):
                has_reloader_flag = True

    if has_reloader_flag:
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
    settings = get_settings()
    agent_backend = settings.get('agent_backend')
    return {
        'service': 'codex-workbench',
        'mode': 'api-only' if CODEX_API_ONLY_MODE else 'ui+api',
        'server_directory_name': server_directory.name or str(server_directory),
        'server_directory_path': str(server_directory),
        'workspace_directory_name': workspace_directory.name or str(workspace_directory),
        'workspace_directory_path': str(workspace_directory),
        'current_branch_name': get_current_branch_name(),
        'model_options': get_codex_model_options_for_backend(agent_backend),
        'model_catalog': get_codex_model_catalog_for_backend(agent_backend),
        'model_catalogs_by_agent_backend': get_codex_model_catalogs_by_agent_backend(),
        'model_catalog_source': get_codex_model_catalog_source(),
        'reasoning_options': get_codex_reasoning_options_for_backend(agent_backend),
        'service_tier_options': CODEX_SERVICE_TIER_OPTIONS,
        'agent_backend_options': get_agent_backend_options(),
        'security_policy': get_codex_security_policy(),
        'feature_flags': {
            'files_api_enabled': bool(CODEX_ENABLE_FILES_API),
            'git_api_enabled': bool(CODEX_ENABLE_GIT_API),
            'image_attachments_enabled': CODEX_MAX_ATTACHMENTS_PER_TURN > 0,
            'mail_api_enabled': bool(CODEX_ENABLE_FILES_API),
            'usage_limits_enabled': bool(CODEX_SHOW_USAGE_LIMITS),
        },
        'attachments': {
            'max_per_turn': int(CODEX_MAX_ATTACHMENTS_PER_TURN),
            'max_bytes': int(CODEX_MAX_ATTACHMENT_BYTES),
        },
        'file_download': {
            'max_single_bytes': int(CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES),
            'max_archive_bytes': int(CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES),
        },
        'mail': {
            'configured': bool(CODEX_MAIL_USERNAME and CODEX_MAIL_PASSWORD),
            'from': CODEX_MAIL_FROM or CODEX_MAIL_USERNAME,
            'smtp_host': CODEX_MAIL_SMTP_HOST,
            'smtp_port': int(CODEX_MAIL_SMTP_PORT),
            'max_archive_bytes': int(CODEX_MAIL_MAX_ARCHIVE_BYTES),
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
    settings = get_settings()
    agent_backend = settings.get('agent_backend')
    return jsonify({
        'settings': settings,
        'model_options': get_codex_model_options_for_backend(agent_backend),
        'model_catalog': get_codex_model_catalog_for_backend(agent_backend),
        'model_catalogs_by_agent_backend': get_codex_model_catalogs_by_agent_backend(),
        'model_catalog_source': get_codex_model_catalog_source(),
        'reasoning_options': get_codex_reasoning_options_for_backend(agent_backend),
        'service_tier_options': CODEX_SERVICE_TIER_OPTIONS,
        'agent_backend_options': get_agent_backend_options(),
        'execution_policy_presets': get_execution_policy_presets(),
        'structured_report_presets': list_structured_report_presets(),
        'app_server_status': get_codex_app_server_status(),
        'usage': usage,
        'session_storage': get_session_storage_summary(),
        'security_policy': get_codex_security_policy(),
        'feature_flags': {
            'usage_limits_enabled': bool(CODEX_SHOW_USAGE_LIMITS),
        },
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
        'feature_flags': {
            'usage_limits_enabled': bool(CODEX_SHOW_USAGE_LIMITS),
        },
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
        'feature_flags': {
            'usage_limits_enabled': bool(CODEX_SHOW_USAGE_LIMITS),
        },
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
    service_tier = payload.get('service_tier')
    agent_backend = payload.get('agent_backend')
    app_server_pilot_enabled = None
    if 'app_server_pilot_enabled' in payload:
        app_server_pilot_enabled = _to_optional_bool(payload.get('app_server_pilot_enabled'))
        if app_server_pilot_enabled is None:
            return jsonify({'error': 'app_server_pilot_enabled 값이 올바르지 않습니다.'}), 400
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
    if service_tier is not None:
        service_tier = str(service_tier).strip()
        if len(service_tier) > CODEX_MAX_SERVICE_TIER_CHARS:
            return jsonify({'error': 'service_tier가 너무 깁니다.'}), 400
        normalized_service_tier = normalize_codex_service_tier(service_tier)
        supported_service_tiers = {
            item.get('id')
            for item in CODEX_SERVICE_TIER_OPTIONS
            if isinstance(item, dict) and item.get('id')
        }
        if normalized_service_tier and normalized_service_tier not in supported_service_tiers:
            return jsonify({'error': 'service_tier 값이 올바르지 않습니다.'}), 400
        service_tier = normalized_service_tier or ''
    if agent_backend is not None:
        agent_backend = str(agent_backend).strip()
        if len(agent_backend) > CODEX_MAX_AGENT_BACKEND_CHARS:
            return jsonify({'error': 'agent_backend 값이 너무 깁니다.'}), 400
        normalized_agent_backend = normalize_codex_agent_backend(agent_backend)
        supported_agent_backends = {
            item.get('id')
            for item in get_agent_backend_options()
            if isinstance(item, dict) and item.get('id')
        }
        if not normalized_agent_backend or normalized_agent_backend not in supported_agent_backends:
            return jsonify({'error': 'agent_backend 값이 올바르지 않습니다.'}), 400
        agent_backend = normalized_agent_backend
    settings = update_settings(
        model=model,
        reasoning_effort=reasoning,
        plan_mode_model=plan_mode_model,
        plan_mode_reasoning_effort=plan_mode_reasoning,
        service_tier=service_tier,
        agent_backend=agent_backend,
        app_server_pilot_enabled=app_server_pilot_enabled,
    )
    snapshot = record_usage_snapshot_if_due()
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = get_usage_summary()
    agent_backend = settings.get('agent_backend')
    return jsonify({
        'settings': settings,
        'model_options': get_codex_model_options_for_backend(agent_backend),
        'model_catalog': get_codex_model_catalog_for_backend(agent_backend),
        'model_catalogs_by_agent_backend': get_codex_model_catalogs_by_agent_backend(),
        'model_catalog_source': get_codex_model_catalog_source(),
        'reasoning_options': get_codex_reasoning_options_for_backend(agent_backend),
        'service_tier_options': CODEX_SERVICE_TIER_OPTIONS,
        'agent_backend_options': get_agent_backend_options(),
        'execution_policy_presets': get_execution_policy_presets(),
        'structured_report_presets': list_structured_report_presets(),
        'app_server_status': get_codex_app_server_status(),
        'usage': usage,
        'session_storage': get_session_storage_summary(),
        'security_policy': get_codex_security_policy(),
        'feature_flags': {
            'usage_limits_enabled': bool(CODEX_SHOW_USAGE_LIMITS),
        },
    })


def _app_server_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    payload = {
        'error': str(error),
        'error_code': getattr(error, 'error_code', 'app_server_error'),
    }
    details = getattr(error, 'details', None)
    if isinstance(details, dict) and details:
        payload['details'] = details
    return jsonify(payload), status_code


def _tooling_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    payload = {
        'error': str(error),
        'error_code': getattr(error, 'error_code', 'tooling_error'),
    }
    details = getattr(error, 'details', None)
    if isinstance(details, dict) and details:
        payload['details'] = details
    return jsonify(payload), status_code


def _parse_app_server_limit(default=20, maximum=100):
    try:
        limit = int(request.args.get('limit', default))
    except (TypeError, ValueError):
        limit = default
    return max(1, min(int(maximum), limit))


@bp.route('/api/codex/app-server/status')
def codex_app_server_status():
    return jsonify({'status': get_codex_app_server_status()})


@bp.route('/api/codex/app-server/remote-control/start', methods=['POST'])
def codex_app_server_remote_control_start():
    try:
        return jsonify({'ok': True, 'status': start_codex_app_server_remote_control()})
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/remote-control/stop', methods=['POST'])
def codex_app_server_remote_control_stop():
    try:
        return jsonify({'ok': True, 'status': stop_codex_app_server_remote_control()})
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/models')
def codex_app_server_models():
    include_hidden = _parse_plan_mode(request.args.get('include_hidden'))
    cursor = request.args.get('cursor')
    try:
        payload = list_codex_app_server_models(
            limit=_parse_app_server_limit(default=20, maximum=100),
            include_hidden=include_hidden,
            cursor=cursor,
        )
        return jsonify(payload)
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/features')
def codex_app_server_features():
    cursor = request.args.get('cursor')
    try:
        payload = list_codex_app_server_features(
            limit=_parse_app_server_limit(default=50, maximum=200),
            cursor=cursor,
        )
        return jsonify(payload)
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads')
def codex_app_server_threads():
    cursor = request.args.get('cursor')
    search_term = request.args.get('search', '')
    cwd = request.args.get('cwd', '')
    include_exec = request.args.get('include_exec', '1') != '0'
    try:
        payload = list_codex_app_server_threads(
            limit=_parse_app_server_limit(default=20, maximum=100),
            cursor=cursor,
            search_term=search_term,
            cwd=cwd,
            include_exec=include_exec,
        )
        return jsonify(payload)
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads/<thread_id>')
def codex_app_server_thread_detail(thread_id):
    include_turns = _parse_plan_mode(request.args.get('include_turns'))
    try:
        return jsonify(read_codex_app_server_thread(thread_id, include_turns=include_turns))
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads/<thread_id>/turns')
def codex_app_server_thread_turns(thread_id):
    cursor = request.args.get('cursor')
    try:
        return jsonify(list_codex_app_server_thread_turns(
            thread_id,
            limit=_parse_app_server_limit(default=20, maximum=100),
            cursor=cursor,
        ))
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads/<thread_id>/resume', methods=['POST'])
def codex_app_server_thread_resume(thread_id):
    try:
        return jsonify({'ok': True, **resume_codex_app_server_thread(thread_id)})
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads/<thread_id>/fork', methods=['POST'])
def codex_app_server_thread_fork(thread_id):
    try:
        return jsonify({'ok': True, **fork_codex_app_server_thread(thread_id)})
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/app-server/threads/<thread_id>/lifecycle-preview', methods=['POST'])
def codex_app_server_thread_lifecycle_preview(thread_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    action = payload.get('action') or request.args.get('action')
    turn_id = payload.get('turn_id') or payload.get('turnId') or request.args.get('turn_id')
    try:
        preview = build_codex_app_server_thread_lifecycle_preview(thread_id, action, turn_id=turn_id)
        return jsonify({'ok': True, 'preview': preview})
    except CodexAppServerError as exc:
        return _app_server_error_response(exc)


@bp.route('/api/codex/tooling/subagents/presets')
def codex_tooling_subagent_presets():
    return jsonify({'presets': list_subagent_cockpit_presets()})


@bp.route('/api/codex/sessions/<session_id>/subagent-presets/<preset_id>/preview', methods=['POST'])
def codex_session_subagent_preset_preview(session_id, preset_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    prompt = str(payload.get('prompt') or '').strip()
    try:
        preview = build_subagent_cockpit_preview(preset_id, prompt)
    except CodexToolingError as exc:
        return _tooling_error_response(exc)
    return _jsonify_chat_payload(
        {'ok': True, 'parent_session_id': session_id, 'preview': preview},
        crypto_session_id,
    )


@bp.route('/api/codex/sessions/<session_id>/subagent-presets/<preset_id>/run', methods=['POST'])
def codex_session_subagent_preset_run(session_id, preset_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    prompt = str(payload.get('prompt') or '').strip()
    try:
        attachments = _parse_attachments(payload)
        result = start_subagent_cockpit_preset_for_session(
            session_id,
            preset_id,
            base_prompt=prompt,
            attachments=attachments,
        )
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)
    except CodexToolingError as exc:
        return _tooling_error_response(exc)
    if not result.get('ok') and int(result.get('started_count') or 0) <= 0:
        return jsonify(result), 400
    result['session_storage'] = get_session_storage_summary()
    return _jsonify_chat_payload(result, crypto_session_id)


@bp.route('/api/codex/tooling/skills/preview', methods=['POST'])
def codex_tooling_skill_preview():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        preview = build_repo_skill_preview(
            payload.get('name'),
            trigger=payload.get('trigger') or '',
            description=payload.get('description') or '',
            include_references=payload.get('include_references', True) is not False,
            include_scripts=payload.get('include_scripts', True) is not False,
            include_assets=payload.get('include_assets', True) is not False,
        )
        return jsonify({'ok': True, 'preview': preview})
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/skills', methods=['POST'])
def codex_tooling_skill_create():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = create_repo_skill_from_preview(
            payload.get('name'),
            trigger=payload.get('trigger') or '',
            description=payload.get('description') or '',
            include_references=payload.get('include_references', True) is not False,
            include_scripts=payload.get('include_scripts', True) is not False,
            include_assets=payload.get('include_assets', True) is not False,
            overwrite=_parse_plan_mode(payload.get('overwrite')),
        )
        return jsonify(result)
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/project-safety/preview')
def codex_tooling_project_safety_preview():
    try:
        return jsonify(get_codex_project_safety_preview())
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/project-safety/templates/<template_id>', methods=['POST'])
def codex_tooling_project_safety_template_save(template_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        return jsonify(save_codex_project_safety_template(
            template_id,
            overwrite=_parse_plan_mode(payload.get('overwrite')),
        ))
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/mcp/preview')
def codex_tooling_mcp_preview():
    try:
        return jsonify(get_mcp_setup_preview())
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/mcp/save-preview', methods=['POST'])
def codex_tooling_mcp_save_preview():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        return jsonify(save_mcp_setup_preview(overwrite=_parse_plan_mode(payload.get('overwrite'))))
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/github-actions/preview')
def codex_tooling_github_actions_preview():
    kind = request.args.get('kind', 'pr_review')
    try:
        return jsonify(get_github_action_template_preview(kind))
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/tooling/github-actions/save-preview', methods=['POST'])
def codex_tooling_github_actions_save_preview():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        return jsonify(save_github_action_template_preview(
            kind=payload.get('kind') or 'pr_review',
            overwrite=_parse_plan_mode(payload.get('overwrite')),
        ))
    except CodexToolingError as exc:
        return _tooling_error_response(exc)


@bp.route('/api/codex/sessions')
def codex_sessions():
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    return _jsonify_chat_payload_or_crypto_error({
        'sessions': list_sessions(),
        'session_storage': get_session_storage_summary(),
    }, crypto_session_id)


@bp.route('/api/codex/chat/crypto-session', methods=['POST'])
def codex_chat_crypto_session():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = create_chat_crypto_session(payload.get('client_public_key'))
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    return jsonify(result)


@bp.route('/api/codex/sessions', methods=['POST'])
def codex_sessions_create():
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    session = create_session(title=title or None)
    return _jsonify_chat_payload_or_crypto_error({
        'session': session,
        'session_storage': get_session_storage_summary(),
    }, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>')
def codex_session_detail(session_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    session = get_session(session_id)
    if not session:
        return jsonify({'error': '세션을 찾을 수 없습니다.'}), 404
    return _jsonify_chat_payload_or_crypto_error({'session': session}, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>', methods=['PATCH'])
def codex_session_rename(session_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
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
    return _jsonify_chat_payload_or_crypto_error({'session': session}, crypto_session_id)


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


@bp.route('/api/codex/sessions/<session_id>/messages/<message_id>', methods=['DELETE'])
def codex_session_message_delete(session_id, message_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify({
            'error': '세션 응답이 실행 중일 때는 대화를 삭제할 수 없습니다.',
            'active_stream_id': active_stream_id,
            'already_running': True
        }), 409

    session = delete_session_message(session_id, message_id)
    if not session:
        return jsonify({'error': '대화를 찾을 수 없습니다.'}), 404
    return _jsonify_chat_payload_or_crypto_error({
        'session': session,
        'session_storage': get_session_storage_summary(),
    }, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>/messages/<message_id>/branch', methods=['POST'])
def codex_session_message_branch(session_id, message_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if len(title) > CODEX_MAX_TITLE_CHARS:
        return jsonify({'error': '세션 이름이 너무 깁니다.'}), 400

    active_stream_id = get_active_stream_id_for_session(session_id)
    if active_stream_id:
        return jsonify({
            'error': '세션 응답이 실행 중일 때는 브랜치 세션을 만들 수 없습니다.',
            'active_stream_id': active_stream_id,
            'already_running': True
        }), 409

    session = branch_session_from_message(session_id, message_id, title=title or None)
    if not session:
        return jsonify({'error': '브랜치 기준 대화를 찾을 수 없습니다.'}), 404
    return _jsonify_chat_payload_or_crypto_error({
        'session': session,
        'session_storage': get_session_storage_summary(),
    }, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>/message', methods=['POST'])
def codex_session_message(session_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
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
    response_agent_backend = get_selected_agent_backend()
    response_model = resolve_response_model_name(model_override=model_override)
    response_reasoning_effort = resolve_response_reasoning_effort(
        model_override=model_override,
        reasoning_override=reasoning_override,
    )
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
        imagegen_prompt=prompt,
    )
    saved_at = time.time()
    duration_ms = max(0, int((saved_at - started_at) * 1000))
    metadata = {
        'duration_ms': duration_ms,
        'response_mode': response_mode,
        'response_model': response_model,
        'response_reasoning_effort': response_reasoning_effort,
        'response_agent_backend': response_agent_backend,
    }
    if isinstance(timing, dict):
        queue_wait_ms = int(timing.get('queue_wait_ms') or 0)
        cli_runtime_ms = int(timing.get('cli_runtime_ms') or 0)
        finalize_lag_ms = max(0, duration_ms - queue_wait_ms - cli_runtime_ms)
        metadata['queue_wait_ms'] = queue_wait_ms
        metadata['cli_runtime_ms'] = cli_runtime_ms
        metadata['finalize_lag_ms'] = finalize_lag_ms
        for diagnostic_key in (
            'event_stream_lagged',
            'dropped_event_count',
            'queue_full_warning_count',
            'sampling_stream_retry_count',
        ):
            if diagnostic_key in timing:
                metadata[diagnostic_key] = timing.get(diagnostic_key)
        work_details = str(timing.get('work_details') or '').strip()
        if work_details:
            metadata['work_details'] = work_details
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
    return _jsonify_chat_payload({
        'session': session,
        'user_message': user_message,
        'assistant_message': assistant_message,
        'response_mode': response_mode,
        'response_model': response_model,
        'response_reasoning_effort': response_reasoning_effort,
        'response_agent_backend': response_agent_backend,
    }, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>/message/stream', methods=['POST'])
def codex_session_message_stream(session_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    worktree_mode = _parse_worktree_mode(payload)
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)
    try:
        structured_report_preset = _parse_structured_report_preset(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if structured_report_preset and worktree_mode:
        return jsonify({'error': 'structured report는 read-only 실행만 지원합니다.'}), 400

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
    if structured_report_preset:
        prompt_with_context = build_structured_report_prompt(
            prompt_with_context,
            structured_report_preset,
        )
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
        question_only=bool(structured_report_preset),
        structured_report_preset=structured_report_preset,
        worktree_mode=worktree_mode,
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
        status_code = 400 if start_result.get('error_code') else 500
        payload = {'error': start_result.get('error') or '메시지를 저장하지 못했습니다.'}
        if start_result.get('error_code'):
            payload['error_code'] = start_result.get('error_code')
        return jsonify(payload), status_code

    return _jsonify_chat_payload({
        'stream_id': start_result.get('stream_id'),
        'started_at': start_result.get('started_at'),
        'user_message': start_result.get('user_message'),
        'assistant_message': start_result.get('assistant_message'),
        'assistant_message_id': start_result.get('assistant_message_id'),
        'response_mode': start_result.get('response_mode'),
        'response_model': start_result.get('response_model'),
        'response_reasoning_effort': start_result.get('response_reasoning_effort'),
        'response_agent_backend': start_result.get('response_agent_backend'),
        'execution_policy': start_result.get('execution_policy'),
        'structured_report_preset': start_result.get('structured_report_preset'),
        'worktree_task': start_result.get('worktree_task'),
    }, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>/message/queue', methods=['POST'])
def codex_session_message_queue(session_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    prompt = (payload.get('prompt') or '').strip()
    plan_mode = _parse_plan_mode(payload.get('plan_mode'))
    worktree_mode = _parse_worktree_mode(payload)
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)
    try:
        structured_report_preset = _parse_structured_report_preset(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if structured_report_preset and worktree_mode:
        return jsonify({'error': 'structured report는 read-only 실행만 지원합니다.'}), 400

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
        structured_report_preset=structured_report_preset,
        worktree_mode=worktree_mode,
    )
    if not result.get('ok'):
        status_code = 400 if result.get('error_code') else 500
        payload = {'error': result.get('error') or '큐 등록에 실패했습니다.'}
        if result.get('error_code'):
            payload['error_code'] = result.get('error_code')
        return jsonify(payload), status_code

    response = {
        'queued': bool(result.get('queued', not result.get('started'))),
        'started': bool(result.get('started')),
        'queue_count': int(result.get('queue_count') or 0),
    }
    session_payload = get_session(session_id) or {}
    pending_queue = session_payload.get('pending_queue')
    response['pending_queue'] = pending_queue if isinstance(pending_queue, list) else []
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
        response['response_reasoning_effort'] = result.get('response_reasoning_effort')
        response['response_agent_backend'] = result.get('response_agent_backend')
        response['execution_policy'] = result.get('execution_policy')
        response['structured_report_preset'] = result.get('structured_report_preset')
        response['worktree_task'] = result.get('worktree_task')
    return _jsonify_chat_payload(response, crypto_session_id)


@bp.route('/api/codex/sessions/<session_id>/subjobs', methods=['POST'])
def codex_session_subjob_create(session_id):
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_chat_prompt_payload(raw_payload)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    prompt = (payload.get('prompt') or '').strip()
    try:
        attachments = _parse_attachments(payload)
    except CodexAttachmentError as exc:
        return _attachment_error_response(exc)

    if not prompt:
        return jsonify({'error': '프롬프트가 비어 있습니다.'}), 400
    if len(prompt) > CODEX_MAX_PROMPT_CHARS:
        return jsonify({'error': '프롬프트가 너무 깁니다.'}), 400

    result = start_codex_subjob_for_session(
        session_id,
        prompt,
        attachments=attachments,
    )
    if not result.get('ok'):
        error = result.get('error') or 'sub job 시작에 실패했습니다.'
        status_code = 404 if '세션을 찾을 수 없습니다' in error or '부모 세션' in error else 500
        return jsonify({'error': error}), status_code

    child_session = result.get('child_session') or {}
    return _jsonify_chat_payload({
        'subjob': True,
        'parent_session_id': result.get('parent_session_id') or session_id,
        'child_session': child_session,
        'stream_id': result.get('stream_id'),
        'started_at': result.get('started_at'),
        'user_message': result.get('user_message'),
        'assistant_message': result.get('assistant_message'),
        'assistant_message_id': result.get('assistant_message_id'),
        'response_mode': result.get('response_mode'),
        'response_model': result.get('response_model'),
        'response_reasoning_effort': result.get('response_reasoning_effort'),
        'response_agent_backend': result.get('response_agent_backend'),
        'session_storage': get_session_storage_summary(),
    }, crypto_session_id)


@bp.route('/api/codex/streams/<stream_id>')
def codex_stream_output(stream_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
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
    return _jsonify_chat_payload_or_crypto_error(response, crypto_session_id)


@bp.route('/api/codex/streams')
def codex_streams_list():
    cleanup_codex_streams()
    include_done = request.args.get('include_done') == '1'
    return jsonify({'streams': list_codex_streams(include_done=include_done)})


@bp.route('/api/codex/streams/<stream_id>/stop', methods=['POST'])
def codex_stream_stop(stream_id):
    try:
        crypto_session_id = _get_chat_response_crypto_session_id()
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    result = stop_codex_stream(stream_id)
    if not result:
        return jsonify({'error': '스트림을 찾을 수 없습니다.'}), 404
    return _jsonify_chat_payload_or_crypto_error(result, crypto_session_id)


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


@bp.route('/api/codex/files/crypto-session', methods=['POST'])
def codex_files_crypto_session():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = create_file_crypto_session(payload.get('client_public_key'))
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    return jsonify(result)


@bp.route('/api/codex/files/read', methods=['POST'])
def codex_files_read():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_optional_file_payload(raw_payload)
        result = read_file(
            root_key=payload.get('root'),
            relative_path=payload.get('path', ''),
            preview_max_bytes=payload.get('preview_max_bytes'),
        )
        return _jsonify_file_payload(result, crypto_session_id)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code


@bp.route('/api/codex/files/write', methods=['POST'])
def codex_files_write():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    raw_payload = request.get_json(silent=True) or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    try:
        payload, crypto_session_id = _decrypt_optional_file_payload(raw_payload)
        if (
            CODEX_REQUIRE_ENCRYPTED_FILE_WRITES
            and not crypto_session_id
            and not _is_trusted_http_crypto_fallback_allowed()
        ):
            raise FileBrowserError(
                '파일 저장 요청은 암호화되어야 합니다.',
                error_code='encrypted_file_write_required',
                status_code=400,
            )
        if payload.get('mode') == 'patch':
            result = write_file_patch(
                root_key=payload.get('root'),
                relative_path=payload.get('path', ''),
                patch=payload.get('patch'),
                expected_modified_ns=payload.get('expected_modified_ns'),
                include_content=False,
            )
        else:
            result = write_file(
                root_key=payload.get('root'),
                relative_path=payload.get('path', ''),
                content=payload.get('content', ''),
                expected_modified_ns=payload.get('expected_modified_ns'),
                include_content=not bool(crypto_session_id),
            )
        return _jsonify_file_payload(result, crypto_session_id)
    except FileCryptoError as exc:
        return _file_crypto_error_response(exc)
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code


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


@bp.route('/api/codex/files/mail', methods=['POST'])
def codex_files_mail():
    if not CODEX_ENABLE_FILES_API:
        return _feature_disabled_response('files')
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        archive = build_mail_archive_payload(
            root_key=payload.get('root'),
            relative_paths=payload.get('paths'),
            max_bytes=CODEX_MAIL_MAX_ARCHIVE_BYTES,
            max_entries=CODEX_MAIL_MAX_ARCHIVE_ENTRIES,
        )
        mail_result = send_mail_with_archive(
            to=payload.get('to'),
            cc=payload.get('cc'),
            bcc=payload.get('bcc'),
            subject=payload.get('subject', ''),
            body=payload.get('body', ''),
            archive_payload=archive,
        )
    except FileBrowserError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code
    except MailSendError as exc:
        return jsonify({'error': str(exc), 'error_code': exc.error_code}), exc.status_code

    return jsonify({
        **mail_result,
        'archive': {
            'name': archive.get('download_name'),
            'size': archive.get('archive_size'),
            'source_size': archive.get('source_size'),
            'file_count': archive.get('file_count'),
            'directory_count': archive.get('directory_count'),
            'entry_count': archive.get('entry_count'),
        },
    })


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
            tail_chars=request.args.get('tail_chars'),
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
            tail_chars=request.args.get('tail_chars'),
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


def _worktree_error_response(error):
    status_code = getattr(error, 'status_code', 400)
    return jsonify({
        'error': str(error),
        'error_code': getattr(error, 'error_code', 'worktree_error'),
    }), status_code


@bp.route('/api/codex/worktrees', methods=['GET', 'POST'])
def codex_worktrees():
    if request.method == 'GET':
        return jsonify({'worktrees': list_git_worktree_tasks()})
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    prompt = str(payload.get('prompt') or payload.get('label') or '').strip()
    session_id = str(payload.get('session_id') or '').strip()
    try:
        task = create_git_worktree_task(prompt, session_id=session_id)
    except CodexWorktreeError as exc:
        return _worktree_error_response(exc)
    return jsonify({'ok': True, 'worktree': task})


@bp.route('/api/codex/worktrees/<task_id>', methods=['GET', 'DELETE'])
def codex_worktree_detail(task_id):
    if request.method == 'GET':
        try:
            return jsonify({'worktree': get_git_worktree_task(task_id)})
        except CodexWorktreeError as exc:
            return _worktree_error_response(exc)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    force = _parse_plan_mode(payload.get('force')) or request.args.get('force') == '1'
    try:
        task = cleanup_git_worktree_task(task_id, force=force)
    except CodexWorktreeError as exc:
        return _worktree_error_response(exc)
    return jsonify({'ok': True, 'worktree': task})


@bp.route('/api/codex/worktrees/<task_id>/handoff', methods=['POST'])
def codex_worktree_handoff(task_id):
    try:
        return jsonify(handoff_git_worktree_task(task_id))
    except CodexWorktreeError as exc:
        return _worktree_error_response(exc)


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
