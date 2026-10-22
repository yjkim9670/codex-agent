"""Workbench model smoke tests. Standard library only except optional direct workers."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
API = '/api/codex'
KEYS = ('agent_backend', 'model', 'reasoning_effort')
_direct_key_cursor = 0


def environment_api_keys():
    """Explicit JSON avoids ambiguous delimiters and never includes secrets in errors."""
    raw = os.environ.get('WORKBENCH_TEST_API_KEYS', '').strip()
    if raw:
        try:
            keys = json.loads(raw)
        except ValueError:
            raise ValueError('WORKBENCH_TEST_API_KEYS must be a JSON array of non-empty strings') from None
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k.strip() for k in keys):
            raise ValueError('WORKBENCH_TEST_API_KEYS must be a JSON array of non-empty strings')
        return [k.strip() for k in keys]
    key = os.environ.get('DTGPT_API_KEY', '').strip()
    return [key] if key else []


def print_key_guidance():
    print('HTTP tests use the server Key Pool: one reserved key per execution, including queued jobs. '
          'Client API key variables do not change the running server.')
    if not environment_api_keys():
        print('API key environment variables are absent. HTTP tests can use keys registered in Workbench. '
              'Direct tests use the local production credential resolver unless an explicit test pool is set.\n'
              'PowerShell (current shell):\n'
              '  $env:WORKBENCH_TEST_API_KEYS = \'["key-1","key-2"]\'\n'
              '  $env:DTGPT_API_KEY = "single-key"  # single-key fallback\n'
              'Linux bash / macOS zsh (current shell):\n'
              '  export WORKBENCH_TEST_API_KEYS=\'["key-1","key-2"]\'\n'
              '  export DTGPT_API_KEY="single-key"  # single-key fallback\n'
              'Direct company execution also requires CODEX_COMPANY_MODE=1 and the same gateway/CLI/model '
              'environment as the server company launcher. OpenCode uses its own provider credentials.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url, timeout=30):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())
        self.trace = None

    def request(self, method, path, payload=None, raw=None, content_type=None, timeout=None):
        started = time.monotonic()
        if self.trace:
            self.trace('http_start', method=method, path=path.split('?')[0])
        try:
            result = self._request(method, path, payload, raw, content_type, timeout)
        except Exception as exc:
            if self.trace:
                self.trace('http_error', method=method, path=path.split('?')[0],
                           seconds=round(time.monotonic() - started, 3), error_type=type(exc).__name__,
                           detail=diagnostic_text(str(exc)))
            raise
        if self.trace:
            self.trace('http_complete', method=method, path=path.split('?')[0],
                       seconds=round(time.monotonic() - started, 3))
            if path.startswith('/streams/'):
                self.trace('stream_snapshot', snapshot=stream_snapshot(result))
                self.trace('stream_diagnostics', diagnostics=response_diagnostics(result))
        return result

    def _request(self, method, path, payload=None, raw=None, content_type=None, timeout=None):
        headers = {'Accept': 'application/json'}
        # Credentials stay in the environment and never enter reports/argv.
        if os.environ.get('WORKBENCH_TEST_COOKIE'):
            headers['Cookie'] = os.environ['WORKBENCH_TEST_COOKIE']
        if os.environ.get('WORKBENCH_TEST_AUTHORIZATION'):
            headers['Authorization'] = os.environ['WORKBENCH_TEST_AUTHORIZATION']
        if payload is not None:
            raw = json.dumps(payload).encode('utf-8')
            content_type = 'application/json'
        if content_type:
            headers['Content-Type'] = content_type
        try:
            with self.opener.open(Request(self.url + API + path, data=raw,
                                          headers=headers, method=method), timeout=timeout or self.timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            body = exc.read(65536).decode('utf-8', errors='replace')
            if self.trace:
                self.trace('http_status', status=exc.code, body=diagnostic_text(body),
                           body_read_limit_bytes=65536)
            raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {exc.code}') from None
        if not isinstance(result, dict):
            raise RuntimeError('Expected JSON object (check authentication/base URL)')
        if result.get('encrypted') or result.get('ciphertext'):
            raise RuntimeError('Encrypted API response unsupported by this test client')
        return result


def matrix(snapshot, backends, models, efforts, exhaustive):
    rows = []
    catalogs = snapshot.get('model_catalogs_by_agent_backend', {})
    for backend in dict.fromkeys('dtgpt' if b == 'codex' else b for b in backends):
        catalog = catalogs.get(backend, [])
        selected = [e for e in catalog if not models or e['slug'] in models]
        if not exhaustive and not models:
            current = snapshot['settings'].get('model')
            selected = [next((e for e in selected if e['slug'] == current), selected[0])] if selected else []
        for missing in models:
            if not any(e['slug'] == missing for e in catalog):
                rows.append(dict(backend=backend, model=missing, reasoning='', status='UNSUPPORTED'))
        if not selected and not models:
            rows.append(dict(backend=backend, model='', reasoning='', status='UNSUPPORTED'))
        for entry in selected:
            supported = entry.get('reasoning_options') or []
            chosen = efforts or (supported if exhaustive else [entry.get('default_reasoning_effort') or ''])
            if backend == 'opencode':
                chosen = efforts or ['']
            for effort in chosen or ['']:
                valid = (not effort) or (backend != 'opencode' and effort in supported)
                rows.append(dict(backend=backend, model=entry['slug'], reasoning=effort,
                                 status='PLANNED' if valid else 'UNSUPPORTED'))
    return rows


def settings_for(row):
    return dict(agent_backend=row['backend'], model=row['model'], reasoning_effort=row['reasoning'])


def check_metadata(data, row):
    # Persisted Workbench messages flatten metadata onto the message. Accept
    # nested metadata too, with explicit top-level fields taking precedence.
    nested = data.get('metadata')
    data = dict(nested if isinstance(nested, dict) else {}, **data)
    expected = dict(response_agent_backend=row['backend'], response_model=row['model'],
                    response_reasoning_effort=row['reasoning'])
    for key, value in expected.items():
        actual = data.get(key)
        if key == 'response_agent_backend':
            actual = actual or data.get('agent_backend')
        if (actual or '') != value:
            raise AssertionError(f'{key} mismatch: expected {value!r}, received {actual!r}')


def stream_snapshot(data):
    """Allowlist state; never export provider output, errors, or environment."""
    keys = ('done', 'saved', 'exit_code', 'finalize_reason', 'process_running', 'process_pid',
            'output_length', 'error_length', 'event_length', 'runtime_ms', 'idle_ms',
            'queue_wait_ms', 'cli_runtime_ms', 'started_at', 'cli_started_at',
            'process_exited_at', 'completed_at', 'saved_at', 'diagnostic_phase',
            'worker_error_type', 'assistant_message_id', 'persistence_failed', 'persistence_complete')
    result = {key: data[key] for key in keys if key in data}
    result['diagnostic_timeline'] = [
        {key: entry[key] for key in ('phase', 'at') if key in entry}
        for entry in (data.get('diagnostic_timeline') or [])[-64:] if isinstance(entry, dict)]
    return result


def diagnostic_text(value, limit=16384):
    """Redact known secrets before retaining the tail of potentially large output."""
    value = str(value)
    for name, secret in os.environ.items():
        if secret and (name in ('WORKBENCH_TEST_COOKIE', 'WORKBENCH_TEST_AUTHORIZATION')
                       or any(part in name.upper() for part in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))):
            value = value.replace(secret, '[REDACTED]')
    # A JSON pool's individual members can appear independently in CLI errors.
    try:
        for secret in environment_api_keys():
            value = value.replace(secret, '[REDACTED]')
    except ValueError:
        pass
    value = re.sub(r'(?i)(\bBearer\s+)[^\s\"\',;]+', r'\1[REDACTED]', value)
    value = re.sub(r'''(?ix)(["']?(?:authorization|cookie|set-cookie|api[_-]?key|access[_-]?token|password|secret)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\r\n,}]+)''',
                   r'\1[REDACTED]', value)
    if len(value) > limit:
        return f'[TRUNCATED: {len(value) - limit} characters omitted]\n' + value[-limit:]
    return value


def response_diagnostics(data):
    """Only export diagnostic fields, never full sessions/settings or user messages."""
    fields = ('output', 'error', 'content', 'events', 'exit_code', 'finalize_reason',
              'worker_error_type', 'assistant_message_id', 'id', 'role',
              'response_agent_backend', 'agent_backend', 'response_model', 'response_reasoning_effort')
    result = {}
    for key in fields:
        if key in data:
            value = data[key]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            result[key] = diagnostic_text(value) if isinstance(value, str) else value
    nested = data.get('metadata')
    if isinstance(nested, dict):
        result['metadata'] = response_diagnostics(nested)
    return result


def wait_stream(client, stream_id, deadline):
    last = {}
    while time.monotonic() < deadline:
        data = client.request('GET', '/streams/' + quote(stream_id, safe=''),
                              timeout=max(0.001, min(client.timeout, deadline - time.monotonic())))
        last = stream_snapshot(data)
        if data.get('done') and data.get('saved'):
            return data
        time.sleep(min(0.3, max(0, deadline - time.monotonic())))
    raise TimeoutError('Stream completion/storage timed out: ' + json.dumps(last, ensure_ascii=False))


def stop_owned(client, stream_id):
    client.request('POST', f'/streams/{stream_id}/stop', {})
    wait_stream(client, stream_id, time.monotonic() + 30)


def upload_text(client, token):
    boundary = 'wb' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
            'filename="문맥 확인.txt"\r\nContent-Type: text/plain\r\n\r\n'
            f'{token}\r\n--{boundary}--\r\n').encode('utf-8')
    return client.request('POST', '/attachments', raw=body,
                          content_type='multipart/form-data; boundary=' + boundary)['attachments']


class Progress:
    """Keep elapsed time visible even during blocking HTTP/CLI calls."""

    def __init__(self, row, scenario, index, total, timeout, interval=1):
        self.label = (f'[{index}/{total}] backend={row["backend"]} model={row["model"]} '
                      f'reasoning={row["reasoning"] or "(default)"} scenario={scenario}')
        self.timeout = timeout
        self.interval = interval
        self.started = time.monotonic()
        self.state = {'phase': 'preparing'}
        self.output = sys.stdout
        self.interactive = self.output.isatty()
        self.last_state = None
        self.line_width = 0
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def _emit(self):
        # Only identifiers and execution state; never prompts or response bodies.
        if not self.interactive and self.state == self.last_state:
            return
        state = ' '.join(f'{key}={value}' for key, value in self.state.items())
        line = (f'{self.label} {state} elapsed={time.monotonic() - self.started:.1f}s '
                f'timeout={self.timeout:g}s')
        if self.interactive:
            line = (f'elapsed={time.monotonic() - self.started:.1f}s {state} '
                    f'{self.label} timeout={self.timeout:g}s')
        line = ''.join(c if c.isprintable() else ' ' for c in safe_detail(line))
        if self.interactive:
            # Leave one column free so long labels cannot wrap into new lines.
            columns = max(0, shutil.get_terminal_size().columns - 1)
            visible = []
            width = 0
            for char in line:
                size = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1)
                if width + size > columns:
                    break
                visible.append(char)
                width += size
            padding = max(0, min(self.line_width, columns) - width)
            print('\r' + ''.join(visible) + ' ' * padding, end='', file=self.output, flush=True)
            self.line_width = width
        else:
            print(line, file=self.output, flush=True)
        self.last_state = dict(self.state)

    def update(self, phase, **identifiers):
        with self.lock:
            self.state.update(phase=phase, **identifiers)
            self._emit()

    def _watch(self):
        while not self.stopped.wait(self.interval):
            with self.lock:
                self._emit()

    def __enter__(self):
        self.update('preparing')
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stopped.set()
        self.thread.join()
        if self.interactive:
            print(file=self.output, flush=True)


def run_case(client, row, args, scenario='echo'):
    result = dict(row, scenario=scenario, evidence='workbench_metadata_and_persisted_response')
    started = time.monotonic()
    session_id = stream_id = None
    settled = True
    token = 'WBTEST_' + uuid.uuid4().hex
    payload = {'prompt': f'Reply with exactly {token}. Do not modify any files.'}
    queued_token = None
    progress = getattr(args, 'progress', None)
    trace_path = getattr(args, 'trace_path', None)
    previous_trace = client.trace
    last_diagnostics = None

    def trace(event, **fields):
        nonlocal last_diagnostics
        if event == 'stream_diagnostics':
            result['last_stream_diagnostics'] = fields['diagnostics']
            if fields['diagnostics'] == last_diagnostics:
                return
            last_diagnostics = fields['diagnostics']
        entry = dict(event=event, at=int(time.time() * 1000),
                     elapsed=round(time.monotonic() - started, 3), **fields)
        if event == 'stream_snapshot':
            result['last_stream_snapshot'] = fields['snapshot']
            if progress is not None:
                snapshot = fields['snapshot']
                progress.update(result.get('last_phase', 'waiting-response'),
                                server_phase=snapshot.get('diagnostic_phase') or 'unknown',
                                done=snapshot.get('done'), saved=snapshot.get('saved'),
                                output_chars=snapshot.get('output_length', 0),
                                error_chars=snapshot.get('error_length', 0))
        if trace_path:
            with Path(trace_path).open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')

    client.trace = trace
    if trace_path:
        result['trace_file'] = Path(trace_path).name
    trace('case_started', backend=row['backend'], model=row['model'], reasoning=row['reasoning'],
          scenario=scenario, mode=args.mode, timeout=args.timeout)

    def update(phase, **identifiers):
        result['last_phase'] = phase
        trace('phase', phase=phase, **identifiers)
        if progress is not None:
            progress.update(phase, **identifiers)

    def verify_metadata(data, source):
        result['metadata_source'] = source
        nested = data.get('metadata')
        fields = dict(nested if isinstance(nested, dict) else {}, **data)
        actual = {key: fields.get(key) for key in (
            'response_agent_backend', 'agent_backend', 'response_model', 'response_reasoning_effort')}
        trace('metadata_check', source=source, expected=settings_for(row), actual=actual)
        check_metadata(data, row)

    try:
        applied = client.request('PATCH', '/settings', settings_for(row))['settings']
        for key, value in settings_for(row).items():
            if (applied.get(key) or '') != value:
                raise AssertionError(f'Applied setting differs: {key}')
        if scenario == 'attachment':
            payload['attachments'] = upload_text(client, token)
            payload['prompt'] = 'Read the attached text file and reply with its exact contents. Do not modify files.'
        if scenario == 'workspace':
            # Expected value is deliberately absent from the prompt.
            token = args.expected_workspace
            payload['prompt'] = 'Inspect the actual current working directory. Reply with its absolute path only. Do not modify files.'
        if scenario == 'worktree':
            payload['worktree_mode'] = True
            payload['prompt'] = 'Inspect the actual current working directory. Reply with its absolute path only. Do not modify files.'
        session_id = client.request('POST', '/sessions', {'title': 'Backend test ' + uuid.uuid4().hex[:10]})['session']['id']
        result['session_id'] = session_id
        use_stream = args.mode == 'stream' or scenario in ('queue', 'worktree')
        update('submitting', session=session_id)
        try:
            data = client.request('POST', f'/sessions/{session_id}/message' + ('/stream' if use_stream else ''),
                                  payload, timeout=args.timeout if not use_stream else None)
        except (TimeoutError, OSError):
            result['cleanup_error'] = 'Message start/completion uncertain; inspect test session before continuing'
            raise
        trace('submission_diagnostics', diagnostics=response_diagnostics(data))
        if use_stream:
            stream_id = data['stream_id']
            result['stream_id'] = stream_id
            settled = False
        update('submitted' if use_stream else 'verifying', **({'stream': stream_id} if stream_id else {}))
        verify_metadata(data, 'stream_start' if use_stream else 'sync_response')
        if scenario == 'worktree':
            token = (data.get('worktree_task') or {}).get('path')
            if not token:
                raise AssertionError('Missing worktree path')
            result['worktree_task'] = data['worktree_task']
        if scenario == 'queue':
            queued_token = 'WBQUEUE_' + uuid.uuid4().hex
            update('queue-submitting')
            queue = client.request('POST', f'/sessions/{session_id}/message/queue',
                                   {'prompt': f'Reply with exactly {queued_token}. Do not modify files.'})
            if not queue.get('queued'):
                raise AssertionError('First response completed before enqueue; queue regression inconclusive')
            update('queued')
            # Change settings while queued: the queued job must retain its snapshot.
            alternate = next((e for e in args.queue_candidates if settings_for(e) != settings_for(row)), None)
            if alternate is None:
                raise AssertionError('Queue regression needs a second supported model/reasoning combination')
            client.request('PATCH', '/settings', settings_for(alternate))
        if use_stream:
            update('waiting-response')
            data = wait_stream(client, stream_id, started + args.timeout)
            settled = True
            verify_metadata(data, 'stream_complete')
            if data.get('exit_code') != 0:
                raise AssertionError('Stream exited unsuccessfully')
        update('verifying')
        session = client.request('GET', f'/sessions/{session_id}')['session']
        message_id = data.get('assistant_message_id') or (data.get('assistant_message') or {}).get('id')
        message = next((m for m in session['messages'] if m.get('id') == message_id), None)
        if message:
            trace('persisted_message', diagnostics=response_diagnostics(message))
        if not message or message.get('role') != 'assistant' or token not in (message.get('content') or ''):
            raise AssertionError('Final persisted assistant response missing expected token/path')
        if message.get('error') or (message.get('metadata') or {}).get('error'):
            raise AssertionError('Persisted assistant response contains an error')
        verify_metadata(message, 'persisted_message')
        if queued_token:
            update('waiting-queue')
            while time.monotonic() < started + args.timeout:
                for child in client.request('GET', '/streams?include_done=1')['streams']:
                    if child.get('session_id') == session_id and child['id'] != stream_id:
                        update('waiting-queue', queued_stream=child['id'])
                        terminal = wait_stream(client, child['id'], started + args.timeout)
                        verify_metadata(terminal, 'queued_stream_complete')
                        if terminal.get('exit_code') != 0:
                            raise AssertionError('Queued stream exited unsuccessfully')
                session = client.request('GET', f'/sessions/{session_id}')['session']
                queued = [m for m in session['messages'] if m.get('role') == 'assistant'
                          and queued_token in (m.get('content') or '')]
                if queued:
                    verify_metadata(queued[-1], 'queued_persisted_message')
                    break
                time.sleep(0.3)
            else:
                raise TimeoutError('Queued response not persisted')
        result['status'] = 'PASS'
    except Exception as exc:
        result['failure_phase'] = result.get('last_phase', 'preparing')
        if result.get('last_stream_snapshot') is not None:
            result['failure_stream_snapshot'] = dict(result['last_stream_snapshot'])
        trace('case_error', error_type=type(exc).__name__, phase=result['failure_phase'])
        result.update(status='TIMEOUT' if isinstance(exc, TimeoutError) else 'FAIL',
                      detail=safe_detail(str(exc)))
        result['exception_traceback'] = diagnostic_text(traceback.format_exc())
        trace('exception', detail=diagnostic_text(str(exc)), traceback=result['exception_traceback'])
        # Preserve evidence before stop/cleanup can change the stream's error/output.
        if result.get('last_stream_diagnostics') is not None:
            result['failure_stream_diagnostics'] = dict(result['last_stream_diagnostics'])
        if stream_id:
            try:
                failure = client.request('GET', '/streams/' + quote(stream_id, safe=''))
                result['failure_stream_diagnostics'] = response_diagnostics(failure)
            except Exception as diagnostic_exc:
                trace('diagnostic_collection_error', source='stream', detail=diagnostic_text(str(diagnostic_exc)))
        if session_id:
            try:
                failed_session = client.request('GET', f'/sessions/{session_id}')['session']
                result['failure_assistant_messages'] = [response_diagnostics(m)
                    for m in failed_session.get('messages', []) if m.get('role') == 'assistant'][-8:]
                trace('failure_assistant_messages', messages=result['failure_assistant_messages'])
            except Exception as diagnostic_exc:
                trace('diagnostic_collection_error', source='session', detail=diagnostic_text(str(diagnostic_exc)))
    finally:
        if stream_id and not settled:
            update('stopping-stream')
            try:
                stop_owned(client, stream_id)
            except Exception:
                result['cleanup_error'] = 'Stream stop/storage could not be confirmed; aborting subsequent tests'
        # Also catch queued child streams owned by this test session.
        if session_id and scenario == 'queue':
            update('cleaning-queue')
            try:
                deadline = time.monotonic() + 30
                while True:
                    for stream in client.request('GET', '/streams')['streams']:
                        if stream.get('session_id') == session_id and not stream.get('done'):
                            stop_owned(client, stream['id'])
                    pending = client.request('GET', f'/sessions/{session_id}')['session'].get('pending_queue')
                    if not pending:
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError('Pending queue remains')
                    time.sleep(0.3)
            except Exception:
                result['cleanup_error'] = 'Queued stream cleanup could not be confirmed'
        result['seconds'] = round(time.monotonic() - started, 3)
        trace('case_finished', status=result.get('status'), seconds=result['seconds'])
        client.trace = previous_trace
    return result


def safe_detail(value):
    return diagnostic_text(value, limit=700)


def direct_worker(row):
    sys.path.insert(0, str(ROOT))
    from codex_agent.services import codex_chat as service
    execution = {
        'requested_backend': row['backend'],
        'actual_backend': None,
        'enabled_backends': sorted(item['id'] for item in service.get_agent_backend_options()),
        'executable': None,
        'resolved_executable': None,
        'transport': 'server_api' if row['backend'] == 'opencode' else 'cli',
    }

    def record_execution():
        print(json.dumps({'event': 'execution_preflight', 'execution': execution}), flush=True)

    def reject_backend(detail):
        print(json.dumps({'status': 'FAIL', 'failure_phase': 'backend_validation',
                          'detail': detail, 'execution': execution}), flush=True)

    if row['backend'] not in execution['enabled_backends']:
        record_execution()
        reject_backend('Requested backend is not enabled in the local direct worker')
        return
    token = 'WBDIRECT_' + uuid.uuid4().hex
    prompt = f'Reply with exactly {token}. Do not modify files or run tools.'
    if row['backend'] == 'opencode':
        execution['actual_backend'] = 'opencode'
        record_execution()
        forwarded_model = service._opencode_model_payload(row['model'])
        if not forwarded_model:
            raise ValueError('OpenCode model must include provider/model')
        forwarded_reasoning = None
        prompt, context = service._prepare_agent_execution(prompt, {'agent_backend': 'opencode'})
        output, error, _, _ = service._execute_opencode_prompt(prompt, context, row['model'])
        ok = not error and token in (output or '')
        evidence = 'production_opencode_payload_builder'
        diagnostics = {'output': output, 'error': error}
    else:
        # Match _run_codex_stream: build credentials/runtime, then apply the
        # selected backend's gateway and model environment before spawning.
        selected = os.environ.get('WORKBENCH_TEST_SELECTED_API_KEY', '').strip()
        internal_key = {'secret': selected} if selected else None
        if selected:
            from codex_agent.services.company_credentials import company_key_pool_supported
            if not company_key_pool_supported():
                raise ValueError('Explicit direct key rotation requires a Windows/Linux company environment '
                                 '(CODEX_COMPANY_MODE=1); HTTP tests use the server pool on any client OS')
            if row['backend'] == 'claude' and os.environ.get('CODEX_CLAUDE_ENV_MODE', '').lower() == 'native':
                raise ValueError('Explicit company test keys cannot be used with CODEX_CLAUDE_ENV_MODE=native')
        actual_backend, cmd = service._build_agent_command(prompt, agent_backend=row['backend'],
            model_override=row['model'], reasoning_override=row['reasoning'],
            inherit_model_settings=False, question_only=True)
        execution.update(actual_backend=actual_backend,
                         executable=diagnostic_text(cmd[0]),
                         resolved_executable=diagnostic_text(shutil.which(cmd[0])) if shutil.which(cmd[0]) else None)
        record_execution()
        if actual_backend != row['backend']:
            reject_backend('Production command builder selected a different backend')
            return
        forwarded_model = cmd[cmd.index('--model') + 1] if '--model' in cmd else None
        if row['backend'] == 'claude':
            forwarded_reasoning = cmd[cmd.index('--effort') + 1] if '--effort' in cmd else ''
            expected_model = service.resolve_claude_cli_model_name(row['model'])
            expected_reasoning = service.resolve_claude_reasoning_effort(
                model_name=row['model'], reasoning_effort=row['reasoning']) or ''
        else:
            forwarded_reasoning = next((json.loads(arg.split('=', 1)[1]) for arg in cmd
                                        if arg.startswith('model_reasoning_effort=')), '')
            expected_model = row['model']
            expected_reasoning = service.resolve_codex_reasoning_effort(
                model_name=row['model'], reasoning_effort=row['reasoning']) or ''
        matches = forwarded_model == (expected_model or None) and forwarded_reasoning == expected_reasoning
        # Allowlist model/effort values only; full argv can contain private paths/config.
        validation = {name: {key: diagnostic_text(value) if isinstance(value, str) else value
                            for key, value in values.items()}
                      for name, values in {
                          'requested': {'model': row['model'], 'reasoning': row['reasoning']},
                          'expected': {'model': expected_model or None, 'reasoning': expected_reasoning},
                          'actual': {'model': forwarded_model, 'reasoning': forwarded_reasoning},
                      }.items()}
        validation['matches'] = matches
        # Flush before spawning so timeouts and spawn errors retain preflight evidence.
        print(json.dumps({'event': 'cli_validation', 'cli_validation': validation}), flush=True)
        if not matches:
            print(json.dumps({'status': 'FAIL', 'failure_phase': 'cli_argument_validation',
                              'detail': 'Production CLI arguments differ from normalized model/reasoning',
                              'cli_validation': validation, 'execution': execution}))
            return
        exec_env = service._build_agent_exec_env(row['backend'], internal_api_key=internal_key)
        service._apply_agent_backend_exec_env(exec_env, row['backend'], model_override=row['model'])
        # Test-only pool values must not leak into CLI descendants.
        exec_env.pop('WORKBENCH_TEST_API_KEYS', None)
        exec_env.pop('WORKBENCH_TEST_SELECTED_API_KEY', None)
        cmd = service._wrap_codex_cli_command(cmd) if actual_backend == 'dtgpt' else cmd
        completed = subprocess.run(cmd, input=prompt, text=True, encoding='utf-8',
                                   errors='replace', capture_output=True, cwd=str(service.WORKSPACE_DIR), env=exec_env)
        ok = completed.returncode == 0 and token in completed.stdout
        evidence = 'production_cli_argument_builder'
        diagnostics = {'output': completed.stdout, 'error': completed.stderr, 'exit_code': completed.returncode}
    print(json.dumps({'status': 'PASS' if ok else 'FAIL', 'evidence': evidence,
                      'forwarded_model': forwarded_model, 'forwarded_reasoning': forwarded_reasoning,
                      'diagnostics': response_diagnostics(diagnostics), 'execution': execution}))


def run_direct(row, timeout):
    global _direct_key_cursor
    env = os.environ.copy()
    env.pop('WORKBENCH_TEST_SELECTED_API_KEY', None)
    # Only the explicit test pool overrides persisted production credentials.
    # DTGPT_API_KEY retains the production resolver's normal fallback priority.
    if row['backend'] != 'opencode' and os.environ.get('WORKBENCH_TEST_API_KEYS', '').strip():
        keys = environment_api_keys()
        env['WORKBENCH_TEST_SELECTED_API_KEY'] = keys[_direct_key_cursor % len(keys)]
        _direct_key_cursor += 1
    cmd = [sys.executable, str(Path(__file__).resolve()), '--direct-case', json.dumps(row)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=os.name != 'nt', env=env)

    def with_validation(result):
        for line in stdout.decode('utf-8', errors='replace').splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get('event') == 'cli_validation':
                result['cli_validation'] = entry['cli_validation']
            if isinstance(entry, dict) and entry.get('event') == 'execution_preflight':
                result['execution'] = entry['execution']
        return result

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        if proc.returncode:
            return with_validation({'status': 'FAIL', 'detail': 'Direct worker failed; check local Python dependencies/CLI configuration',
                    'exit_code': proc.returncode, 'output': diagnostic_text(stdout.decode('utf-8', errors='replace')),
                    'error': diagnostic_text(stderr.decode('utf-8', errors='replace'))})
        return with_validation(json.loads(stdout.decode('utf-8').splitlines()[-1]))
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        if isinstance(exc, KeyboardInterrupt):
            raise
        return with_validation({'status': 'TIMEOUT', 'detail': 'Direct process tree terminated; OpenCode remote cleanup may be needed',
                'output': diagnostic_text(stdout.decode('utf-8', errors='replace')),
                'error': diagnostic_text(stderr.decode('utf-8', errors='replace'))})
    except (ValueError, IndexError):
        return with_validation({'status': 'FAIL', 'detail': 'Invalid direct worker verdict',
                'output': diagnostic_text(stdout.decode('utf-8', errors='replace')),
                'error': diagnostic_text(stderr.decode('utf-8', errors='replace'))})


def run_standalone(cases, args, directory):
    """Read-only with respect to the Workbench HTTP server and chat store."""
    results = []
    interrupted = False
    try:
        for index, (row, _) in enumerate(cases, 1):
            started = time.monotonic()
            result = dict(row, scenario='direct')
            trace_path = directory / f'case-{index:03d}.jsonl'
            result['trace_file'] = trace_path.name

            def trace(event, **fields):
                with trace_path.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(dict(event=event, at=int(time.time() * 1000),
                        elapsed=round(time.monotonic() - started, 3), **fields), ensure_ascii=False) + '\n')

            trace('case_started', backend=row['backend'], model=row['model'],
                  reasoning=row['reasoning'], mode='direct', timeout=args.timeout)
            if row['status'] == 'PLANNED':
                with Progress(row, 'direct', index, len(cases), args.timeout) as progress:
                    progress.update('running-direct')
                    try:
                        result.update(run_direct(row, args.timeout))
                    except Exception as exc:
                        result.update(status='FAIL', detail=diagnostic_text(str(exc)),
                                      exception_traceback=diagnostic_text(traceback.format_exc()))
                    progress.update('finished-direct', status=result['status'])
            result['seconds'] = round(time.monotonic() - started, 3)
            trace('case_finished', result=result)
            results.append(result)
            report(directory, results)
    except KeyboardInterrupt:
        interrupted = True
        raise
    finally:
        report(directory, results)
        write_json(directory / 'summary.json', dict(mode='direct', cases=len(results),
            interrupted=interrupted, workbench_settings_changed=False, workbench_sessions_created=0))
        print(f'Reports: {directory}')
    return int(any(r['status'] != 'PASS' for r in results))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def report(directory, results):
    write_json(directory / 'results.json', results)
    (directory / 'diagnostics.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results), encoding='utf-8')
    fields = ['backend', 'model', 'reasoning', 'scenario', 'status', 'seconds', 'session_id', 'evidence', 'detail', 'cleanup_error', 'direct']
    with (directory / 'results.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields, extrasaction='ignore')
        writer.writeheader()
        for row in results:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v for k, v in row.items() if k in fields})


def main(argv=None):
    global _direct_key_cursor
    _direct_key_cursor = 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--backend', action='append', choices=['codex', 'dtgpt', 'claude', 'opencode'],
                        help='Backend to test (repeatable; default: opencode, claude)')
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--reasoning', action='append', default=[])
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list-only', action='store_true')
    parser.add_argument('--mode', choices=['direct', 'stream', 'sync'], default='direct',
                        help='direct (default): no Workbench sessions/settings writes; stream/sync: live HTTP integration tests')
    parser.add_argument('--direct', choices=['off', 'failed', 'all'], default='off')
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--output-directory')
    parser.add_argument('--restore-settings')
    parser.add_argument('--context-checks', action='store_true')
    parser.add_argument('--worktree-check', action='store_true')
    parser.add_argument('--queue-check', action='store_true')
    parser.add_argument('--expected-workspace', default='')
    parser.add_argument('--direct-case', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.direct_case:
        direct_worker(json.loads(args.direct_case))
        return 0
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.mode == 'direct' and (args.context_checks or args.worktree_check or args.queue_check):
        parser.error('Context/worktree/queue checks require --mode stream or --mode sync (creates Workbench sessions)')
    if args.mode == 'direct' and args.direct != 'off':
        parser.error('--direct is an additional comparison for --mode stream/sync; default mode already runs directly')
    if args.context_checks and not args.expected_workspace:
        parser.error('--context-checks requires --expected-workspace (server absolute path)')
    if urlsplit(args.base_url).scheme not in ('http', 'https'):
        parser.error('Expected HTTP(S) base URL')
    client = Client(args.base_url, min(30, args.timeout))
    if args.restore_settings:
        backup = json.loads(Path(args.restore_settings).read_text(encoding='utf-8'))
        if backup['base_url'] != client.url:
            parser.error('Restore file base URL differs')
        restored = client.request('PATCH', '/settings', backup['settings'])['settings']
        if any((restored.get(k) or '') != (v or '') for k, v in backup['settings'].items()):
            raise RuntimeError('Restored settings differ from backup')
        print('Settings restored.')
        return 0
    print_key_guidance()
    snapshot = client.request('GET', '/settings')
    backends = args.backend or ['opencode', 'claude']
    rows = matrix(snapshot, backends, args.model, args.reasoning, args.all)
    args.queue_candidates = matrix(snapshot, backends, [], [], True)
    args.queue_candidates = [r for r in args.queue_candidates if r['status'] == 'PLANNED']
    scenarios = ['echo']
    if args.context_checks:
        scenarios += ['workspace', 'attachment']
    if args.worktree_check:
        scenarios += ['worktree']
    if args.queue_check:
        scenarios += ['queue']
    cases = []
    seen = set()
    for row in rows:
        cases.append((row, 'echo'))
        if row['status'] == 'PLANNED' and row['backend'] not in seen:
            cases.extend((row, scenario) for scenario in scenarios[1:])
            seen.add(row['backend'])
    count = sum(r['status'] == 'PLANNED' for r, _ in cases)
    queue_count = sum(s == 'queue' for _, s in cases)
    if args.mode == 'direct':
        print(f'Direct model calls: {count}; Workbench sessions: 0; settings: read-only. Runs on this PC using local credentials.')
    else:
        print('HTTP integration mode creates Workbench sessions and requires an idle server.')
        print(f'Workbench model calls: {count + queue_count}; direct comparison: up to {count if args.direct != "off" else 0}')
    for row, scenario in cases:
        print(f"{row['backend']:8} {row['model']:32} {row['reasoning'] or '(default)':10} {scenario:12} {row['status']}")
    if args.list_only:
        return 0
    directory = Path(args.output_directory or ROOT / 'tmp' / ('backend-tests-' + uuid.uuid4().hex[:12])).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    if args.mode == 'direct':
        return run_standalone(cases, args, directory)
    backup_settings = {k: snapshot['settings'].get(k) or '' for k in KEYS}
    backup = directory / 'restore-settings.json'
    write_json(backup, {'base_url': client.url, 'settings': backup_settings})
    print(f'Recovery file: {backup}')
    results = []
    restoration_failed = False
    try:
        active = client.request('GET', '/streams')['streams']
        if any(not s.get('done') for s in active):
            raise RuntimeError('Active streams found; run tests when Workbench is idle')
        for index, (row, scenario) in enumerate(cases, 1):
            if row['status'] == 'PLANNED':
                with Progress(row, scenario, index, len(cases), args.timeout) as progress:
                    args.progress = progress
                    args.trace_path = directory / f'case-{index:03d}.jsonl'
                    try:
                        result = run_case(client, row, args, scenario)
                    finally:
                        args.progress = None
            else:
                result = dict(row, scenario=scenario)
            if not result.get('cleanup_error') and row['status'] == 'PLANNED' and (args.direct == 'all' or (args.direct == 'failed' and result['status'] != 'PASS')):
                with Progress(row, scenario + '/direct', index, len(cases), args.timeout) as progress:
                    progress.update('running-direct')
                    result['direct'] = run_direct(row, args.timeout)
                    progress.update('finished-direct', status=result['direct']['status'])
            results.append(result)
            report(directory, results)
            print(f"{row['backend']} {row['model']} reasoning={row['reasoning'] or '(default)'} "
                  f"{scenario}: {result['status']} elapsed={result.get('seconds', 0):.3f}s", flush=True)
            if result.get('cleanup_error'):
                break
    finally:
        try:
            restored = client.request('PATCH', '/settings', backup_settings)['settings']
            if any((restored.get(k) or '') != v for k, v in backup_settings.items()):
                raise RuntimeError('Restored settings differ')
        except Exception:
            restoration_failed = True
            print(f'Settings restoration FAILED. Use -RestoreSettings "{backup}"', file=sys.stderr)
        report(directory, results)
        write_json(directory / 'summary.json', {'settings_restored': not restoration_failed, 'cases': len(results)})
    print(f'Reports: {directory}')
    return int(restoration_failed or any(r['status'] != 'PASS' or (r.get('direct') or {}).get('status', 'PASS') != 'PASS' for r in results))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f'Test runner failed: {safe_detail(str(exc))}', file=sys.stderr)
        sys.exit(2)
