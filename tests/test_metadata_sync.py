"""Verify history, input boundaries, and manual runner invocation."""
import json
from pathlib import Path
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.blueprints import metadata_sync as routes
from codex_agent.services import metadata_sync as sync


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, 'ROOT', tmp_path)
    monkeypatch.setattr(sync, '_PROCESS', None)
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'codex-web-app/templates'))
    app.register_blueprint(routes.bp)
    monkeypatch.setattr(routes, 'is_internal_multiuser_mode', lambda: False)
    return tmp_path, app.test_client()


def write_run(root, name, payload):
    folder = root / '.sync_runtime/codex_daily_doc_sync/runs' / name
    folder.mkdir(parents=True)
    (folder / 'run_metadata.json').write_text(json.dumps(payload))
    return folder


def test_history_distinguishes_legacy_and_actual_changes(setup):
    root, client = setup
    write_run(root, '20261001', {'result': 'success'})
    folder = write_run(root, '20261002', {'result': 'success', 'published': True, 'changes': [{'path': 'a.md', 'diff': '-old\n+new'}]})
    (folder / 'codex_final_response.md').write_text('Summary and deferred items')
    response = client.get('/api/codex/metadata-sync').get_json()
    assert response['runs'][0]['changed_files'] == 1
    assert response['runs'][1]['has_change_record'] is False
    detail = client.get('/api/codex/metadata-sync/runs/20261002').get_json()
    assert detail['metadata']['changes'][0]['diff'] == '-old\n+new'
    assert detail['summary'] == 'Summary and deferred items'
    assert client.get('/metadata-sync').status_code == 200


@pytest.mark.parametrize('scope', ['all', 'feature:a;touch /tmp/a', '../escape', None, ['feature:vcd']])
def test_rejects_broad_or_invalid_scope_before_starting(setup, scope):
    _, client = setup
    response = client.post('/api/codex/metadata-sync/run', json={'scope': scope}, headers={'X-Workbench-Request': 'metadata-sync'})
    assert response.status_code == 400


def test_post_requires_same_origin_and_explicit_header(setup):
    _, client = setup
    assert client.post('/api/codex/metadata-sync/run', json={'scope': 'feature:vcd'}).status_code == 400
    assert client.post('/api/codex/metadata-sync/run', json={'scope': 'feature:vcd'}, headers={'X-Workbench-Request': 'metadata-sync', 'Origin': 'https://foreign.example'}).status_code == 403


@pytest.mark.parametrize('scope', ['feature:vcd', 'project:HPA'])
def test_manual_start_uses_argument_array_and_defers_duplicate(setup, monkeypatch, scope):
    root, client = setup
    runner = root / 'git_actions/scripts/run_metadata_doc_sync.py'
    runner.parent.mkdir(parents=True)
    runner.touch()
    calls = []
    class Process:
        pid = 123
        def poll(self):
            return None
    def start(command, **kwargs):
        calls.append((command, kwargs))
        return Process()
    monkeypatch.setattr(sync.subprocess, 'Popen', start)
    kwargs = {'json': {'scope': scope}, 'headers': {'X-Workbench-Request': 'metadata-sync'}}
    assert client.post('/api/codex/metadata-sync/run', **kwargs).status_code == 202
    assert calls[0][0][-4:] == ['--mode', 'manual', '--scope', scope]
    assert client.post('/api/codex/metadata-sync/run', **kwargs).status_code == 409
    assert len(calls) == 1


def test_missing_project_and_missing_run_have_explicit_results(setup):
    _, client = setup
    assert client.get('/api/codex/metadata-sync').get_json()['available'] is False
    assert client.get('/api/codex/metadata-sync/runs/missing').status_code == 404
    assert client.get('/api/codex/metadata-sync/runs/invalid.id').status_code == 400


def test_shared_project_is_restricted_in_multiuser_mode(setup, monkeypatch):
    _, client = setup
    monkeypatch.setattr(routes, 'is_internal_multiuser_mode', lambda: True)
    assert client.get('/api/codex/metadata-sync').status_code == 403
    assert client.get('/metadata-sync').status_code == 403
    assert client.get('/api/codex/metadata-sync/preview').status_code == 403


def test_preview_collects_live_candidates_without_sync_or_state_writes(setup, monkeypatch):
    root, client = setup
    collector = root / 'git_actions/scripts/collect_metadata_doc_sync_context.py'
    collector.parent.mkdir(parents=True)
    collector.touch()
    state = sync.runtime() / 'state.json'
    state.parent.mkdir(parents=True)
    state.write_text('{"last_success_head": "abc123"}')
    before = state.read_bytes()
    calls = []
    def collect(command, **kwargs):
        calls.append(command)
        assert kwargs['cwd'] == root
        assert kwargs['timeout'] == 30
        output = Path(command[command.index('--output') + 1])
        output.write_text(json.dumps({
            'generated_at_kst': '2026-10-26T12:00:00+09:00',
            'affected_scopes': {'features': ['vcd', 'no_docs'], 'projects': ['HPA', 'empty_project']},
            'changed_paths': {'all': ['src/vcd.py']},
            'candidate_docs': [
                {'scope_type': 'feature', 'scope_name': 'vcd', 'path': 'vcd.md', 'reasons': ['affected_scope']},
                {'scope_type': 'feature', 'scope_name': 'translation_only', 'path': 'translated.md', 'reasons': ['stale_translation']},
                {'scope_type': 'project', 'scope_name': 'HPA', 'path': 'HPA.md', 'reasons': ['affected_scope']},
                {'scope_type': 'project', 'scope_name': 'translated_project', 'path': 'project_en.md', 'reasons': ['stale_translation']},
                {'scope_type': 'design_tool', 'scope_name': 'sim', 'path': 'sim.md', 'reasons': ['affected_scope']},
            ], 'warnings': ['review warning'],
        }))
        return sync.subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(sync.subprocess, 'run', collect)
    response = client.get('/api/codex/metadata-sync/preview')
    assert response.status_code == 200
    data = response.get_json()
    assert [f['name'] for f in data['features']] == ['no_docs', 'translation_only', 'vcd']
    assert data['features'][2]['documents'] == ['vcd.md']
    assert data['features'][1]['reasons'] == ['stale_translation']
    assert [p['name'] for p in data['projects']] == ['HPA', 'empty_project', 'translated_project']
    assert data['projects'][0]['documents'] == ['HPA.md']
    assert data['projects'][1]['documents'] == []
    assert data['projects'][2]['reasons'] == ['stale_translation']
    assert data['other_documents'][0]['path'] == 'sim.md'
    assert data['warnings'] == ['review warning']
    assert data['changed_paths_count'] == 1
    assert calls[0][-2:] == ['--since-ref', 'abc123']
    assert '--skip-validation' in calls[0]
    assert state.read_bytes() == before
    assert not (sync.runtime() / 'runs').exists()
    assert not (sync.runtime() / 'run.lock').exists()


def test_preview_reports_missing_collector_and_timeout(setup, monkeypatch):
    root, client = setup
    assert client.get('/api/codex/metadata-sync/preview').status_code == 503
    collector = root / 'git_actions/scripts/collect_metadata_doc_sync_context.py'
    collector.parent.mkdir(parents=True)
    collector.touch()
    def timeout(*args, **kwargs):
        raise sync.subprocess.TimeoutExpired('collector', 30)
    monkeypatch.setattr(sync.subprocess, 'run', timeout)
    assert client.get('/api/codex/metadata-sync/preview').status_code == 504


def test_preview_reports_collector_failure_and_empty_results(setup, monkeypatch):
    root, client = setup
    collector = root / 'git_actions/scripts/collect_metadata_doc_sync_context.py'
    collector.parent.mkdir(parents=True)
    collector.write_text('import sys; sys.exit(1)')
    assert client.get('/api/codex/metadata-sync/preview').status_code == 503
    collector.write_text('import json, sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index("--output") + 1]).write_text(json.dumps({}))')
    result = client.get('/api/codex/metadata-sync/preview').get_json()
    assert result['features'] == []
    assert result['projects'] == []
    assert result['since_ref'] == ''


def test_dashboard_uses_mounted_api_url(setup):
    _, client = setup
    response = client.get('/metadata-sync', environ_overrides={'SCRIPT_NAME': '/workbench'})
    assert b'data-api-url="/workbench/api/codex/metadata-sync"' in response.data
    assert b'id="preview-projects"' in response.data
