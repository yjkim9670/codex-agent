"""Git command helpers for Codex Agent."""

import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from ..config import REPO_ROOT, WORKSPACE_DIR

GIT_TIMEOUT_SECONDS = 600
GIT_NETWORK_TIMEOUT_SECONDS = 180
_GIT_ACTIONS = {
    'sync': ['git', 'fetch', '--prune']
}
_GIT_MUTATION_ACTIONS = {'stage', 'commit', 'push', 'sync'}
_GIT_MUTATION_LOCK = threading.Lock()
_GIT_REPO_TARGET_WORKSPACE = 'workspace'
_GIT_REPO_TARGET_CODEX_AGENT = 'codex_agent'
_GIT_REPO_TARGET_ALIASES = {
    _GIT_REPO_TARGET_WORKSPACE: _GIT_REPO_TARGET_WORKSPACE,
    'default': _GIT_REPO_TARGET_WORKSPACE,
    _GIT_REPO_TARGET_CODEX_AGENT: _GIT_REPO_TARGET_CODEX_AGENT,
    'codex-agent': _GIT_REPO_TARGET_CODEX_AGENT,
    'codex': _GIT_REPO_TARGET_CODEX_AGENT,
    'agent': _GIT_REPO_TARGET_CODEX_AGENT
}


def _normalize_repo_target(value):
    target = str(value or '').strip().lower()
    if not target:
        return _GIT_REPO_TARGET_WORKSPACE
    return _GIT_REPO_TARGET_ALIASES.get(target, _GIT_REPO_TARGET_WORKSPACE)


def _resolve_repo_root(repo_target=_GIT_REPO_TARGET_WORKSPACE):
    normalized_target = _normalize_repo_target(repo_target)
    if normalized_target == _GIT_REPO_TARGET_CODEX_AGENT:
        repo_base = REPO_ROOT
        repo_label = 'Codex Agent 저장소'
    else:
        repo_base = WORKSPACE_DIR
        repo_label = '워크스페이스 저장소'
    if not repo_base.exists():
        return None, f'{repo_label} 경로를 찾을 수 없습니다: {repo_base}'
    try:
        result = subprocess.run(
            ['git', '-C', str(repo_base), 'rev-parse', '--show-toplevel'],
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
        return None, stderr or stdout or f'{repo_label}를 찾을 수 없습니다.'

    repo_root = Path((result.stdout or '').strip())
    if not repo_root.exists():
        return None, 'git 저장소 경로를 확인할 수 없습니다.'
    return repo_root, None


def _run_git_command(cmd, repo_root, timeout, env):
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            stdin=subprocess.DEVNULL,
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
    repo_root, error = _resolve_repo_root(_GIT_REPO_TARGET_WORKSPACE)
    if error:
        return ''
    env = os.environ.copy()
    env.setdefault('GIT_TERMINAL_PROMPT', '0')
    return _read_current_branch(repo_root, env)


def _is_history_file(path):
    base = os.path.basename(path or '').lower()
    return base == 'history' or base.startswith('history.')


def _normalize_status_marker(status_code):
    code = (status_code or '').strip()
    if not code:
        return ''
    if code == '??':
        return 'U'
    if 'U' in code:
        return 'U'
    if 'D' in code:
        return 'D'
    if 'A' in code:
        return 'A'
    if 'R' in code:
        return 'R'
    if 'C' in code:
        return 'C'
    if 'M' in code:
        return 'M'
    if 'T' in code:
        return 'T'
    return code[0]


def _extract_changed_file_details(status_text):
    entries = []
    for line in (status_text or '').splitlines():
        if len(line) < 4:
            continue
        status_code = line[:2]
        path = line[3:].strip()
        if not path:
            continue
        if ' -> ' in path:
            path = path.split(' -> ')[-1].strip()
        if not path:
            continue
        entries.append({
            'path': path,
            'status': _normalize_status_marker(status_code)
        })
    return entries


def _extract_changed_files(status_text):
    return [entry['path'] for entry in _extract_changed_file_details(status_text)]


def _extract_name_status_details(status_text):
    entries = []
    for line in (status_text or '').splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split('\t')
        if len(parts) < 2:
            continue
        status_code = parts[0].strip()
        path = parts[-1].strip()
        if not path:
            continue
        if ' -> ' in path:
            path = path.split(' -> ')[-1].strip()
        if not path:
            continue
        entries.append({
            'path': path,
            'status': _normalize_status_marker(status_code)
        })
    return entries


def _build_commit_message(status_text, max_files=3):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    files = [path for path in _extract_changed_files(status_text) if not _is_history_file(path)]
    if not files:
        return timestamp
    listed = files[:max_files]
    suffix = f" (+{len(files) - max_files})" if len(files) > max_files else ''
    return f"{timestamp} {', '.join(listed)}{suffix}"


def _normalize_selected_files(value):
    if not isinstance(value, list):
        return []
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        path = item.strip().replace('\\', '/')
        if not path:
            continue
        while path.startswith('./'):
            path = path[2:]
        if not path or path.startswith('/') or path.startswith('../') or '/..' in path:
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def _read_changed_snapshot(repo_root, env):
    status_result, status_error = _run_git_command(
        ['git', '-C', str(repo_root), 'status', '--porcelain'],
        repo_root,
        15,
        env
    )
    if status_error or not status_result or status_result.returncode != 0:
        return [], []
    changed_files_detail = _extract_changed_file_details(status_result.stdout or '')
    changed_files = [entry['path'] for entry in changed_files_detail]
    return changed_files_detail, changed_files


def _read_staged_snapshot(repo_root, env):
    staged_result, staged_error = _run_git_command(
        ['git', '-C', str(repo_root), 'diff', '--cached', '--name-status'],
        repo_root,
        15,
        env
    )
    if staged_error or not staged_result or staged_result.returncode != 0:
        return [], []
    staged_files_detail = _extract_name_status_details(staged_result.stdout or '')
    staged_files = [entry['path'] for entry in staged_files_detail]
    return staged_files_detail, staged_files


def _build_result(
    repo_root,
    env,
    started_at,
    command='',
    exit_code=0,
    stdout='',
    stderr='',
    extra=None
):
    changed_files_detail, changed_files = _read_changed_snapshot(repo_root, env)
    staged_files_detail, staged_files = _read_staged_snapshot(repo_root, env)
    branch_name = _read_current_branch(repo_root, env)
    payload = {
        'ok': exit_code == 0,
        'exit_code': exit_code,
        'stdout': (stdout or '').strip(),
        'stderr': (stderr or '').strip(),
        'branch': branch_name,
        'changed_files_count': len(changed_files),
        'changed_files': changed_files,
        'changed_files_detail': changed_files_detail,
        'staged_files_count': len(staged_files),
        'staged_files': staged_files,
        'staged_files_detail': staged_files_detail,
        'command': command,
        'repo_root': str(repo_root),
        'duration_ms': max(0, int((time.time() - started_at) * 1000))
    }
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _run_checked(cmd, repo_root, env, timeout, fallback_error):
    result, error = _run_git_command(cmd, repo_root, timeout, env)
    if error:
        return None, error
    if not result:
        return None, {'error': fallback_error}
    if result.returncode != 0:
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        return None, {'error': stderr or stdout or fallback_error}
    return result, None


def _resolve_push_command(repo_root, env):
    upstream = _read_upstream_branch(repo_root, env)
    if upstream:
        return ['git', '-C', str(repo_root), 'push'], None
    branch_name = _read_current_branch_for_push(repo_root, env)
    if not branch_name:
        return None, {'error': '현재 브랜치를 확인할 수 없습니다. (detached HEAD일 수 있습니다.)'}
    remote_name = _pick_remote(repo_root, env)
    if not remote_name:
        return None, {'error': '원격 저장소를 찾을 수 없습니다.'}
    return ['git', '-C', str(repo_root), 'push', '-u', remote_name, branch_name], None


def run_git_action(action, payload=None):
    try:
        action = (action or '').strip().lower()
        payload = payload if isinstance(payload, dict) else {}
        if action not in {'status', 'stage', 'commit', 'push', 'sync', 'submit'}:
            return {'error': '지원하지 않는 git 작업입니다.'}
        if action == 'submit':
            return {'error': 'submit 작업은 비활성화되었습니다. stage -> commit -> push 순서로 실행해주세요.'}

        repo_target = _normalize_repo_target(payload.get('repo_target'))
        repo_root, error = _resolve_repo_root(repo_target)
        if error:
            return {'error': error}

        env = os.environ.copy()
        env.setdefault('GIT_TERMINAL_PROMPT', '0')
        env.setdefault('GCM_INTERACTIVE', 'never')
        started_at = time.time()
        lock_acquired = False
        if action in _GIT_MUTATION_ACTIONS:
            lock_acquired = _GIT_MUTATION_LOCK.acquire(blocking=False)
            if not lock_acquired:
                return {'error': '다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.'}

        try:
            if action == 'status':
                result, error = _run_checked(
                    ['git', '-C', str(repo_root), 'status', '--porcelain'],
                    repo_root,
                    env,
                    15,
                    'git status를 확인하지 못했습니다.'
                )
                if error:
                    return error
                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command='git status --porcelain',
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    extra={'repo_target': repo_target}
                )

            if action == 'sync':
                fetch_cmd = _GIT_ACTIONS['sync']
                result, error = _run_checked(
                    fetch_cmd,
                    repo_root,
                    env,
                    GIT_NETWORK_TIMEOUT_SECONDS,
                    'git fetch에 실패했습니다.'
                )
                if error:
                    return error
                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command=' '.join(fetch_cmd),
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    extra={'repo_target': repo_target}
                )

            if action == 'stage':
                selected_files = _normalize_selected_files(payload.get('files'))
                if not selected_files:
                    return {'error': '스테이징할 파일을 선택해주세요.'}

                replace_index = payload.get('replace')
                if replace_index is None:
                    replace_index = True
                replace_index = bool(replace_index)

                if replace_index:
                    reset_result, error = _run_checked(
                        ['git', '-C', str(repo_root), 'reset'],
                        repo_root,
                        env,
                        30,
                        'git 인덱스 초기화에 실패했습니다.'
                    )
                    if error:
                        return error
                    reset_stdout = (reset_result.stdout or '').strip()
                    reset_stderr = (reset_result.stderr or '').strip()
                else:
                    reset_stdout = ''
                    reset_stderr = ''

                add_cmd = ['git', '-C', str(repo_root), 'add', '--', *selected_files]
                add_result, error = _run_checked(
                    add_cmd,
                    repo_root,
                    env,
                    60,
                    'git add에 실패했습니다.'
                )
                if error:
                    return error
                combined_stdout = '\n'.join(
                    item for item in [reset_stdout, (add_result.stdout or '').strip()] if item
                )
                combined_stderr = '\n'.join(
                    item for item in [reset_stderr, (add_result.stderr or '').strip()] if item
                )
                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command='git reset && git add -- <selected files>' if replace_index else 'git add -- <selected files>',
                    exit_code=add_result.returncode,
                    stdout=combined_stdout,
                    stderr=combined_stderr,
                    extra={
                        'selected_files_count': len(selected_files),
                        'selected_files': selected_files,
                        'repo_target': repo_target
                    }
                )

            if action == 'commit':
                staged_files_detail, _ = _read_staged_snapshot(repo_root, env)
                if not staged_files_detail:
                    return {'error': '스테이징된 변경 사항이 없습니다. 먼저 stage를 실행해주세요.'}

                commit_message = str(payload.get('message') or '').strip()
                if not commit_message:
                    synthetic_status = '\n'.join(
                        f"M  {entry['path']}" for entry in staged_files_detail if entry.get('path')
                    )
                    commit_message = _build_commit_message(synthetic_status)

                commit_cmd = ['git', '-C', str(repo_root), 'commit', '-m', commit_message]
                commit_result, error = _run_checked(
                    commit_cmd,
                    repo_root,
                    env,
                    GIT_TIMEOUT_SECONDS,
                    'git commit에 실패했습니다.'
                )
                if error:
                    return error

                head_result, head_error = _run_git_command(
                    ['git', '-C', str(repo_root), 'rev-parse', '--short', 'HEAD'],
                    repo_root,
                    10,
                    env
                )
                commit_hash = ''
                if not head_error and head_result and head_result.returncode == 0:
                    commit_hash = (head_result.stdout or '').strip()

                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command='git commit -m <message>',
                    exit_code=commit_result.returncode,
                    stdout=commit_result.stdout,
                    stderr=commit_result.stderr,
                    extra={
                        'commit_message': commit_message,
                        'commit_hash': commit_hash,
                        'repo_target': repo_target
                    }
                )

            if action == 'push':
                if payload.get('confirm') is not True:
                    return {'error': 'push 실행 전 confirm=true가 필요합니다.'}
                push_cmd, push_error = _resolve_push_command(repo_root, env)
                if push_error:
                    return push_error
                push_result, error = _run_checked(
                    push_cmd,
                    repo_root,
                    env,
                    GIT_NETWORK_TIMEOUT_SECONDS,
                    'git push에 실패했습니다.'
                )
                if error:
                    return error

                fetch_cmd = _GIT_ACTIONS['sync']
                fetch_result, fetch_exec_error = _run_git_command(
                    fetch_cmd,
                    repo_root,
                    GIT_NETWORK_TIMEOUT_SECONDS,
                    env
                )
                post_fetch_ok = False
                post_fetch_stdout = ''
                post_fetch_stderr = ''
                post_fetch_error = ''
                post_fetch_exit_code = -1
                if fetch_exec_error:
                    post_fetch_error = fetch_exec_error.get('error') or 'post-fetch 실행에 실패했습니다.'
                elif not fetch_result:
                    post_fetch_error = 'post-fetch 결과를 확인할 수 없습니다.'
                else:
                    post_fetch_stdout = (fetch_result.stdout or '').strip()
                    post_fetch_stderr = (fetch_result.stderr or '').strip()
                    post_fetch_exit_code = int(fetch_result.returncode)
                    if fetch_result.returncode == 0:
                        post_fetch_ok = True
                    else:
                        post_fetch_error = post_fetch_stderr or post_fetch_stdout or 'post-fetch에 실패했습니다.'

                push_stdout = (push_result.stdout or '').strip()
                push_stderr = (push_result.stderr or '').strip()
                combined_stdout = '\n'.join(item for item in [push_stdout, post_fetch_stdout] if item)
                combined_stderr = '\n'.join(
                    item for item in [
                        push_stderr,
                        post_fetch_stderr,
                        f'post-fetch error: {post_fetch_error}' if post_fetch_error else ''
                    ] if item
                )
                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command=f"{' '.join(push_cmd)} && {' '.join(fetch_cmd)}",
                    exit_code=push_result.returncode,
                    stdout=combined_stdout,
                    stderr=combined_stderr,
                    extra={
                        'repo_target': repo_target,
                        'post_fetch_ok': post_fetch_ok,
                        'post_fetch_exit_code': post_fetch_exit_code,
                        'post_fetch_stdout': post_fetch_stdout,
                        'post_fetch_stderr': post_fetch_stderr,
                        'post_fetch_error': post_fetch_error
                    }
                )

            return {'error': '지원하지 않는 git 작업입니다.'}
        finally:
            if lock_acquired:
                _GIT_MUTATION_LOCK.release()
    except Exception as exc:
        return {'error': f'git 작업 처리 중 오류가 발생했습니다: {exc}'}
