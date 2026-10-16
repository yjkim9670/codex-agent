"""Workbench model smoke tests. Standard library only except optional direct workers."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
API = '/api/codex'
KEYS = ('agent_backend', 'model', 'reasoning_effort')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url, timeout=30):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, payload=None, raw=None, content_type=None, timeout=None):
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
            # Do not log server bodies: they can contain credentials/prompts.
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
    expected = dict(response_agent_backend=row['backend'], response_model=row['model'],
                    response_reasoning_effort=row['reasoning'])
    for key, value in expected.items():
        actual = data.get(key)
        if key == 'response_agent_backend':
            actual = actual or data.get('agent_backend')
        if (actual or '') != value:
            raise AssertionError(f'{key} mismatch: expected {value!r}, received {actual!r}')


def wait_stream(client, stream_id, deadline):
    while time.monotonic() < deadline:
        data = client.request('GET', '/streams/' + quote(stream_id, safe=''))
        if data.get('done') and data.get('saved'):
            return data
        time.sleep(min(0.3, max(0, deadline - time.monotonic())))
    raise TimeoutError('Stream completion/storage timed out')


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
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def _emit(self):
        # Only identifiers and execution state; never prompts or response bodies.
        state = ' '.join(f'{key}={value}' for key, value in self.state.items())
        line = (f'{self.label} {state} elapsed={time.monotonic() - self.started:.1f}s '
                f'timeout={self.timeout:g}s')
        line = ''.join(c if c.isprintable() else ' ' for c in safe_detail(line))
        print(line, flush=True)

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


def run_case(client, row, args, scenario='echo'):
    result = dict(row, scenario=scenario, evidence='workbench_metadata_and_persisted_response')
    started = time.monotonic()
    session_id = stream_id = None
    settled = True
    token = 'WBTEST_' + uuid.uuid4().hex
    payload = {'prompt': f'Reply with exactly {token}. Do not modify any files.'}
    queued_token = None
    progress = getattr(args, 'progress', None)

    def update(phase, **identifiers):
        if progress is not None:
            progress.update(phase, **identifiers)

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
        if use_stream:
            stream_id = data['stream_id']
            settled = False
        update('submitted' if use_stream else 'verifying', **({'stream': stream_id} if stream_id else {}))
        check_metadata(data, row)
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
            check_metadata(data, row)
            if data.get('exit_code') != 0:
                raise AssertionError('Stream exited unsuccessfully')
        update('verifying')
        session = client.request('GET', f'/sessions/{session_id}')['session']
        message_id = data.get('assistant_message_id') or (data.get('assistant_message') or {}).get('id')
        message = next((m for m in session['messages'] if m.get('id') == message_id), None)
        if not message or message.get('role') != 'assistant' or token not in (message.get('content') or ''):
            raise AssertionError('Final persisted assistant response missing expected token/path')
        if (message.get('metadata') or {}).get('error'):
            raise AssertionError('Persisted assistant response contains an error')
        check_metadata(message.get('metadata') or {}, row)
        if queued_token:
            update('waiting-queue')
            while time.monotonic() < started + args.timeout:
                for child in client.request('GET', '/streams?include_done=1')['streams']:
                    if child.get('session_id') == session_id and child['id'] != stream_id:
                        update('waiting-queue', queued_stream=child['id'])
                        terminal = wait_stream(client, child['id'], started + args.timeout)
                        check_metadata(terminal, row)
                        if terminal.get('exit_code') != 0:
                            raise AssertionError('Queued stream exited unsuccessfully')
                session = client.request('GET', f'/sessions/{session_id}')['session']
                queued = [m for m in session['messages'] if m.get('role') == 'assistant'
                          and queued_token in (m.get('content') or '')]
                if queued:
                    check_metadata(queued[-1].get('metadata') or {}, row)
                    break
                time.sleep(0.3)
            else:
                raise TimeoutError('Queued response not persisted')
        result['status'] = 'PASS'
    except Exception as exc:
        result.update(status='TIMEOUT' if isinstance(exc, TimeoutError) else 'FAIL',
                      detail=safe_detail(str(exc)))
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
    return result


def safe_detail(value):
    for name in ('WORKBENCH_TEST_COOKIE', 'WORKBENCH_TEST_AUTHORIZATION'):
        secret = os.environ.get(name)
        if secret:
            value = value.replace(secret, '[REDACTED]')
    return value[:700]


def direct_worker(row):
    sys.path.insert(0, str(ROOT))
    from codex_agent.services import codex_chat as service
    token = 'WBDIRECT_' + uuid.uuid4().hex
    prompt = f'Reply with exactly {token}. Do not modify files or run tools.'
    if row['backend'] == 'opencode':
        forwarded_model = service._opencode_model_payload(row['model'])
        if not forwarded_model:
            raise ValueError('OpenCode model must include provider/model')
        forwarded_reasoning = None
        prompt, context = service._prepare_agent_execution(prompt, {'agent_backend': 'opencode'})
        output, error, _, _ = service._execute_opencode_prompt(prompt, context, row['model'])
        ok = not error and token in (output or '')
        evidence = 'production_opencode_payload_builder'
    else:
        _, cmd = service._build_agent_command(prompt, agent_backend=row['backend'],
            model_override=row['model'], reasoning_override=row['reasoning'],
            inherit_model_settings=False, question_only=True)
        forwarded_model = cmd[cmd.index('--model') + 1] if '--model' in cmd else None
        if row['backend'] == 'claude':
            forwarded_reasoning = cmd[cmd.index('--effort') + 1] if '--effort' in cmd else ''
            expected_model = service.resolve_claude_cli_model_name(row['model'])
        else:
            forwarded_reasoning = next((json.loads(arg.split('=', 1)[1]) for arg in cmd
                                        if arg.startswith('model_reasoning_effort=')), '')
            expected_model = row['model']
        if forwarded_model != expected_model or forwarded_reasoning != row['reasoning']:
            raise ValueError('Production CLI arguments differ from requested model/reasoning')
        cmd = service._wrap_codex_cli_command(cmd) if row['backend'] == 'dtgpt' else cmd
        completed = subprocess.run(cmd, input=prompt, text=True, encoding='utf-8',
                                   errors='replace', capture_output=True, cwd=str(service.WORKSPACE_DIR))
        ok = completed.returncode == 0 and token in completed.stdout
        evidence = 'production_cli_argument_builder'
    # Only emit a verdict; CLI output may contain private environment context.
    print(json.dumps({'status': 'PASS' if ok else 'FAIL', 'evidence': evidence,
                      'forwarded_model': forwarded_model, 'forwarded_reasoning': forwarded_reasoning}))


def run_direct(row, timeout):
    cmd = [sys.executable, str(Path(__file__).resolve()), '--direct-case', json.dumps(row)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=os.name != 'nt')
    try:
        stdout, _ = proc.communicate(timeout=timeout)
        if proc.returncode:
            return {'status': 'FAIL', 'detail': 'Direct worker failed; check local Python dependencies/CLI configuration'}
        return json.loads(stdout.decode('utf-8').splitlines()[-1])
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return {'status': 'TIMEOUT', 'detail': 'Direct process tree terminated; OpenCode remote cleanup may be needed'}
    except (ValueError, IndexError):
        return {'status': 'FAIL', 'detail': 'Invalid direct worker verdict'}


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--backend', action='append', choices=['codex', 'dtgpt', 'claude', 'opencode'],
                        help='Backend to test (repeatable; default: claude, opencode)')
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--reasoning', action='append', default=[])
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list-only', action='store_true')
    parser.add_argument('--mode', choices=['stream', 'sync'], default='stream')
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
    snapshot = client.request('GET', '/settings')
    backends = args.backend or ['claude', 'opencode']
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
    print(f'Workbench model calls: {count + queue_count}; direct comparison: up to {count if args.direct != "off" else 0}')
    for row, scenario in cases:
        print(f"{row['backend']:8} {row['model']:32} {row['reasoning'] or '(default)':10} {scenario:12} {row['status']}")
    if args.list_only:
        return 0
    directory = Path(args.output_directory or ROOT / 'tmp' / ('backend-tests-' + uuid.uuid4().hex[:12])).resolve()
    directory.mkdir(parents=True, exist_ok=False)
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
