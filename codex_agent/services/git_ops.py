"""Git command helpers for Codex Agent."""

import os
import subprocess
import time
from pathlib import Path

from ..config import WORKSPACE_DIR

GIT_TIMEOUT_SECONDS = 600
_GIT_ACTIONS = {
    'submit': ['git', 'submit'],
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


def run_git_action(action):
    action = (action or '').strip()
    if action not in _GIT_ACTIONS:
        return {'error': '지원하지 않는 git 작업입니다.'}

    repo_root, error = _resolve_repo_root()
    if error:
        return {'error': error}

    cmd = _GIT_ACTIONS[action]
    env = os.environ.copy()
    env.setdefault('GIT_TERMINAL_PROMPT', '0')

    started_at = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            env=env
        )
    except FileNotFoundError:
        return {'error': 'git 명령을 찾을 수 없습니다.'}
    except subprocess.TimeoutExpired:
        return {'error': 'git 작업 시간이 초과되었습니다.'}
    except Exception as exc:
        return {'error': f'git 실행 중 오류가 발생했습니다: {exc}'}

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
