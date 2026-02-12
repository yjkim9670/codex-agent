"""Git command helpers for Codex Agent."""

import os
import re
import subprocess
import time
from pathlib import Path

from ..config import WORKSPACE_DIR
from .codex_chat import get_session, list_sessions

GIT_TIMEOUT_SECONDS = 600
_GIT_ACTIONS = {
    'sync': ['git', 'fetch', '--prune']
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


def _normalize_summary_text(text):
    if not text:
        return ''
    cleaned = re.sub(r'```.*?```', ' ', str(text), flags=re.DOTALL)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.replace('`', '').strip()
    return cleaned


def _summarize_recent_conversation(messages):
    if not isinstance(messages, list) or not messages:
        return ''
    last_user = None
    last_assistant = None
    for entry in reversed(messages):
        role = entry.get('role')
        content = _normalize_summary_text(entry.get('content') or '')
        if not content:
            continue
        if not last_user and role == 'user':
            last_user = content
        if not last_assistant and role == 'assistant':
            last_assistant = content
        if last_user and last_assistant:
            break
    if last_user and last_assistant:
        summary = f"{last_user} / {last_assistant}"
    else:
        summary = last_user or last_assistant or ''
    return summary


def _build_commit_summary():
    sessions = list_sessions()
    if not sessions:
        return ''
    session_id = sessions[0].get('id')
    if not session_id:
        return ''
    session = get_session(session_id)
    if not session:
        return ''
    return _summarize_recent_conversation(session.get('messages', []))


def _build_commit_message():
    try:
        summary = _build_commit_summary()
        if not summary:
            sessions = list_sessions()
            summary = sessions[0].get('title') if sessions else ''
        return _sanitize_commit_title(summary)
    except Exception:
        return _sanitize_commit_title('')


def run_git_action(action):
    try:
        action = (action or '').strip()
        if action not in _GIT_ACTIONS and action != 'submit':
            return {'error': '지원하지 않는 git 작업입니다.'}

        repo_root, error = _resolve_repo_root()
        if error:
            return {'error': error}

        env = os.environ.copy()
        env.setdefault('GIT_TERMINAL_PROMPT', '0')

        started_at = time.time()
        cmd = None
        if action == 'submit':
            cmd = ['git', 'commit']
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
            cmd = ['git', 'commit', '-m', message]
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
            'command': ' '.join(cmd) if cmd else '',
            'repo_root': str(repo_root),
            'duration_ms': duration_ms
        }
    except Exception as exc:
        return {'error': f'git 작업 처리 중 오류가 발생했습니다: {exc}'}
