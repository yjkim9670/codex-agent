"""Git command helpers for Codex Agent."""

import os
import subprocess
import time
from pathlib import Path

from ..config import WORKSPACE_DIR
from .codex_chat import list_sessions

GIT_TIMEOUT_SECONDS = 600
_GIT_ACTIONS = {
    'sync': ['git', 'sync']
}


def _resolve_repo_root():
    if not WORKSPACE_DIR.exists():
        return None, f'워크스페이스 경로를 찾을 수 없습니다: {WORKSPACE_DIR}'
    try:
        result = subprocess.run(
            ['git', '-C', str(WORKSPACE_DIR), 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
    except FileNotFoundError:
        return None, 'git 명령을 찾을 수 없습니다.'
    except subprocess.TimeoutExpired:
        return None, 'git 저장소 확인 시간이 초과되었습니다.'
    except Exception as exc:
        return None, f'git 저장소 확인 중 오류가 발생했습니다: {exc}'

    if result.returncode != 0:
        stderr = (result.stderr or '').strip()
        stdout = (result.stdout or '').strip()
        return None, stderr or stdout or 'git 저장소를 찾을 수 없습니다.'

    repo_root = Path((result.stdout or '').strip())
    if not repo_root.exists():
        return None, 'git 저장소 경로를 확인할 수 없습니다.'
    return repo_root, None


def _run_git_command(cmd, repo_root, timeout, env):
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env
        )
    except FileNotFoundError:
        return None, {'error': 'git 명령을 찾을 수 없습니다.'}
    except subprocess.TimeoutExpired:
        return None, {'error': 'git 작업 시간이 초과되었습니다.'}
    except Exception as exc:
        return None, {'error': f'git 실행 중 오류가 발생했습니다: {exc}'}
    return result, None


def _sanitize_commit_title(title):
    normalized = ' '.join(str(title or '').strip().split())
    if not normalized:
        return 'codex: update'
    if not normalized.lower().startswith('codex:'):
        normalized = f'codex: {normalized}'
    if len(normalized) > 72:
        normalized = f"{normalized[:69]}..."
    return normalized


def _build_commit_message():
    sessions = list_sessions()
    title = sessions[0].get('title') if sessions else ''
    return _sanitize_commit_title(title)


def run_git_action(action):
    action = (action or '').strip()
    if action not in _GIT_ACTIONS and action != 'submit':
        return {'error': '지원하지 않는 git 작업입니다.'}

    repo_root, error = _resolve_repo_root()
    if error:
        return {'error': error}

    env = os.environ.copy()
    env.setdefault('GIT_TERMINAL_PROMPT', '0')

    started_at = time.time()
    if action == 'submit':
        status_result, error = _run_git_command(
            ['git', '-C', str(repo_root), 'status', '--porcelain'],
            repo_root,
            15,
            env
        )
        if error:
            return error
        if not (status_result.stdout or '').strip():
            return {'error': '커밋할 변경 사항이 없습니다.'}

        add_result, error = _run_git_command(
            ['git', '-C', str(repo_root), 'add', '-A'],
            repo_root,
            30,
            env
        )
        if error:
            return error
        if add_result.returncode != 0:
            stdout = (add_result.stdout or '').strip()
            stderr = (add_result.stderr or '').strip()
            return {'error': stderr or stdout or 'git add에 실패했습니다.'}

        message = _build_commit_message()
        result, error = _run_git_command(
            ['git', '-C', str(repo_root), 'commit', '-m', message],
            repo_root,
            GIT_TIMEOUT_SECONDS,
            env
        )
        if error:
            return error
    else:
        cmd = _GIT_ACTIONS[action]
        result, error = _run_git_command(cmd, repo_root, GIT_TIMEOUT_SECONDS, env)
        if error:
            return error

    duration_ms = max(0, int((time.time() - started_at) * 1000))
    stdout = (result.stdout or '').strip()
    stderr = (result.stderr or '').strip()
    return {
        'ok': result.returncode == 0,
        'exit_code': result.returncode,
        'stdout': stdout,
        'stderr': stderr,
        'command': ' '.join(cmd),
        'repo_root': str(repo_root),
        'duration_ms': duration_ms
    }
