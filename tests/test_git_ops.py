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
