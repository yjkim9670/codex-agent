from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent.services import git_ops


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
