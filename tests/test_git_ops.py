from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent import codex_app
from codex_agent.blueprints import codex_chat as codex_chat_blueprint
from codex_agent.services import codex_chat, git_ops


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', '-C', str(repo_root), *args],
        capture_output=True,
        check=True,
        text=True,
    )


def _run_git_raw(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        capture_output=True,
        check=True,
        text=True,
    )


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _run_git(repo_root, 'init', '-q')
    _run_git(repo_root, 'config', 'user.email', 'codex@example.com')
    _run_git(repo_root, 'config', 'user.name', 'Codex Test')


def _commit_file(repo_root: Path, relative_path: str, content: str = 'initial\n') -> None:
    target = repo_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    _run_git(repo_root, 'add', relative_path)
    _run_git(repo_root, 'commit', '-qm', f'add {relative_path}')


def _configure_test_user(repo_root: Path) -> None:
    _run_git(repo_root, 'config', 'user.email', 'codex@example.com')
    _run_git(repo_root, 'config', 'user.name', 'Codex Test')


def _create_diverged_repo(tmp_path: Path, *, overlap: bool = False) -> Path:
    branch = 'dev/tj-0430'
    seed = tmp_path / 'seed'
    remote = tmp_path / 'remote.git'
    local = tmp_path / 'workspace'
    peer = tmp_path / 'peer'

    _init_repo(seed)
    _commit_file(seed, 'base.txt', 'base\n')
    base_branch = _run_git(seed, 'branch', '--show-current').stdout.strip()
    _run_git(seed, 'checkout', '-q', '-b', branch)
    _commit_file(seed, 'branch.txt', 'branch\n')
    _run_git_raw('init', '--bare', str(remote))
    _run_git(seed, 'remote', 'add', 'upstream', str(remote))
    _run_git(seed, 'push', '-q', 'upstream', base_branch, branch)

    _run_git_raw('clone', '-q', '-o', 'oo', str(remote), str(local))
    _configure_test_user(local)
    _run_git(local, 'checkout', '-q', '-b', branch, f'oo/{branch}')

    _run_git_raw('clone', '-q', str(remote), str(peer))
    _configure_test_user(peer)
    _run_git(peer, 'checkout', '-q', branch)

    if overlap:
        _commit_file(local, 'shared.txt', 'local\n')
        _commit_file(peer, 'shared.txt', 'remote\n')
    else:
        _commit_file(local, 'local.txt', 'local\n')
        _commit_file(peer, 'remote.txt', 'remote\n')
    _run_git(peer, 'push', '-q', 'origin', branch)
    return local


def test_git_revert_restores_modified_tracked_file(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt', 'before\n')
    (repo_root / 'tracked.txt').write_text('after\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('revert', {
        'repo_target': 'workspace',
        'file': 'tracked.txt',
    })

    assert result['ok'] is True
    assert result['changed_files_count'] == 0
    assert result['reverted_file'] == 'tracked.txt'
    assert (repo_root / 'tracked.txt').read_text(encoding='utf-8') == 'before\n'


def test_git_revert_removes_untracked_file(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt')
    (repo_root / 'scratch.txt').write_text('scratch\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('revert', {
        'repo_target': 'workspace',
        'file': 'scratch.txt',
    })

    assert result['ok'] is True
    assert result['changed_files_count'] == 0
    assert not (repo_root / 'scratch.txt').exists()


def test_git_status_lists_files_inside_untracked_directory(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt')
    (repo_root / 'scratch' / 'nested').mkdir(parents=True)
    (repo_root / 'scratch' / 'first.txt').write_text('first\n', encoding='utf-8')
    (repo_root / 'scratch' / 'nested' / 'second.txt').write_text('second\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('status', {'repo_target': 'workspace'})

    assert result['ok'] is True
    assert result['changed_files'] == [
        'scratch/first.txt',
        'scratch/nested/second.txt',
    ]
    assert all(entry['status'] == 'U' for entry in result['changed_files_detail'])


def test_git_status_decodes_korean_untracked_excel_filename(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _run_git(repo_root, 'config', 'core.quotePath', 'true')
    filename = '마이클_리포트_2026.05.09_GV80(제네시스 GV80).xls'
    (repo_root / filename).write_bytes(b'excel placeholder\n')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('status', {'repo_target': 'workspace'})

    assert result['ok'] is True
    assert result['changed_files'] == [filename]
    assert result['changed_files_detail'] == [
        {
            'path': filename,
            'status': 'U',
            'raw_status': '??',
        }
    ]


def test_git_diff_returns_tracked_file_changes(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt', 'before\n')
    (repo_root / 'tracked.txt').write_text('after\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('diff', {
        'repo_target': 'workspace',
        'file': 'tracked.txt',
    })

    assert result['ok'] is True
    assert result['repo_target'] == 'workspace'
    assert result['path'] == 'tracked.txt'
    assert result['status'] == 'M'
    assert 'diff --git a/tracked.txt b/tracked.txt' in result['diff']
    assert '-before' in result['diff']
    assert '+after' in result['diff']


def test_git_diff_returns_untracked_file_changes(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt')
    (repo_root / 'scratch.txt').write_text('scratch\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('diff', {
        'repo_target': 'workspace',
        'file': 'scratch.txt',
    })

    assert result['ok'] is True
    assert result['path'] == 'scratch.txt'
    assert result['status'] == 'U'
    assert result['is_untracked'] is True
    assert 'new file mode' in result['diff']
    assert '+scratch' in result['diff']


def test_git_commit_detail_lists_initial_commit_files(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'docs/초기 문서.txt', 'initial\n')
    commit_hash = _run_git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('commit-detail', {
        'repo_target': 'workspace',
        'commit_hash': commit_hash,
    })

    assert result['ok'] is True
    assert result['commit_hash'] == commit_hash
    assert result['is_initial_commit'] is True
    assert result['comparison_basis'] == 'empty_tree'
    assert result['changed_files_count'] == 1
    assert result['changed_files_detail'] == [{
        'path': 'docs/초기 문서.txt',
        'status': 'A',
        'raw_status': 'A',
    }]


def test_git_commit_detail_preserves_rename_paths(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'old name.txt', 'same content\n')
    (repo_root / 'nested').mkdir()
    _run_git(repo_root, 'mv', 'old name.txt', 'nested/new name.txt')
    _run_git(repo_root, 'commit', '-qm', 'rename file')
    commit_hash = _run_git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('commit-detail', {
        'repo_target': 'workspace',
        'commit_hash': commit_hash,
    })

    assert result['ok'] is True
    assert result['changed_files_detail'] == [{
        'path': 'nested/new name.txt',
        'status': 'R',
        'raw_status': 'R100',
        'original_path': 'old name.txt',
    }]


def test_git_commit_detail_uses_first_parent_for_merge_commit(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'base.txt', 'base\n')
    main_branch = _run_git(repo_root, 'branch', '--show-current').stdout.strip()
    _run_git(repo_root, 'checkout', '-qb', 'feature')
    _commit_file(repo_root, 'feature.txt', 'feature\n')
    _run_git(repo_root, 'checkout', '-q', main_branch)
    _commit_file(repo_root, 'main.txt', 'main\n')
    _run_git(repo_root, 'merge', '--no-ff', '-qm', 'merge feature', 'feature')
    commit_hash = _run_git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('commit-detail', {
        'repo_target': 'workspace',
        'commit_hash': commit_hash,
    })

    assert result['ok'] is True
    assert result['is_merge_commit'] is True
    assert result['parent_count'] == 2
    assert result['comparison_basis'] == 'first_parent'
    assert result['changed_files'] == ['feature.txt']


def test_git_commit_detail_rejects_non_full_sha(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('commit-detail', {
        'repo_target': 'workspace',
        'commit_hash': 'deadbeef',
    })

    assert result['error_code'] == 'git_commit_hash_invalid'


def test_git_commit_detail_api_returns_changed_file_tree_data(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'src/nested/app.py', 'print("ok")\n')
    commit_hash = _run_git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)
    monkeypatch.setattr(codex_app, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'ensure_pending_queue_background_worker', lambda: None)
    monkeypatch.setattr(codex_chat_blueprint, 'CODEX_ENABLE_GIT_API', True)
    app = codex_app.create_codex_app()
    app.config['TESTING'] = True

    with app.test_client() as client:
        response = client.post('/api/codex/git/commit-detail', json={
            'repo_target': 'workspace',
            'commit_hash': commit_hash,
        })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['commit_hash'] == commit_hash
    assert payload['changed_files_count'] == 1
    assert payload['changed_files_detail'][0]['path'] == 'src/nested/app.py'


def test_git_message_generates_detailed_message_with_codex_cli(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt', 'before\n')
    (repo_root / 'tracked.txt').write_text('after\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)
    captured = {}

    def fake_execute_codex_prompt(prompt, **kwargs):
        captured['prompt'] = prompt
        captured['kwargs'] = kwargs
        return (
            '{"subject":"feat: update tracked preview",'
            '"body_en":["Reflect tracked file changes","Verify bilingual commit body generation"],'
            '"body_ko":["추적 파일 변경사항을 반영","이중 언어 커밋 본문 생성을 검증"]}',
            None,
            {'total_tokens': 10},
            {'cli_runtime_ms': 1},
        )

    monkeypatch.setattr(codex_chat, 'execute_codex_prompt', fake_execute_codex_prompt)

    result = git_ops.run_git_action('message', {
        'repo_target': 'workspace',
        'files': ['tracked.txt'],
        'model': 'gpt-5-codex',
        'reasoning_effort': 'high',
    })

    assert result['ok'] is True
    assert result['commit_message_subject'] == 'feat: update tracked preview'
    assert result['commit_message_body'] == (
        '- Reflect tracked file changes\n'
        '- Verify bilingual commit body generation\n\n'
        '- 추적 파일 변경사항을 반영\n'
        '- 이중 언어 커밋 본문 생성을 검증'
    )
    assert result['generator_agent_backend'] == 'dtgpt'
    assert result['generator_execution_policy'] == 'read_only_ephemeral'
    assert result['generator_model'] == 'gpt-5-codex'
    assert result['generator_reasoning_effort'] == 'high'
    assert 'diff --git a/tracked.txt b/tracked.txt' in captured['prompt']
    assert 'The subject must be written in English only' in captured['prompt']
    assert 'faithful Korean translations of the body_en items' in captured['prompt']
    assert captured['kwargs']['agent_backend'] == 'dtgpt'
    assert captured['kwargs']['question_only'] is True
    assert captured['kwargs']['inherit_model_settings'] is False
    assert captured['kwargs']['model_override'] == 'gpt-5-codex'
    assert captured['kwargs']['reasoning_override'] == 'high'


def test_git_message_parser_formats_bilingual_body_and_rejects_non_english_subject():
    subject, body = git_ops._parse_commit_message_generation_output(
        '{"subject":"fix: 한국어 제목",'
        '"body_en":["Handle generated comments"],'
        '"body_ko":["생성된 코멘트를 처리합니다"]}'
    )

    assert git_ops._is_english_only_commit_subject(subject) is False
    assert body == (
        '- Handle generated comments\n\n'
        '- 생성된 코멘트를 처리합니다'
    )
    assert 'English' not in body
    assert '한국어' not in body
    assert git_ops._is_bilingual_commit_message_body(body) is True


def test_git_message_fallback_is_english_and_bilingual():
    subject, body = git_ops._build_ai_commit_message_fallback()

    assert git_ops._is_english_only_commit_subject(subject) is True
    assert git_ops._is_bilingual_commit_message_body(body) is True


def test_git_message_parser_rejects_unpaired_bilingual_items():
    _, body = git_ops._parse_commit_message_generation_output(
        '{"subject":"fix: keep translations paired",'
        '"body_en":["First change","Second change"],'
        '"body_ko":["첫 번째 변경"]}'
    )

    assert body == ''


def test_git_message_uses_persisted_default_model_when_request_omits_model(monkeypatch):
    captured = {}

    def fake_execute_codex_prompt(prompt, **kwargs):
        captured['prompt'] = prompt
        captured['kwargs'] = kwargs
        return '{}', None, None, None

    monkeypatch.setattr(codex_chat, 'execute_codex_prompt', fake_execute_codex_prompt)
    monkeypatch.setattr(
        codex_chat,
        'get_settings',
        lambda: {
            'git_commit_message_model': 'gpt-5.4-mini',
            'git_commit_message_reasoning_effort': 'low',
        },
    )

    git_ops._execute_commit_message_prompt('commit prompt')

    assert captured['kwargs']['model_override'] == 'gpt-5.4-mini'
    assert captured['kwargs']['reasoning_override'] == 'low'
    assert captured['kwargs']['agent_backend'] == 'dtgpt'
    assert captured['kwargs']['inherit_model_settings'] is False


def test_git_commit_accepts_subject_and_body(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'tracked.txt', 'before\n')
    (repo_root / 'tracked.txt').write_text('after\n', encoding='utf-8')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    stage_result = git_ops.run_git_action('stage', {
        'repo_target': 'workspace',
        'files': ['tracked.txt'],
        'replace': True,
    })
    assert stage_result['ok'] is True

    result = git_ops.run_git_action('commit', {
        'repo_target': 'workspace',
        'message_subject': 'feat: update tracked file',
        'message_body': '- 상세 본문을 커밋에 포함\n- 두 번째 줄 유지',
    })

    assert result['ok'] is True
    assert result['commit_message_subject'] == 'feat: update tracked file'
    assert '두 번째 줄 유지' in result['commit_message_body']
    log_message = _run_git(repo_root, 'log', '-1', '--pretty=%B').stdout.strip()
    assert log_message == 'feat: update tracked file\n\n- 상세 본문을 커밋에 포함\n- 두 번째 줄 유지'


def test_git_revert_restores_staged_rename(tmp_path, monkeypatch):
    repo_root = tmp_path / 'workspace'
    _init_repo(repo_root)
    _commit_file(repo_root, 'old.txt', 'old\n')
    _run_git(repo_root, 'mv', 'old.txt', 'new.txt')
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('revert', {
        'repo_target': 'workspace',
        'file': 'new.txt',
    })

    assert result['ok'] is True
    assert result['changed_files_count'] == 0
    assert (repo_root / 'old.txt').read_text(encoding='utf-8') == 'old\n'
    assert not (repo_root / 'new.txt').exists()


def test_git_sync_falls_back_to_upstream_remote_when_origin_is_missing(tmp_path, monkeypatch):
    repo_root = _create_diverged_repo(tmp_path)
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('sync', {
        'repo_target': 'workspace',
        'remote': 'origin',
        'branch': 'dev/tj-0430',
        'apply_after_fetch': False,
    })

    assert result['ok'] is True
    assert result['sync_remote'] == 'oo'
    assert result['sync_target'] == 'oo/dev/tj-0430'
    assert result['fallback_used'] is True
    assert result['sync_ahead_count_before'] == 1
    assert result['sync_behind_count_before'] == 1


def test_git_sync_prefers_upstream_remote_over_legacy_origin_request(tmp_path, monkeypatch):
    repo_root = _create_diverged_repo(tmp_path)
    origin_url = _run_git(repo_root, 'remote', 'get-url', 'oo').stdout.strip()
    _run_git(repo_root, 'remote', 'add', 'origin', origin_url)
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('sync', {
        'repo_target': 'workspace',
        'remote': 'origin',
        'branch': 'dev/tj-0430',
        'apply_after_fetch': False,
    })

    assert result['ok'] is True
    assert result['sync_remote'] == 'oo'
    assert result['fallback_used'] is True


def test_git_sync_merges_diverged_disjoint_changes(tmp_path, monkeypatch):
    repo_root = _create_diverged_repo(tmp_path)
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('sync', {
        'repo_target': 'workspace',
        'remote': 'origin',
        'branch': 'dev/tj-0430',
        'apply_after_fetch': True,
        'apply_strategy': 'auto',
    })

    assert result['ok'] is True
    assert result['sync_remote'] == 'oo'
    assert result['sync_apply_ok'] is True
    assert result['sync_apply_strategy'] == 'merge'
    assert result['sync_preflight']['state'] == 'diverged'
    assert result['sync_overlap_files'] == []
    assert (repo_root / 'remote.txt').read_text(encoding='utf-8') == 'remote\n'


def test_git_sync_blocks_diverged_overlap_before_merge(tmp_path, monkeypatch):
    repo_root = _create_diverged_repo(tmp_path, overlap=True)
    monkeypatch.setattr(git_ops, 'WORKSPACE_DIR', repo_root)

    result = git_ops.run_git_action('sync', {
        'repo_target': 'workspace',
        'remote': 'origin',
        'branch': 'dev/tj-0430',
        'apply_after_fetch': True,
        'apply_strategy': 'auto',
    })

    assert result['error_code'] == 'git_sync_overlap'
    assert result['sync_remote'] == 'oo'
    assert result['sync_preflight']['state'] == 'diverged'
    assert result['sync_overlap_files'] == ['shared.txt']
    assert not (repo_root / '.git' / 'MERGE_HEAD').exists()
