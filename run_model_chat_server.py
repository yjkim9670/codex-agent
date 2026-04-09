#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the Model Chat server."""

import argparse
import importlib
import json
import logging
import os
import re
import sys
from pathlib import Path

if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

script_dir = Path(__file__).resolve().parent
repo_root = script_dir
DEFAULT_CONFIG_FILENAME = 'model_agent_config.json'


def _is_truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


QUIET_MODE = _is_truthy(os.environ.get('MODEL_CHAT_QUIET'))


def _print_info(message):
    if not QUIET_MODE:
        print(message)


def _print_error(message):
    print(message, file=sys.stderr)

def ensure_workspace_directory(script_path):
    if os.environ.get('MODEL_WORKSPACE_DIR'):
        return
    default_workspace = (script_path / 'workspace').resolve()
    os.environ['MODEL_WORKSPACE_DIR'] = str(default_workspace)
    _print_info(f"[INFO] Default workspace enabled: {default_workspace}")


def _coerce_port(value, fallback):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return fallback
    if port < 1 or port > 65535:
        return fallback
    return port


def _coerce_bool(value, fallback):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off'}:
            return False
    return fallback


def _coerce_list(value):
    if isinstance(value, list):
        normalized = []
        for item in value:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


_ENV_REFERENCE_PATTERN = re.compile(r'^\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}$')


def _resolve_env_reference(value):
    if not isinstance(value, str):
        return value
    token = value.strip()
    if not token:
        return value

    match = _ENV_REFERENCE_PATTERN.match(token)
    if match:
        return os.environ.get(match.group(1), '')

    if token.lower().startswith('env:'):
        env_name = token[4:].strip()
        if env_name:
            return os.environ.get(env_name, '')
    return value


def _resolve_config_env_references(value):
    if isinstance(value, dict):
        return {key: _resolve_config_env_references(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_config_env_references(item) for item in value]
    return _resolve_env_reference(value)


def _resolve_config_path(script_path, default_config_filename=DEFAULT_CONFIG_FILENAME):
    configured = os.environ.get('MODEL_AGENT_CONFIG_PATH', '').strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = (script_path / candidate).resolve()
        return candidate
    return script_path / default_config_filename


def load_runtime_config(script_path, default_config_filename=DEFAULT_CONFIG_FILENAME):
    config_path = _resolve_config_path(script_path, default_config_filename=default_config_filename)
    if not config_path.exists():
        _print_info(f"[INFO] Config file not found. Using defaults: {config_path}")
        return {}, config_path

    try:
        raw = config_path.read_text(encoding='utf-8')
        config = json.loads(raw)
    except Exception as exc:
        _print_error(f"[ERROR] Failed to load config JSON: {config_path} ({exc})")
        sys.exit(1)

    if not isinstance(config, dict):
        _print_error(f"[ERROR] Config JSON must be an object: {config_path}")
        sys.exit(1)

    config = _resolve_config_env_references(config)
    _print_info(f"[INFO] Loaded config: {config_path}")
    return config, config_path


def _set_env_default(key, value):
    if value is None:
        return
    if os.environ.get(key):
        return
    os.environ[key] = str(value)


def _set_env_from_config(key, value):
    if value is None:
        return
    os.environ[key] = str(value)


def _resolve_workspace_dir(raw_value, base_dir):
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    return str(path)


def apply_runtime_environment(config, config_path):
    agent_config = config.get('agent')
    legacy_gemini_config = config.get('gemini')
    if isinstance(agent_config, dict):
        runtime_config = agent_config
    elif isinstance(legacy_gemini_config, dict):
        runtime_config = legacy_gemini_config
    else:
        return

    workspace_dir = _resolve_workspace_dir(runtime_config.get('workspace_dir'), config_path.parent)
    if 'workspace_dir' in runtime_config:
        _set_env_from_config('MODEL_WORKSPACE_DIR', workspace_dir)
    else:
        _set_env_default('MODEL_WORKSPACE_DIR', workspace_dir)
    if runtime_config.get('storage_namespace') is not None:
        _set_env_from_config('MODEL_AGENT_STORAGE_NAMESPACE', str(runtime_config.get('storage_namespace')).strip())
    _set_env_default('MODEL_CHAT_SECRET_KEY', runtime_config.get('secret_key'))
    _set_env_default('MODEL_DEFAULT_PROVIDER', runtime_config.get('default_provider'))

    provider_options = _coerce_list(runtime_config.get('provider_options'))
    if provider_options:
        _set_env_default('MODEL_PROVIDER_OPTIONS', ','.join(provider_options))
    workspace_blocked_paths = _coerce_list(runtime_config.get('workspace_blocked_paths'))
    if 'workspace_blocked_paths' in runtime_config:
        _set_env_from_config('MODEL_WORKSPACE_BLOCKED_PATHS', ','.join(workspace_blocked_paths))
    elif workspace_blocked_paths:
        _set_env_default('MODEL_WORKSPACE_BLOCKED_PATHS', ','.join(workspace_blocked_paths))

    providers_config = runtime_config.get('providers')
    if not isinstance(providers_config, dict):
        providers_config = {}

    provider_env_mappings = {
        'gemini': {
            'api_key': 'MODEL_GEMINI_API_KEY',
            'api_base_url': 'MODEL_GEMINI_API_BASE_URL',
            'default_model': 'MODEL_GEMINI_DEFAULT_MODEL',
            'model_options': 'MODEL_GEMINI_MODEL_OPTIONS',
        },
        'dtgpt': {
            'api_key': 'MODEL_DTGPT_API_KEY',
            'api_key_env': 'MODEL_DTGPT_API_KEY_ENV',
            'api_key_header': 'MODEL_DTGPT_API_KEY_HEADER',
            'api_key_prefix': 'MODEL_DTGPT_API_KEY_PREFIX',
            'api_base_url': 'MODEL_DTGPT_API_BASE_URL',
            'api_base_urls': 'MODEL_DTGPT_API_BASE_URLS',
            'default_model': 'MODEL_DTGPT_DEFAULT_MODEL',
            'model_options': 'MODEL_DTGPT_MODEL_OPTIONS',
        },
    }

    normalized_providers = {}
    for provider_name in provider_env_mappings:
        provider_config = providers_config.get(provider_name)
        if not isinstance(provider_config, dict):
            provider_config = {}
        normalized_providers[provider_name] = provider_config

    # Backward compatibility for the older single-provider schema.
    if runtime_config.get('api_key') is not None:
        normalized_providers['gemini'].setdefault('api_key', runtime_config.get('api_key'))
    if runtime_config.get('api_base_url') is not None:
        normalized_providers['gemini'].setdefault('api_base_url', runtime_config.get('api_base_url'))
    if runtime_config.get('default_model') is not None:
        normalized_providers['gemini'].setdefault('default_model', runtime_config.get('default_model'))
    legacy_model_options = _coerce_list(runtime_config.get('model_options'))
    if legacy_model_options and 'model_options' not in normalized_providers['gemini']:
        normalized_providers['gemini']['model_options'] = legacy_model_options

    for provider_name, env_mapping in provider_env_mappings.items():
        provider_config = normalized_providers.get(provider_name, {})
        if env_mapping.get('api_key'):
            _set_env_default(env_mapping['api_key'], provider_config.get('api_key'))
        if env_mapping.get('api_key_env'):
            _set_env_default(env_mapping['api_key_env'], provider_config.get('api_key_env'))
        if env_mapping.get('api_key_header'):
            _set_env_default(env_mapping['api_key_header'], provider_config.get('api_key_header'))
        if env_mapping.get('api_key_prefix'):
            _set_env_default(env_mapping['api_key_prefix'], provider_config.get('api_key_prefix'))
        if env_mapping.get('api_base_url'):
            _set_env_default(env_mapping['api_base_url'], provider_config.get('api_base_url'))
        if env_mapping.get('api_base_urls'):
            provider_base_urls = _coerce_list(provider_config.get('api_base_urls'))
            if provider_base_urls:
                _set_env_default(env_mapping['api_base_urls'], ','.join(provider_base_urls))
        if env_mapping.get('default_model'):
            _set_env_default(env_mapping['default_model'], provider_config.get('default_model'))

        provider_model_options = _coerce_list(provider_config.get('model_options'))
        if provider_model_options and env_mapping.get('model_options'):
            _set_env_default(env_mapping['model_options'], ','.join(provider_model_options))

    numeric_mappings = {
        'max_prompt_chars': 'MODEL_MAX_PROMPT_CHARS',
        'context_max_chars': 'MODEL_CONTEXT_MAX_CHARS',
        'exec_timeout_seconds': 'MODEL_EXEC_TIMEOUT_SECONDS',
        'api_timeout_seconds': 'MODEL_API_TIMEOUT_SECONDS',
        'stream_ttl_seconds': 'MODEL_STREAM_TTL_SECONDS',
        'max_title_chars': 'MODEL_MAX_TITLE_CHARS',
        'max_provider_chars': 'MODEL_MAX_PROVIDER_CHARS',
        'max_model_chars': 'MODEL_MAX_MODEL_CHARS',
    }
    for key, env_key in numeric_mappings.items():
        value = runtime_config.get(key)
        if value is None:
            continue
        _set_env_default(env_key, value)


def get_server_defaults(config):
    defaults = {
        'host': '0.0.0.0',
        'port': 3100,
        'debug': True,
        'use_reloader': True,
        'threaded': True
    }
    server_config = config.get('server')
    if not isinstance(server_config, dict):
        return defaults

    host = server_config.get('host')
    if isinstance(host, str) and host.strip():
        defaults['host'] = host.strip()
    defaults['port'] = _coerce_port(server_config.get('port'), defaults['port'])
    defaults['debug'] = _coerce_bool(server_config.get('debug'), defaults['debug'])
    defaults['use_reloader'] = _coerce_bool(server_config.get('use_reloader'), defaults['use_reloader'])
    defaults['threaded'] = _coerce_bool(server_config.get('threaded'), defaults['threaded'])
    return defaults

os.chdir(script_dir)

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

def parse_args(server_defaults, description='Run Model Chat server.'):
    parser = argparse.ArgumentParser(description=description)
    default_port = server_defaults['port']
    default_host = server_defaults['host']
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=default_port,
        help=f'Port to bind the server (default: {default_port})',
    )
    parser.add_argument(
        '--host',
        default=default_host,
        help=f'Host interface to bind (default: {default_host})',
    )
    args = parser.parse_args()
    if args.port < 1 or args.port > 65535:
        parser.error('--port must be between 1 and 65535')
    return args


def _import_app_factory(import_target):
    target = str(import_target or '').strip()
    if not target:
        raise ImportError('App factory import target is empty.')

    module_name, separator, attribute_name = target.partition(':')
    if not separator or not module_name or not attribute_name:
        raise ImportError(
            f'Invalid app factory target: {target}. Expected module.path:callable_name'
        )

    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name, None)
    if factory is None or not callable(factory):
        raise ImportError(f'App factory is not callable: {target}')
    return factory


def main(
        default_config_filename=DEFAULT_CONFIG_FILENAME,
        cli_description='Run Model Chat server.',
        startup_label='Model Chat Server',
        access_label='Model chat API',
        app_factory_import='model_agent.model_app:create_model_app'):
    runtime_config, config_path = load_runtime_config(
        script_dir,
        default_config_filename=default_config_filename,
    )
    apply_runtime_environment(runtime_config, config_path)
    ensure_workspace_directory(script_dir)
    server_defaults = get_server_defaults(runtime_config)
    args = parse_args(server_defaults, description=cli_description)
    if QUIET_MODE:
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        try:
            import flask.cli
            flask.cli.show_server_banner = lambda *unused_args, **unused_kwargs: None
        except Exception:
            pass
    try:
        create_app = _import_app_factory(app_factory_import)
    except ImportError as exc:
        _print_error(f"[ERROR] Failed to import model chat modules: {exc}")
        _print_error(f"[ERROR] Current directory: {os.getcwd()}")
        _print_error(f"[ERROR] Script directory: {script_dir}")
        _print_error(f"[ERROR] Python path: {sys.path[:3]}")
        sys.exit(1)

    app = create_app()
    use_reloader = server_defaults['use_reloader']
    _print_info(f"[INFO] Starting {startup_label}...")
    _print_info(f"[INFO] Access the {access_label} at: http://localhost:{args.port}")
    app.run(
        debug=server_defaults['debug'],
        host=args.host,
        port=args.port,
        use_reloader=use_reloader,
        threaded=server_defaults['threaded'],
    )


if __name__ == '__main__':
    main()
