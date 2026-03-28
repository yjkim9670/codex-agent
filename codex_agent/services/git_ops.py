"""Git command helpers for Codex Agent."""

from collections import Counter
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
_GIT_MUTATION_LOCKS = {
    _GIT_REPO_TARGET_WORKSPACE: threading.Lock(),
    _GIT_REPO_TARGET_CODEX_AGENT: threading.Lock()
}
_GIT_MUTATION_STATE_LOCK = threading.Lock()
_GIT_ACTIVE_MUTATIONS = {}


def _normalize_repo_target(value):
    target = str(value or '').strip().lower()
    if not target:
        return _GIT_REPO_TARGET_WORKSPACE
    return _GIT_REPO_TARGET_ALIASES.get(target, _GIT_REPO_TARGET_WORKSPACE)


def _get_mutation_lock(repo_target):
    target = _normalize_repo_target(repo_target)
    with _GIT_MUTATION_STATE_LOCK:
        lock = _GIT_MUTATION_LOCKS.get(target)
        if not lock:
            lock = threading.Lock()
            _GIT_MUTATION_LOCKS[target] = lock
    return lock


def _register_active_mutation(repo_target, action):
    target = _normalize_repo_target(repo_target)
    state = {
        'repo_target': target,
        'action': str(action or '').strip() or 'unknown',
        'started_at': time.time(),
        'cancel_event': threading.Event(),
        'process': None
    }
    with _GIT_MUTATION_STATE_LOCK:
        _GIT_ACTIVE_MUTATIONS[target] = state
    return state


def _set_active_mutation_process(state, process):
    if not state:
        return
    target = _normalize_repo_target(state.get('repo_target'))
    with _GIT_MUTATION_STATE_LOCK:
        current = _GIT_ACTIVE_MUTATIONS.get(target)
        if current is state:
            state['process'] = process


def _clear_active_mutation(repo_target, state=None):
    target = _normalize_repo_target(repo_target)
    with _GIT_MUTATION_STATE_LOCK:
        current = _GIT_ACTIVE_MUTATIONS.get(target)
        if not current:
            return
        if state is None or current is state:
            _GIT_ACTIVE_MUTATIONS.pop(target, None)


def _get_active_mutation_summary(repo_target):
    target = _normalize_repo_target(repo_target)
    with _GIT_MUTATION_STATE_LOCK:
        state = _GIT_ACTIVE_MUTATIONS.get(target)
        if not state:
            return None
        action = str(state.get('action') or '').strip() or 'unknown'
        started_at = float(state.get('started_at') or time.time())
    elapsed_seconds = max(0, int(time.time() - started_at))
    return {
        'repo_target': target,
        'action': action,
        'elapsed_seconds': elapsed_seconds
    }


def _terminate_process(process):
    if not process:
        return
    try:
        if process.poll() is not None:
            return
    except Exception:
        return
    try:
        process.terminate()
        process.wait(timeout=1)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=1)
        except Exception:
            pass


def _request_cancel_active_mutation(repo_target):
    target = _normalize_repo_target(repo_target)
    process = None
    action = ''
    started_at = time.time()
    with _GIT_MUTATION_STATE_LOCK:
        state = _GIT_ACTIVE_MUTATIONS.get(target)
        if not state:
            return {
                'repo_target': target,
                'cancel_requested': False,
                'cancelled_action': '',
                'active_elapsed_seconds': 0
            }
        cancel_event = state.get('cancel_event')
        if cancel_event:
            cancel_event.set()
        process = state.get('process')
        action = str(state.get('action') or '').strip()
        started_at = float(state.get('started_at') or time.time())
    elapsed_seconds = max(0, int(time.time() - started_at))
    _terminate_process(process)
    return {
        'repo_target': target,
        'cancel_requested': True,
        'cancelled_action': action,
        'active_elapsed_seconds': elapsed_seconds
    }


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


def _run_git_command(cmd, repo_root, timeout, env, cancel_event=None, mutation_state=None):
    process = None
    started_at = time.time()
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        _set_active_mutation_process(mutation_state, process)
        while True:
            if cancel_event and cancel_event.is_set():
                _terminate_process(process)
                stdout, stderr = process.communicate()
                return None, {
                    'error': '요청이 취소되어 git 작업을 중단했습니다.',
                    'error_code': 'git_cancelled',
                    'cancelled': True,
                    'stdout': (stdout or '').strip(),
                    'stderr': (stderr or '').strip()
                }
            if timeout and time.time() - started_at > timeout:
                _terminate_process(process)
                stdout, stderr = process.communicate()
                return None, {
                    'error': 'git 작업 시간이 초과되었습니다.',
                    'error_code': 'git_timeout',
                    'timeout': True,
                    'stdout': (stdout or '').strip(),
                    'stderr': (stderr or '').strip()
                }
            returncode = process.poll()
            if returncode is not None:
                stdout, stderr = process.communicate()
                result = subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
                return result, None
            time.sleep(0.1)
    except FileNotFoundError:
        return None, {'error': 'git 명령을 찾을 수 없습니다.', 'error_code': 'git_not_found'}
    except Exception as exc:
        return None, {'error': f'git 실행 중 오류가 발생했습니다: {exc}', 'error_code': 'git_exec_error'}
    finally:
        _set_active_mutation_process(mutation_state, None)


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


def _list_remotes(repo_root, env):
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'remote'],
        repo_root,
        10,
        env
    )
    if error or not result or result.returncode != 0:
        return []
    return [name.strip() for name in (result.stdout or '').splitlines() if name.strip()]


def _pick_remote(repo_root, env):
    remotes = _list_remotes(repo_root, env)
    if not remotes:
        return ''
    if 'origin' in remotes:
        return 'origin'
    return remotes[0]


def _normalize_remote_name(repo_root, env, remote_name=''):
    requested = str(remote_name or '').strip()
    remotes = _list_remotes(repo_root, env)
    if not remotes:
        return ''
    if requested and requested in remotes:
        return requested
    if requested and requested not in remotes:
        return _pick_remote(repo_root, env)
    return _pick_remote(repo_root, env)


def _ref_exists(repo_root, env, ref_name):
    ref = str(ref_name or '').strip()
    if not ref:
        return False
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'rev-parse', '--verify', '--quiet', ref],
        repo_root,
        10,
        env
    )
    return not error and bool(result) and result.returncode == 0


def _read_local_remote_head_branch(repo_root, env, remote_name):
    remote = str(remote_name or '').strip()
    if not remote:
        return ''
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'symbolic-ref', '--quiet', '--short', f'refs/remotes/{remote}/HEAD'],
        repo_root,
        10,
        env
    )
    if error or not result or result.returncode != 0:
        return ''
    value = (result.stdout or '').strip()
    prefix = f'{remote}/'
    if value.startswith(prefix):
        return value[len(prefix):].strip()
    return ''


def _read_network_remote_head_branch(repo_root, env, remote_name):
    remote = str(remote_name or '').strip()
    if not remote:
        return ''
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'ls-remote', '--symref', remote, 'HEAD'],
        repo_root,
        20,
        env
    )
    if error or not result or result.returncode != 0:
        return ''
    for line in (result.stdout or '').splitlines():
        stripped = line.strip()
        if not stripped.startswith('ref:'):
            continue
        # Example: ref: refs/heads/main  HEAD
        parts = stripped.split()
        if len(parts) < 2:
            continue
        ref_name = parts[1].strip()
        prefix = 'refs/heads/'
        if ref_name.startswith(prefix):
            branch = ref_name[len(prefix):].strip()
            if branch:
                return branch
    return ''


def _remote_branch_exists(repo_root, env, remote_name, branch_name):
    remote = str(remote_name or '').strip()
    branch = str(branch_name or '').strip()
    if not remote or not branch:
        return None
    if _ref_exists(repo_root, env, f'{remote}/{branch}'):
        return True
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'ls-remote', '--heads', remote, branch],
        repo_root,
        20,
        env
    )
    if error or not result or result.returncode != 0:
        return None
    return bool((result.stdout or '').strip())


def _resolve_remote_branch(repo_root, env, remote_name, preferred_branch=''):
    remote = _normalize_remote_name(repo_root, env, remote_name)
    if not remote:
        return '', '', False

    preferred = str(preferred_branch or '').strip()
    if preferred:
        preferred_exists = _remote_branch_exists(repo_root, env, remote, preferred)
        if preferred_exists is True:
            return remote, preferred, False

    local_head_branch = _read_local_remote_head_branch(repo_root, env, remote)
    if local_head_branch:
        fallback_used = bool(preferred and local_head_branch != preferred)
        return remote, local_head_branch, fallback_used

    network_head_branch = _read_network_remote_head_branch(repo_root, env, remote)
    if network_head_branch:
        fallback_used = bool(preferred and network_head_branch != preferred)
        return remote, network_head_branch, fallback_used

    # Common fallback when remote default is still "master".
    for candidate in ('main', 'master'):
        exists = _remote_branch_exists(repo_root, env, remote, candidate)
        if exists is True:
            fallback_used = bool(preferred and candidate != preferred)
            return remote, candidate, fallback_used

    # If existence cannot be determined, keep caller preference.
    if preferred:
        return remote, preferred, False
    return remote, '', False


def _read_commit_history(repo_root, env, ref_name='HEAD', max_count=20):
    ref = str(ref_name or '').strip()
    if not ref:
        return [], {'error': '히스토리 조회 기준 브랜치가 비어 있습니다.'}
    try:
        count = int(max_count)
    except (TypeError, ValueError):
        count = 20
    count = max(1, min(100, count))
    pretty = '--pretty=format:%H%x1f%h%x1f%ad%x1f%an%x1f%s'
    cmd = [
        'git', '-C', str(repo_root), 'log',
        f'--max-count={count}',
        '--date=iso-strict',
        pretty,
        ref,
        '--'
    ]
    result, error = _run_git_command(cmd, repo_root, 20, env)
    if error:
        return [], error
    if not result or result.returncode != 0:
        message = (result.stderr or result.stdout or '').strip() if result else ''
        return [], {'error': message or f'{ref} 이력을 불러오지 못했습니다.'}
    history = []
    for line in (result.stdout or '').splitlines():
        parts = line.split('\x1f')
        if len(parts) < 5:
            continue
        history.append({
            'commit_hash': parts[0].strip(),
            'short_hash': parts[1].strip(),
            'committed_at': parts[2].strip(),
            'author': parts[3].strip(),
            'subject': parts[4].strip()
        })
    return history, None


def _read_divergence_counts(repo_root, env, left_ref, right_ref):
    left = str(left_ref or '').strip()
    right = str(right_ref or '').strip()
    if not left or not right:
        return None, None
    cmd = ['git', '-C', str(repo_root), 'rev-list', '--left-right', '--count', f'{left}...{right}']
    result, error = _run_git_command(cmd, repo_root, 10, env)
    if error or not result or result.returncode != 0:
        return None, None
    parts = (result.stdout or '').strip().split()
    if len(parts) != 2:
        return None, None
    try:
        ahead = max(0, int(parts[0]))
        behind = max(0, int(parts[1]))
    except ValueError:
        return None, None
    return ahead, behind


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


def _is_test_path(path):
    normalized = str(path or '').strip().replace('\\', '/').lower()
    if not normalized:
        return False
    base = os.path.basename(normalized)
    if normalized.startswith('tests/') or '/tests/' in normalized or '/test/' in normalized:
        return True
    return (
        base.startswith('test_')
        or base.endswith('_test.py')
        or base.endswith('.test.js')
        or base.endswith('.test.jsx')
        or base.endswith('.test.ts')
        or base.endswith('.test.tsx')
        or base.endswith('.spec.js')
        or base.endswith('.spec.jsx')
        or base.endswith('.spec.ts')
        or base.endswith('.spec.tsx')
    )


def _is_doc_path(path):
    normalized = str(path or '').strip().replace('\\', '/').lower()
    if not normalized:
        return False
    if normalized.startswith('docs/') or '/docs/' in normalized:
        return True
    return normalized.endswith('.md') or normalized.endswith('.rst') or normalized.endswith('.txt')


def _is_config_path(path):
    normalized = str(path or '').strip().replace('\\', '/').lower()
    if not normalized:
        return False
    base = os.path.basename(normalized)
    config_names = {
        'pyproject.toml',
        'poetry.lock',
        'requirements.txt',
        'requirements-dev.txt',
        'setup.py',
        'setup.cfg',
        'tox.ini',
        'package.json',
        'package-lock.json',
        'pnpm-lock.yaml',
        'yarn.lock',
        '.gitignore',
        '.gitattributes',
        'dockerfile',
        'docker-compose.yml',
        'docker-compose.yaml',
        'makefile',
        '.env',
        '.env.example'
    }
    if base in config_names:
        return True
    return (
        normalized.endswith('.json')
        or normalized.endswith('.toml')
        or normalized.endswith('.yaml')
        or normalized.endswith('.yml')
        or normalized.endswith('.ini')
        or normalized.endswith('.cfg')
        or normalized.endswith('.conf')
    )


def _summarize_top_scopes(paths, max_items=3):
    scope_counter = Counter()
    for raw_path in paths:
        path = str(raw_path or '').strip().replace('\\', '/')
        if not path:
            continue
        segments = [segment for segment in path.split('/') if segment]
        if not segments:
            continue
        scope = '/'.join(segments[:2]) if len(segments) >= 2 else segments[0]
        scope_counter[scope] += 1
    ranked = sorted(scope_counter.items(), key=lambda item: (-item[1], item[0]))
    return [{'scope': scope, 'count': count} for scope, count in ranked[: max(1, int(max_items or 1))]]


def _summarize_status_counts(status_counts):
    if not isinstance(status_counts, dict):
        return ''
    labels = [
        ('M', '수정'),
        ('A', '추가'),
        ('D', '삭제'),
        ('R', '이동/이름변경'),
        ('C', '복사'),
        ('T', '타입변경'),
        ('U', '충돌')
    ]
    chunks = []
    for code, label in labels:
        try:
            count = int(status_counts.get(code) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            chunks.append(f'{label} {count}')
    return ', '.join(chunks)


def _parse_numstat_output(numstat_text):
    parsed = []
    insertions = 0
    deletions = 0
    binary_files = 0
    for line in (numstat_text or '').splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split('\t')
        if len(parts) < 3:
            continue
        add_raw = parts[0].strip()
        del_raw = parts[1].strip()
        path = parts[-1].strip()
        if not path:
            continue
        if ' -> ' in path:
            path = path.split(' -> ')[-1].strip()
        if not path:
            continue
        additions = int(add_raw) if add_raw.isdigit() else 0
        removed = int(del_raw) if del_raw.isdigit() else 0
        if add_raw == '-' or del_raw == '-':
            binary_files += 1
        insertions += additions
        deletions += removed
        parsed.append(
            {
                'path': path,
                'additions': additions,
                'deletions': removed,
                'line_changes': additions + removed
            }
        )
    return {
        'insertions': insertions,
        'deletions': deletions,
        'binary_files': binary_files,
        'file_stats': parsed
    }


def _analyze_staged_changes(repo_root, env, staged_files_detail):
    detail = staged_files_detail if isinstance(staged_files_detail, list) else []
    paths = []
    status_counter = Counter()
    for entry in detail:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get('path') or '').strip()
        status = str(entry.get('status') or '').strip()
        if not path:
            continue
        paths.append(path)
        if status:
            status_counter[status] += 1

    numstat_result, numstat_error = _run_git_command(
        ['git', '-C', str(repo_root), 'diff', '--cached', '--numstat'],
        repo_root,
        20,
        env
    )
    numstat = {
        'insertions': 0,
        'deletions': 0,
        'binary_files': 0,
        'file_stats': []
    }
    if not numstat_error and numstat_result and numstat_result.returncode == 0:
        numstat = _parse_numstat_output(numstat_result.stdout or '')

    top_files = sorted(
        numstat.get('file_stats') or [],
        key=lambda item: (-int(item.get('line_changes') or 0), str(item.get('path') or ''))
    )[:3]

    return {
        'total_files': len(paths),
        'status_counts': dict(status_counter),
        'insertions': int(numstat.get('insertions') or 0),
        'deletions': int(numstat.get('deletions') or 0),
        'binary_files': int(numstat.get('binary_files') or 0),
        'top_scopes': _summarize_top_scopes(paths, max_items=3),
        'top_files': top_files,
        'test_files': sum(1 for path in paths if _is_test_path(path)),
        'doc_files': sum(1 for path in paths if _is_doc_path(path)),
        'config_files': sum(1 for path in paths if _is_config_path(path))
    }


def _build_commit_analysis_lines(analysis):
    if not isinstance(analysis, dict):
        return []
    lines = []
    try:
        total_files = int(analysis.get('total_files') or 0)
    except (TypeError, ValueError):
        total_files = 0
    if total_files > 0:
        status_text = _summarize_status_counts(analysis.get('status_counts') or {})
        if status_text:
            lines.append(f'파일 변경: {total_files}개 ({status_text})')
        else:
            lines.append(f'파일 변경: {total_files}개')

    try:
        insertions = int(analysis.get('insertions') or 0)
    except (TypeError, ValueError):
        insertions = 0
    try:
        deletions = int(analysis.get('deletions') or 0)
    except (TypeError, ValueError):
        deletions = 0
    try:
        binary_files = int(analysis.get('binary_files') or 0)
    except (TypeError, ValueError):
        binary_files = 0
    if insertions > 0 or deletions > 0 or binary_files > 0:
        line = f'라인 변경: +{insertions} / -{deletions}'
        if binary_files > 0:
            line += f' (바이너리 {binary_files}개)'
        lines.append(line)

    top_scopes = analysis.get('top_scopes') if isinstance(analysis.get('top_scopes'), list) else []
    scope_chunks = []
    for item in top_scopes[:3]:
        if not isinstance(item, dict):
            continue
        scope = str(item.get('scope') or '').strip()
        try:
            count = int(item.get('count') or 0)
        except (TypeError, ValueError):
            count = 0
        if scope and count > 0:
            scope_chunks.append(f'{scope}({count})')
    if scope_chunks:
        lines.append(f'주요 경로: {", ".join(scope_chunks)}')

    category_chunks = []
    for key, label in (
        ('test_files', '테스트'),
        ('doc_files', '문서'),
        ('config_files', '설정')
    ):
        try:
            count = int(analysis.get(key) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            category_chunks.append(f'{label} {count}개')
    if category_chunks:
        lines.append(f'포함 범주: {", ".join(category_chunks)}')

    top_files = analysis.get('top_files') if isinstance(analysis.get('top_files'), list) else []
    file_chunks = []
    for item in top_files[:3]:
        if not isinstance(item, dict):
            continue
        path = str(item.get('path') or '').strip()
        try:
            additions = int(item.get('additions') or 0)
        except (TypeError, ValueError):
            additions = 0
        try:
            removals = int(item.get('deletions') or 0)
        except (TypeError, ValueError):
            removals = 0
        if path:
            file_chunks.append(f'{path} (+{additions}/-{removals})')
    if file_chunks:
        lines.append(f'변경량 상위 파일: {", ".join(file_chunks)}')

    return lines


def _build_commit_message(status_text, max_files=3, analysis=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    files = [path for path in _extract_changed_files(status_text) if not _is_history_file(path)]
    if not files:
        subject = timestamp
    else:
        listed = files[:max_files]
        suffix = f" (+{len(files) - max_files})" if len(files) > max_files else ''
        subject = f"{timestamp} {', '.join(listed)}{suffix}"

    analysis_lines = _build_commit_analysis_lines(analysis)
    body = ''
    comment = ''
    if analysis_lines:
        body = '자동 분석 요약\n' + '\n'.join(f'- {line}' for line in analysis_lines)
        comment = '; '.join(analysis_lines[:2])
    return {
        'subject': subject,
        'body': body,
        'comment': comment,
        'analysis_lines': analysis_lines
    }


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


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or '').strip().lower()
    if not text:
        return False
    return text in {'1', 'true', 't', 'yes', 'y', 'on'}


def _parse_history_request(payload):
    requested_remote = str(payload.get('remote') or '').strip() or 'origin'
    requested_branch = str(payload.get('branch') or '').strip() or 'main'
    try:
        limit = int(payload.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(100, limit))
    return requested_remote, requested_branch, limit


def _build_history_unavailable_result(
    repo_target,
    started_at,
    requested_remote='origin',
    requested_branch='main',
    limit=20,
    error_message=''
):
    remote_name = str(requested_remote or '').strip() or 'origin'
    branch_name = str(requested_branch or '').strip() or 'main'
    remote_ref = f'{remote_name}/{branch_name}'
    reason = str(error_message or '').strip() or 'git 저장소를 찾을 수 없습니다.'
    return {
        'ok': True,
        'exit_code': 0,
        'stdout': '',
        'stderr': '',
        'branch': '',
        'changed_files_count': 0,
        'changed_files': [],
        'changed_files_detail': [],
        'staged_files_count': 0,
        'staged_files': [],
        'staged_files_detail': [],
        'command': f'git log --max-count={limit} HEAD / {remote_ref}',
        'repo_root': '',
        'duration_ms': max(0, int((time.time() - started_at) * 1000)),
        'repo_target': _normalize_repo_target(repo_target),
        'history_limit': limit,
        'current_branch': '',
        'remote_name': remote_name,
        'main_branch': branch_name,
        'requested_remote_name': remote_name,
        'requested_main_branch': branch_name,
        'main_branch_fallback': False,
        'remote_main_ref': remote_ref,
        'current_branch_history': [],
        'remote_main_history': [],
        'remote_main_history_error': reason,
        'ahead_count': None,
        'behind_count': None,
        'repo_missing': True
    }


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
    upstream_branch = _read_upstream_branch(repo_root, env)
    ahead_count = None
    behind_count = None
    if upstream_branch and _ref_exists(repo_root, env, upstream_branch):
        ahead_count, behind_count = _read_divergence_counts(repo_root, env, 'HEAD', upstream_branch)
    payload = {
        'ok': exit_code == 0,
        'exit_code': exit_code,
        'stdout': (stdout or '').strip(),
        'stderr': (stderr or '').strip(),
        'branch': branch_name,
        'upstream_branch': upstream_branch,
        'ahead_count': ahead_count,
        'behind_count': behind_count,
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


def _run_checked(cmd, repo_root, env, timeout, fallback_error, cancel_event=None, mutation_state=None):
    result, error = _run_git_command(
        cmd,
        repo_root,
        timeout,
        env,
        cancel_event=cancel_event,
        mutation_state=mutation_state
    )
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
        if action not in {'status', 'history', 'stage', 'commit', 'push', 'sync', 'cancel', 'submit'}:
            return {'error': '지원하지 않는 git 작업입니다.'}
        if action == 'submit':
            return {'error': 'submit 작업은 비활성화되었습니다. stage -> commit -> push 순서로 실행해주세요.'}

        repo_target = _normalize_repo_target(payload.get('repo_target'))
        if action == 'cancel':
            cancel_result = _request_cancel_active_mutation(repo_target)
            if cancel_result.get('cancel_requested'):
                action_name = cancel_result.get('cancelled_action') or 'git'
                elapsed = int(cancel_result.get('active_elapsed_seconds') or 0)
                message = f'{action_name} 작업 취소를 요청했습니다. ({elapsed}초 경과)'
            else:
                message = '취소할 실행 중 git 작업이 없습니다.'
            return {
                'ok': True,
                'exit_code': 0,
                'stdout': '',
                'stderr': '',
                'command': 'git cancel',
                'repo_target': repo_target,
                'cancel_requested': bool(cancel_result.get('cancel_requested')),
                'cancelled_action': cancel_result.get('cancelled_action') or '',
                'active_elapsed_seconds': int(cancel_result.get('active_elapsed_seconds') or 0),
                'message': message
            }

        started_at = time.time()
        repo_root, error = _resolve_repo_root(repo_target)
        if error:
            if action == 'history':
                requested_remote, requested_branch, limit = _parse_history_request(payload)
                return _build_history_unavailable_result(
                    repo_target,
                    started_at,
                    requested_remote=requested_remote,
                    requested_branch=requested_branch,
                    limit=limit,
                    error_message='현재 repository: None'
                )
            return {'error': error, 'error_code': 'repo_not_found', 'repo_target': repo_target}

        env = os.environ.copy()
        env.setdefault('GIT_TERMINAL_PROMPT', '0')
        env.setdefault('GCM_INTERACTIVE', 'never')
        lock_acquired = False
        mutation_lock = None
        mutation_state = None
        if action in _GIT_MUTATION_ACTIONS:
            mutation_lock = _get_mutation_lock(repo_target)
            lock_acquired = mutation_lock.acquire(blocking=False)
            if not lock_acquired:
                active = _get_active_mutation_summary(repo_target)
                if active:
                    action_name = active.get('action') or 'git'
                    elapsed = int(active.get('elapsed_seconds') or 0)
                    return {
                        'error': (
                            f'다른 git 작업이 진행 중입니다. '
                            f'현재 {action_name} 실행 중 ({elapsed}초 경과). 잠시 후 다시 시도해주세요.'
                        ),
                        'error_code': 'git_mutation_in_flight',
                        'active_repo_target': active.get('repo_target'),
                        'active_action': action_name,
                        'active_elapsed_seconds': elapsed
                    }
                return {
                    'error': '다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.',
                    'error_code': 'git_mutation_in_flight'
                }
            mutation_state = _register_active_mutation(repo_target, action)
        cancel_event = mutation_state.get('cancel_event') if mutation_state else None

        try:
            if action == 'status':
                result, error = _run_checked(
                    ['git', '-C', str(repo_root), 'status', '--porcelain'],
                    repo_root,
                    env,
                    15,
                    'git status를 확인하지 못했습니다.',
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
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
                requested_remote = str(payload.get('remote') or '').strip()
                requested_branch = str(payload.get('branch') or '').strip()
                sync_apply_requested = _to_bool(
                    payload.get('apply_after_fetch')
                    if 'apply_after_fetch' in payload
                    else payload.get('apply')
                )
                remote_name = _normalize_remote_name(repo_root, env, requested_remote)
                if not remote_name:
                    return {'error': '원격 저장소를 찾을 수 없습니다.'}
                fetch_cmd = ['git', '-C', str(repo_root), 'fetch', '--prune', remote_name]
                fetch_result, error = _run_checked(
                    fetch_cmd,
                    repo_root,
                    env,
                    GIT_NETWORK_TIMEOUT_SECONDS,
                    'git fetch에 실패했습니다.',
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
                )
                if error:
                    return error

                resolved_remote, resolved_branch, fallback_used = _resolve_remote_branch(
                    repo_root,
                    env,
                    remote_name,
                    requested_branch
                )
                remote_name = resolved_remote or remote_name
                branch_name = resolved_branch or requested_branch
                sync_target = f'{remote_name}/{branch_name}' if remote_name and branch_name else ''

                sync_apply_ok = False
                sync_apply_exit_code = -1
                sync_apply_stdout = ''
                sync_apply_stderr = ''
                sync_apply_error = ''
                merge_cmd = []
                merge_result = None
                if sync_apply_requested:
                    if not sync_target:
                        return {'error': '동기화 대상 원격 브랜치를 확인할 수 없습니다.'}
                    if not _ref_exists(repo_root, env, sync_target):
                        return {'error': f'{sync_target} 레퍼런스를 찾을 수 없습니다. fetch 후 브랜치를 다시 확인해주세요.'}
                    merge_cmd = ['git', '-C', str(repo_root), 'merge', '--ff-only', sync_target]
                    merge_result, merge_error = _run_checked(
                        merge_cmd,
                        repo_root,
                        env,
                        GIT_TIMEOUT_SECONDS,
                        'git sync 적용에 실패했습니다.',
                        cancel_event=cancel_event,
                        mutation_state=mutation_state
                    )
                    if merge_error:
                        return merge_error
                    sync_apply_ok = True
                    sync_apply_exit_code = int(merge_result.returncode)
                    sync_apply_stdout = (merge_result.stdout or '').strip()
                    sync_apply_stderr = (merge_result.stderr or '').strip()

                fetch_stdout = (fetch_result.stdout or '').strip()
                fetch_stderr = (fetch_result.stderr or '').strip()
                combined_stdout = '\n'.join(
                    item for item in [fetch_stdout, sync_apply_stdout] if item
                )
                combined_stderr = '\n'.join(
                    item for item in [fetch_stderr, sync_apply_stderr] if item
                )
                command = ' '.join(fetch_cmd)
                if merge_cmd:
                    command = f"{command} && {' '.join(merge_cmd)}"
                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command=command,
                    exit_code=fetch_result.returncode,
                    stdout=combined_stdout,
                    stderr=combined_stderr,
                    extra={
                        'repo_target': repo_target,
                        'sync_remote': remote_name,
                        'sync_branch': branch_name,
                        'requested_sync_remote': requested_remote,
                        'requested_sync_branch': requested_branch,
                        'sync_branch_fallback': fallback_used,
                        'sync_target': sync_target,
                        'sync_apply_requested': sync_apply_requested,
                        'sync_apply_ok': sync_apply_ok,
                        'sync_apply_exit_code': sync_apply_exit_code,
                        'sync_apply_stdout': sync_apply_stdout,
                        'sync_apply_stderr': sync_apply_stderr,
                        'sync_apply_error': sync_apply_error
                    }
                )

            if action == 'history':
                requested_remote, requested_branch, limit = _parse_history_request(payload)

                current_branch = _read_current_branch(repo_root, env) or 'HEAD'
                resolved_remote, resolved_branch, fallback_used = _resolve_remote_branch(
                    repo_root,
                    env,
                    requested_remote,
                    requested_branch
                )
                remote_name = resolved_remote or requested_remote
                branch_name = resolved_branch or requested_branch
                remote_ref = f'{remote_name}/{branch_name}'

                current_branch_history, current_error = _read_commit_history(
                    repo_root,
                    env,
                    'HEAD',
                    max_count=limit
                )
                if current_error:
                    return {'error': current_error.get('error') or '현재 브랜치 이력을 불러오지 못했습니다.'}

                remote_history = []
                remote_history_error = ''
                if _ref_exists(repo_root, env, remote_ref):
                    remote_history, remote_error = _read_commit_history(
                        repo_root,
                        env,
                        remote_ref,
                        max_count=limit
                    )
                    if remote_error:
                        remote_history_error = remote_error.get('error') or f'{remote_ref} 이력을 불러오지 못했습니다.'
                        remote_history = []
                else:
                    remote_history_error = (
                        f'{remote_ref} 레퍼런스를 아직 찾을 수 없습니다. 먼저 fetch를 실행해 최신 원격 정보를 가져오세요.'
                    )

                ahead_count, behind_count = _read_divergence_counts(repo_root, env, 'HEAD', remote_ref)

                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command=f'git log --max-count={limit} HEAD / {remote_ref}',
                    exit_code=0,
                    stdout='',
                    stderr='',
                    extra={
                        'repo_target': repo_target,
                        'history_limit': limit,
                        'current_branch': current_branch,
                        'remote_name': remote_name,
                        'main_branch': branch_name,
                        'requested_remote_name': requested_remote,
                        'requested_main_branch': requested_branch,
                        'main_branch_fallback': fallback_used,
                        'remote_main_ref': remote_ref,
                        'current_branch_history': current_branch_history,
                        'remote_main_history': remote_history,
                        'remote_main_history_error': remote_history_error,
                        'ahead_count': ahead_count,
                        'behind_count': behind_count
                    }
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
                        'git 인덱스 초기화에 실패했습니다.',
                        cancel_event=cancel_event,
                        mutation_state=mutation_state
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
                    'git add에 실패했습니다.',
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
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

                commit_analysis = _analyze_staged_changes(repo_root, env, staged_files_detail)
                commit_analysis_lines = _build_commit_analysis_lines(commit_analysis)

                commit_message_input = str(payload.get('message') or '').strip()
                commit_message_subject = commit_message_input
                commit_message_body = ''
                commit_comment = '; '.join(commit_analysis_lines[:2]) if commit_analysis_lines else ''
                if not commit_message_subject:
                    synthetic_status = '\n'.join(
                        f"M  {entry['path']}" for entry in staged_files_detail if entry.get('path')
                    )
                    message_payload = _build_commit_message(
                        synthetic_status,
                        analysis=commit_analysis
                    )
                    commit_message_subject = str(message_payload.get('subject') or '').strip()
                    commit_message_body = str(message_payload.get('body') or '').strip()
                    commit_comment = str(message_payload.get('comment') or '').strip()
                    message_lines = message_payload.get('analysis_lines')
                    if isinstance(message_lines, list):
                        commit_analysis_lines = [str(line).strip() for line in message_lines if str(line).strip()]

                commit_cmd = ['git', '-C', str(repo_root), 'commit', '-m', commit_message_subject]
                if commit_message_body:
                    commit_cmd.extend(['-m', commit_message_body])
                commit_result, error = _run_checked(
                    commit_cmd,
                    repo_root,
                    env,
                    GIT_TIMEOUT_SECONDS,
                    'git commit에 실패했습니다.',
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
                )
                if error:
                    return error

                head_result, head_error = _run_git_command(
                    ['git', '-C', str(repo_root), 'rev-parse', '--short', 'HEAD'],
                    repo_root,
                    10,
                    env,
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
                )
                commit_hash = ''
                if not head_error and head_result and head_result.returncode == 0:
                    commit_hash = (head_result.stdout or '').strip()

                commit_message_full = commit_message_subject
                if commit_message_body:
                    commit_message_full = f'{commit_message_subject}\n\n{commit_message_body}'
                command_template = 'git commit -m <subject>'
                if commit_message_body:
                    command_template += ' -m <body>'

                return _build_result(
                    repo_root,
                    env,
                    started_at,
                    command=command_template,
                    exit_code=commit_result.returncode,
                    stdout=commit_result.stdout,
                    stderr=commit_result.stderr,
                    extra={
                        'commit_message': commit_message_subject,
                        'commit_message_subject': commit_message_subject,
                        'commit_message_body': commit_message_body,
                        'commit_message_full': commit_message_full,
                        'commit_comment': commit_comment,
                        'commit_analysis': commit_analysis,
                        'commit_analysis_lines': commit_analysis_lines,
                        'auto_generated_message': not bool(commit_message_input),
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
                    'git push에 실패했습니다.',
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
                )
                if error:
                    return error

                fetch_cmd = _GIT_ACTIONS['sync']
                fetch_result, fetch_exec_error = _run_git_command(
                    fetch_cmd,
                    repo_root,
                    GIT_NETWORK_TIMEOUT_SECONDS,
                    env,
                    cancel_event=cancel_event,
                    mutation_state=mutation_state
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
            if mutation_state:
                _clear_active_mutation(repo_target, mutation_state)
            if lock_acquired:
                mutation_lock.release()
    except Exception as exc:
        return {'error': f'git 작업 처리 중 오류가 발생했습니다: {exc}'}
