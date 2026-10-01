"""History consolidation must preserve originals and isolate execution state."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services import history_library as history


def write_store(path, sessions):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'sessions': sessions}), encoding='utf-8')


def session(sid='one', messages=None):
    return {'id': sid, 'title': '<script>alert(1)</script>', 'created_at': '2026-01-01T00:00:00Z',
            'updated_at': '2026-01-01T00:00:00Z', 'messages': messages or []}


def test_dry_run_import_idempotence_backup_and_original_unchanged(tmp_path):
    original = tmp_path / 'project/history.json'
    library = tmp_path / 'central/library.json'
    write_store(original, [session(), session()])
    contents = original.read_bytes()
    source = history.build_source(original.parent, [original])
    preview = history.import_sources([source], library)
    assert not library.exists()
    assert len(next(iter(preview['sources'].values()))['sessions']) == 1
    first = history.import_sources([source], library, apply=True)
    second = history.import_sources([source], library, apply=True)
    assert first == second
    assert original.read_bytes() == contents
    backup = next(library.parent.glob('*.backup-*'))
    assert history.load_library(backup) == first
    assert library.stat().st_mode & 0o777 == 0o600
    with pytest.raises(history.HistoryLibraryError, match='overwrite'):
        history.import_sources([source], original, apply=True)


def test_merge_preserves_messages_from_both_copies_and_project_identity(tmp_path):
    a, b = tmp_path / 'a.json', tmp_path / 'b.json'
    write_store(a, [session(messages=[{'id': 'a', 'role': 'user', 'content': 'first'}])])
    write_store(b, [session(messages=[{'id': 'b', 'role': 'assistant', 'content': 'second'}])])
    key, merged = history.build_source(tmp_path, [a, b])
    assert {m['id'] for m in merged['sessions'][0]['messages']} == {'a', 'b'}
    other_key, other = history.build_source(tmp_path / 'other-project', [a])
    payload = history.import_sources([(key, merged), (other_key, other)], tmp_path / 'library.json')
    assert len(payload['sources']) == 2


def test_live_refresh_deletion_and_fallback_are_explicit(tmp_path):
    original = tmp_path / 'history.json'
    write_store(original, [session()])
    _, source = history.build_source(tmp_path, [original])
    write_store(original, [session('two')])
    records, warnings = history.source_sessions(source)
    assert [r['id'] for r in records] == ['two']
    assert warnings == []
    write_store(original, [])
    assert history.source_sessions(source) == ([], [])
    original.write_text('{broken', encoding='utf-8')
    records, warnings = history.source_sessions(source)
    assert [r['id'] for r in records] == ['one']
    assert warnings


def test_corrupt_source_or_library_aborts_without_replacement(tmp_path):
    source_path = tmp_path / 'source.json'
    source_path.write_text('{broken', encoding='utf-8')
    with pytest.raises(history.HistoryLibraryError):
        history.build_source(tmp_path, [source_path])
    write_store(source_path, [session()])
    source = history.build_source(tmp_path, [source_path])
    library = tmp_path / 'library.json'
    library.write_text('{broken', encoding='utf-8')
    with pytest.raises(history.HistoryLibraryError):
        history.import_sources([source], library, apply=True)
    assert library.read_text() == '{broken'


def test_view_filters_by_registered_project_and_escapes_content(tmp_path, monkeypatch):
    from codex_agent import codex_app
    monkeypatch.setattr(codex_app, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'ensure_pending_queue_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'is_internal_multiuser_mode', lambda: False)
    monkeypatch.setattr(codex_app, '_is_company_mode_enabled', lambda: False)
    monkeypatch.setattr(codex_app, 'CODEX_API_ONLY_MODE', False)
    store = tmp_path / 'source.json'
    write_store(store, [session(messages=[{'id': 'm', 'role': 'user', 'content': '<script>bad()</script>'}])])
    key, source = history.build_source(tmp_path, [store])
    monkeypatch.setattr(history, 'get_sources', lambda: {key: source})
    client = codex_app.create_codex_app().test_client()
    response = client.get(f'/history?project={key}&session=one')
    assert response.status_code == 200
    assert b'&lt;script&gt;bad()&lt;/script&gt;' in response.data
    assert b'<script>bad()' not in response.data
    assert client.get('/history?project=unregistered').status_code == 404
    assert client.get(f'/history?project={key}&session=missing').status_code == 404
    monkeypatch.setattr(codex_app, '_is_company_mode_enabled', lambda: True)
    assert client.get('/history').status_code == 404
    monkeypatch.setattr(codex_app, '_is_company_mode_enabled', lambda: False)
    monkeypatch.setattr(codex_app, 'is_internal_multiuser_mode', lambda: True)
    monkeypatch.setattr(codex_app, 'load_ip_user_map', lambda _: {})
    assert client.get('/history').status_code == 403


def test_invalid_library_is_not_silently_reinitialized(tmp_path):
    path = tmp_path / 'library.json'
    path.write_text(json.dumps({'version': 1, 'sources': {'bad': {}}}))
    with pytest.raises(history.HistoryLibraryError):
        history.load_library(path)
