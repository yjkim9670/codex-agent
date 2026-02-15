"""Git command helpers for Codex Agent."""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from ..config import WORKSPACE_DIR

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


def _read_current_branch(repo_root, env):
    symbolic_result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'symbolic-ref', '--short', 'HEAD'],
        repo_root,
        10,
        env
    )
    if not error and symbolic_result and symbolic_result.returncode == 0:
        branch_name = (symbolic_result.stdout or '').strip()
        if branch_name:
            return branch_name

    commit_result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--short', 'HEAD'],
        repo_root,
        10,
        env
    )
    if error or not commit_result or commit_result.returncode != 0:
        return ''
    commit_short = (commit_result.stdout or '').strip()
    if not commit_short:
        return ''
    return f'detached@{commit_short}'


def _read_current_branch_for_push(repo_root, env):
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--abbrev-ref', 'HEAD'],
        repo_root,
        10,
        env
    )
    if error or not result or result.returncode != 0:
        return ''
    branch = (result.stdout or '').strip()
    if not branch or branch == 'HEAD':
        return ''
    return branch


def _read_upstream_branch(repo_root, env):
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
        repo_root,
        10,
        env
    )
    if error or not result or result.returncode != 0:
        return ''
    return (result.stdout or '').strip()


def _pick_remote(repo_root, env):
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'remote'],
        repo_root,
        10,
        env
    )
    if error or not result or result.returncode != 0:
        return ''
    remotes = [name.strip() for name in (result.stdout or '').splitlines() if name.strip()]
    if not remotes:
        return ''
    if 'origin' in remotes:
        return 'origin'
    return remotes[0]


def get_current_branch_name():
    repo_root, error = _resolve_repo_root()
    if error:
        return ''
    env = os.environ.copy()
    env.setdefault('GIT_TERMINAL_PROMPT', '0')
    return _read_current_branch(repo_root, env)


def _is_history_file(path):
    base = os.path.basename(path or '').lower()
    return base == 'history' or base.startswith('history.')


def _extract_changed_files(status_text):
    files = []
    for line in (status_text or '').splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if not path:
            continue
        if ' -> ' in path:
            path = path.split(' -> ')[-1].strip()
        if not path:
            continue
        files.append(path)
    return files


def _build_commit_message(status_text, max_files=3):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    files = [path for path in _extract_changed_files(status_text) if not _is_history_file(path)]
    if not files:
        return timestamp
    listed = files[:max_files]
    suffix = f" (+{len(files) - max_files})" if len(files) > max_files else ''
    return f"{timestamp} {', '.join(listed)}{suffix}"


def run_git_action(action):
    try:
        action = (action or '').strip()
        if action not in _GIT_ACTIONS and action not in {'submit', 'status'}:
            return {'error': '지원하지 않는 git 작업입니다.'}

        repo_root, error = _resolve_repo_root()
        if error:
            return {'error': error}

        env = os.environ.copy()
        env.setdefault('GIT_TERMINAL_PROMPT', '0')

        started_at = time.time()
        cmd = None
        preserve_output = False
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

            message = _build_commit_message(status_result.stdout or '')
            result, error = _run_git_command(
                ['git', '-C', str(repo_root), 'commit', '-m', message],
                repo_root,
                GIT_TIMEOUT_SECONDS,
                env
            )
            if error:
                return error
            if result.returncode != 0:
                stdout = (result.stdout or '').strip()
                stderr = (result.stderr or '').strip()
                return {'error': stderr or stdout or 'git commit에 실패했습니다.'}

            upstream = _read_upstream_branch(repo_root, env)
            if upstream:
                push_cmd = ['git', '-C', str(repo_root), 'push']
            else:
                branch_name = _read_current_branch_for_push(repo_root, env)
                if not branch_name:
                    return {'error': '현재 브랜치를 확인할 수 없습니다. (detached HEAD일 수 있습니다.)'}
                remote_name = _pick_remote(repo_root, env)
                if not remote_name:
                    return {'error': '원격 저장소를 찾을 수 없습니다.'}
                push_cmd = ['git', '-C', str(repo_root), 'push', '-u', remote_name, branch_name]

            cmd = push_cmd
            push_result, error = _run_git_command(
                push_cmd,
                repo_root,
                GIT_TIMEOUT_SECONDS,
                env
            )
            if error:
                return error
            if push_result.returncode != 0:
                stdout = (push_result.stdout or '').strip()
                stderr = (push_result.stderr or '').strip()
                return {'error': stderr or stdout or 'git push에 실패했습니다.'}

            cmd = ['git', 'commit', '&&', 'git', 'push']
            stdout = '\n'.join([
                (result.stdout or '').strip(),
                (push_result.stdout or '').strip()
            ]).strip()
            stderr = '\n'.join([
                (result.stderr or '').strip(),
                (push_result.stderr or '').strip()
            ]).strip()
            result = push_result
            preserve_output = True
        else:
            if action == 'sync':
                fetch_cmd = _GIT_ACTIONS[action]
                cmd = fetch_cmd
                fetch_result, error = _run_git_command(fetch_cmd, repo_root, GIT_TIMEOUT_SECONDS, env)
                if error:
                    return error
                if fetch_result.returncode != 0:
                    stdout = (fetch_result.stdout or '').strip()
                    stderr = (fetch_result.stderr or '').strip()
                    return {'error': stderr or stdout or 'git fetch에 실패했습니다.'}
                push_cmd = ['git', 'push']
                cmd = push_cmd
                push_result, error = _run_git_command(push_cmd, repo_root, GIT_TIMEOUT_SECONDS, env)
                if error:
                    return error
                if push_result.returncode != 0:
                    stdout = (push_result.stdout or '').strip()
                    stderr = (push_result.stderr or '').strip()
                    return {'error': stderr or stdout or 'git push에 실패했습니다.'}
                result = push_result
                cmd = ['git', 'fetch', '--prune', '&&', 'git', 'push']
                stdout = '\n'.join([
                    (fetch_result.stdout or '').strip(),
                    (push_result.stdout or '').strip()
                ]).strip()
                stderr = '\n'.join([
                    (fetch_result.stderr or '').strip(),
                    (push_result.stderr or '').strip()
                ]).strip()
            elif action == 'status':
                cmd = ['git', 'status', '--porcelain']
                result, error = _run_git_command(cmd, repo_root, 15, env)
                if error:
                    return error
            else:
                cmd = _GIT_ACTIONS[action]
                result, error = _run_git_command(cmd, repo_root, GIT_TIMEOUT_SECONDS, env)
                if error:
                    return error

        duration_ms = max(0, int((time.time() - started_at) * 1000))
        if action != 'sync' and not preserve_output:
            stdout = (result.stdout or '').strip()
            stderr = (result.stderr or '').strip()
        status_result, status_error = _run_git_command(
            ['git', '-C', str(repo_root), 'status', '--porcelain'],
            repo_root,
            15,
            env
        )
        changed_files = []
        if not status_error and status_result and status_result.returncode == 0:
            changed_files = _extract_changed_files(status_result.stdout or '')
        branch_name = _read_current_branch(repo_root, env)
        return {
            'ok': result.returncode == 0,
            'exit_code': result.returncode,
            'stdout': stdout,
            'stderr': stderr,
            'branch': branch_name,
            'changed_files_count': len(changed_files),
            'changed_files': changed_files,
            'command': ' '.join(cmd) if cmd else '',
            'repo_root': str(repo_root),
            'duration_ms': duration_ms
        }
    except Exception as exc:
        return {'error': f'git 작업 처리 중 오류가 발생했습니다: {exc}'}
