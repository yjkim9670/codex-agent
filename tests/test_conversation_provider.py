"""Provider isolation contract and opt-in native CLI request audit."""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'conversation-app'))
from services.codex_provider import INSTRUCTIONS, Provider, RPC, sanitize_catalog
from shared.chat_accounts import accounts
from services.artifacts import Artifacts, TOOL, TOOL_NAME


def test_catalog_removes_coding_instructions_and_tools():
    result = sanitize_catalog([{'slug': 'model', 'apply_patch_tool_type': 'freeform',
        'model_messages': {'instructions_template': 'coding agent'}, 'base_instructions': 'coding agent',
        'experimental_supported_tools': ['clock', 'send_user_message_async'],
        'supported_reasoning_levels': [{'effort': 'low'}, {'effort': 'ultra'}]}])[0]
    assert result['apply_patch_tool_type'] is None
    assert result['model_messages'] is None
    assert result['experimental_supported_tools'] == []
    assert result['base_instructions'] == INSTRUCTIONS
    assert result['tool_mode'] == 'direct'
    assert result['node_repl_disabled'] and result['multi_agent_version'] == 'disabled'
    assert result['supported_reasoning_levels'] == [{'effort': 'low'}]


def test_auth_snapshot_has_no_refresh_token_or_extensions(tmp_path):
    source = tmp_path / 'original'
    source.mkdir()
    original = {'tokens': {'access_token': 'access', 'id_token': 'id', 'account_id': 'identity', 'refresh_token': 'secret'}, 'last_refresh': '2026-10-28T00:00:00Z'}
    (source / 'auth.json').write_text(json.dumps(original))
    provider = Provider(tmp_path / 'chat')
    account = {'id': 'a', 'codex_home': str(source), 'provider_account_id': 'identity'}
    home, workspace = provider.prepare(account)
    auth = json.loads((home / 'auth.json').read_text())
    assert auth['tokens']['refresh_token'] == ''
    assert auth['last_refresh'] == original['last_refresh']
    assert json.loads((source / 'auth.json').read_text()) == original
    assert not (home / 'config.toml').exists() and not (home / 'skills').exists()
    assert list(workspace.iterdir()) == []
    assert (home / 'auth.json').stat().st_mode & 0o777 == 0o600
    assert provider.home({**account, 'provider_account_id': 'other'}) != home


@pytest.mark.skipif(os.environ.get('RUN_CODEX_CHAT_NATIVE_TESTS') != '1', reason='Opt-in native Codex request audit; no model API calls')
def test_native_cli_exposes_only_artifacts_and_optional_web(tmp_path):
    """Capture real serialized CLI requests at a local fake provider, not self-report."""
    captured = queue.Queue()
    handled = threading.Event()
    invoke = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            if not invoke.is_set():
                invoke.set()
                captured.put(json.loads(raw))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                item = {'type': 'function_call', 'id': 'fc_audit', 'call_id': 'call_audit',
                        'name': TOOL_NAME, 'namespace': 'functions',
                        'arguments': json.dumps({'operation': 'write', 'path': 'audit.txt', 'content': 'artifact audit'})}
                events = [
                    ('response.created', {'response': {'id': 'resp_audit', 'status': 'in_progress', 'output': []}}),
                    ('response.output_item.done', {'output_index': 0, 'item': item}),
                    ('response.completed', {'response': {'id': 'resp_audit', 'status': 'completed', 'output': [item]}}),
                ]
                for kind, value in events:
                    value['type'] = kind
                    self.wfile.write(('event: ' + kind + '\ndata: ' + json.dumps(value) + '\n\n').encode())
                return
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"audit complete","type":"invalid_request_error"}}')
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    account = next(a for a in accounts() if a['authenticated'])
    metadata = json.loads((Path(account['codex_home']) / 'models_cache.json').read_text())['models']
    # No real authentication is copied or sent to the audit endpoint.
    home = tmp_path / 'home'
    home.mkdir()
    workspace = tmp_path / 'empty'
    workspace.mkdir()
    catalog = home / 'chat_models.json'
    catalog.write_text(json.dumps({'models': sanitize_catalog(metadata)}))
    try:
        for mode in ('disabled', 'live'):
            artifacts = Artifacts()
            handled.clear()
            invoke.clear()
            def handle(params):
                result = artifacts.call(params)
                handled.set()
                return result
            rpc = RPC(home, workspace, catalog, {
                'model_providers.audit.name': 'audit',
                'model_providers.audit.base_url': f'http://127.0.0.1:{http.server_port}/v1',
                'model_providers.audit.wire_api': 'responses',
                'model_providers.audit.requires_openai_auth': False,
                'model_providers.audit.supports_standalone_web_search': True,
                'features.enable_request_compression': False}, artifact_handler=handle)
            try:
                thread = rpc.call('thread/start', {'model': metadata[0]['slug'], 'modelProvider': 'audit',
                    'cwd': str(workspace), 'baseInstructions': INSTRUCTIONS,
                    'config': {'web_search': mode}, 'dynamicTools': [TOOL], 'environments': [], 'approvalPolicy': 'never', 'sandbox': 'read-only'})
                assert thread.get('instructionSources') == []
                rpc.call('turn/start', {'threadId': thread['thread']['id'], 'input': [{'type': 'text', 'text': 'Hello'}], 'effort': 'low'})
                body = captured.get(timeout=30)
                tools = body.get('tools', []) + [t for i in body.get('input', []) if i.get('type') == 'additional_tools' for t in i.get('tools', [])]
                functions = [t for t in tools if t.get('name') == 'functions']
                assert len(functions) == 1
                artifact_tools = functions[0]['tools']
                assert len(artifact_tools) == 1 and artifact_tools[0]['name'] == TOOL_NAME
                remaining = [t for t in tools if t.get('name') != 'functions']
                if mode == 'disabled':
                    assert remaining == []
                else:
                    assert len(remaining) == 1 and remaining[0]['name'] == 'web'
                    assert [t['name'] for t in remaining[0]['tools']] == ['run']
                assert handled.wait(10), 'Native CLI did not dispatch the artifact call'
                assert (artifacts.root / 'audit.txt').read_text() == 'artifact audit'
                request_context = json.dumps(body.get('input', []))
                assert 'AGENTS.md' not in request_context
                assert 'available_skills' not in request_context
                assert 'coding workspace' not in request_context
            finally:
                rpc.close()
                artifacts.close()
                shutil.rmtree(artifacts.root)
    finally:
        http.shutdown()
        http.server_close()


def test_title_stream_hides_fragmented_metadata_and_preserves_markdown():
    from services.codex_provider import TitleStream
    events = []
    stream = TitleStream(lambda kind, data: events.append((kind, data)))
    for part in ['<chat_', 'title>번역 요청</chat_title>', '\n\n**Hello**', '\nworld']:
        stream.delta(part)
    assert [data['title'] for kind, data in events if kind == 'title'] == ['번역 요청']
    assert ''.join(data['text'] for kind, data in events if kind == 'delta') == '**Hello**\nworld'
    events.clear()
    stream = TitleStream(lambda kind, data: events.append((kind, data)))
    stream.delta('Title omitted')
    stream.delta('', final=True)
    assert events == [('delta', {'text': 'Title omitted'})]


def test_limits_normalization_uses_duration_and_codex_bucket():
    from services.codex_provider import normalize_limits
    result = normalize_limits({'rateLimits': {'primary': {'windowDurationMins': 10080, 'usedPercent': 25, 'resetsAt': 2000000000}}})
    assert result['five_hour'] is None
    assert result['weekly']['remaining_percent'] == 75
    result = normalize_limits({'rateLimitsByLimitId': {'codex': {'primary': {'windowDurationMins': 300, 'usedPercent': 120}, 'secondary': {'windowDurationMins': 10080, 'usedPercent': float('nan')}}}})
    assert result['five_hour']['remaining_percent'] == 0
    assert result['weekly'] is None
    assert normalize_limits({})['five_hour'] is None


def test_limits_cache_isolates_accounts_and_closes_rpc(tmp_path, monkeypatch):
    import services.codex_provider as module
    opened = []
    class FakeRPC:
        def __init__(self, *args):
            self.closed = False
            opened.append(self)
        def call(self, method, params, timeout):
            assert method == 'account/rateLimits/read'
            return {'rateLimits': {'primary': {'windowDurationMins': 300, 'usedPercent': 20}}}
        def close(self):
            self.closed = True
    monkeypatch.setattr(module, 'RPC', FakeRPC)
    provider = Provider(tmp_path)
    monkeypatch.setattr(provider, 'prepare', lambda account: (tmp_path, tmp_path))
    account = {'id': 'one', 'provider_account_id': 'identity'}
    assert provider.limits(account)['five_hour']['remaining_percent'] == 80
    provider.limits(account)
    provider.limits(account, force=True)
    assert len(opened) == 1 and opened[0].closed
    provider.limits({**account, 'provider_account_id': 'other'})
    assert len(opened) == 2 and opened[1].closed


def test_first_reply_provider_separates_title_and_keeps_sandbox(tmp_path, monkeypatch):
    import services.codex_provider as module
    calls, output = [], []
    artifact_paths = []
    class FakeRPC:
        def __init__(self, home, workspace, catalog, artifact_handler):
            artifact_paths.append(artifact_handler.__self__.root)
            self.events = queue.Queue()
            for event in [
                {'method': 'item/agentMessage/delta', 'params': {'delta': '<chat_title>요청 제목</chat_title>\n\nHello'}},
                {'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': '<chat_title>요청 제목</chat_title>\n\nHello'}}},
                {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}},
            ]:
                self.events.put(event)
        def call(self, method, params):
            calls.append((method, params))
            if method == 'thread/start':
                return {'model': 'test', 'thread': {'id': 'thread'}}
            return {'turn': {'id': 'turn'}}
        def close(self):
            pass
    monkeypatch.setattr(module, 'RPC', FakeRPC)
    provider = Provider(tmp_path)
    monkeypatch.setattr(provider, 'models', lambda account: [{'model': 'test', 'defaultReasoningEffort': 'low', 'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]}])
    monkeypatch.setattr(provider, 'prepare', lambda account: (tmp_path, tmp_path))
    try:
        provider.run({'provider_account_id': 'account'}, {'model': 'test', 'effort': 'low', 'search': 'off', 'generate_title': True},
                     [{'role': 'user', 'content': 'Hello'}], lambda kind, data: output.append((kind, data)), threading.Event())
        start = calls[0][1]
        assert '<chat_title>' in start['baseInstructions']
        assert start['sandbox'] == 'read-only' and start['approvalPolicy'] == 'never'
        assert start['dynamicTools'] == [TOOL]
        assert ('title', {'title': '요청 제목'}) in output
        assert ('answer', {'text': 'Hello'}) in output
        assert output[-1] == ('done', {'status': 'completed'})
        assert all('<chat_title>' not in data['text'] for kind, data in output if kind in ('answer', 'delta'))
    finally:
        for artifact_path in artifact_paths:
            shutil.rmtree(artifact_path)
