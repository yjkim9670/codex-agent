"""Remote branch listing and safe switching helpers for Codex Workbench."""

import os

from .git_ops import (
    GIT_NETWORK_TIMEOUT_SECONDS,
    _clear_active_mutation,
    _get_active_mutation_summary,
    _get_mutation_lock,
    _list_remotes,
    _normalize_repo_target,
    _read_changed_snapshot,
    _read_current_branch,
    _read_upstream_branch,
    _ref_exists,
    _register_active_mutation,
    _resolve_repo_root,
    _run_checked,
    _run_git_command,
)


def _git_env():
    env = os.environ.copy()
    env.setdefault('GIT_TERMINAL_PROMPT', '0')
    env.setdefault('GCM_INTERACTIVE', 'never')
    return env


def _mutation_busy_result(repo_target):
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
            'active_elapsed_seconds': elapsed,
        }
    return {
        'error': '다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.',
        'error_code': 'git_mutation_in_flight',
    }


def _split_remote_branch_ref(value, remotes):
    ref_name = str(value or '').strip()
    for remote in sorted(remotes, key=len, reverse=True):
        prefix = f'{remote}/'
        if ref_name.startswith(prefix):
            return remote, ref_name[len(prefix):].strip()
    return '', ''


def _read_local_branch_upstreams(repo_root, env):
    result, error = _run_git_command(
        [
            'git', '-C', str(repo_root), 'for-each-ref',
            '--format=%(refname:short)%09%(upstream:short)',
            'refs/heads',
        ],
        repo_root,
        15,
        env,
    )
    if error or not result or result.returncode != 0:
        return {}
    upstreams = {}
    for raw_line in (result.stdout or '').splitlines():
        local_branch, _, upstream = raw_line.partition('\t')
        local_branch = local_branch.strip()
        upstream = upstream.strip()
        if local_branch:
            upstreams[local_branch] = upstream
    return upstreams


def _list_remote_branch_entries(repo_root, env):
    remotes = _list_remotes(repo_root, env)
    result, error = _run_git_command(
        [
            'git', '-C', str(repo_root), 'for-each-ref',
            '--format=%(refname:short)%09%(objectname:short)',
            'refs/remotes',
        ],
        repo_root,
        15,
        env,
    )
    if error:
        return [], remotes, error
    if not result or result.returncode != 0:
        message = ((result.stderr or '').strip() if result else '') or '원격 브랜치 목록을 읽지 못했습니다.'
        return [], remotes, {'error': message, 'error_code': 'git_remote_branches_failed'}

    current_branch = _read_current_branch(repo_root, env)
    current_upstream = _read_upstream_branch(repo_root, env)
    local_upstreams = _read_local_branch_upstreams(repo_root, env)
    local_by_upstream = {
        upstream: local
        for local, upstream in local_upstreams.items()
        if upstream
    }
    entries = []
    for raw_line in (result.stdout or '').splitlines():
        ref_name, _, short_hash = raw_line.partition('\t')
        ref_name = ref_name.strip()
        if not ref_name or ref_name.endswith('/HEAD'):
            continue
        remote_name, branch_name = _split_remote_branch_ref(ref_name, remotes)
        if not remote_name or not branch_name:
            continue
        local_branch = local_by_upstream.get(ref_name) or ''
        entries.append({
            'remote': remote_name,
            'branch': branch_name,
            'ref': ref_name,
            'short_hash': short_hash.strip(),
            'local_branch': local_branch,
            'checked_out': bool(
                current_branch
                and (
                    current_branch == local_branch
                    or (current_branch == branch_name and current_upstream == ref_name)
                )
            ),
        })
    entries.sort(key=lambda item: (item['remote'].lower(), item['branch'].lower()))
    return entries, remotes, None


def _build_remote_branch_list_result(repo_target, repo_root, env, *, fetch_performed=False):
    entries, remotes, error = _list_remote_branch_entries(repo_root, env)
    if error:
        return {
            **error,
            'repo_target': _normalize_repo_target(repo_target),
        }
    changed_files_detail, _ = _read_changed_snapshot(repo_root, env)
    return {
        'ok': True,
        'repo_target': _normalize_repo_target(repo_target),
        'repo_root': str(repo_root),
        'current_branch': _read_current_branch(repo_root, env),
        'current_upstream': _read_upstream_branch(repo_root, env),
        'changed_files_count': len(changed_files_detail),
        'dirty': bool(changed_files_detail),
        'remotes': remotes,
        'remote_branches': entries,
        'fetch_performed': bool(fetch_performed),
    }


def list_remote_branches(repo_target='workspace', *, fetch=False):
    """Return fetched remote branch refs, optionally refreshing all remotes first."""
    target = _normalize_repo_target(repo_target)
    repo_root, error = _resolve_repo_root(target)
    if error:
        return {'error': error, 'error_code': 'repo_not_found', 'repo_target': target}

    env = _git_env()
    if not fetch:
        return _build_remote_branch_list_result(target, repo_root, env)

    mutation_lock = _get_mutation_lock(target)
    if not mutation_lock.acquire(blocking=False):
        return _mutation_busy_result(target)
    mutation_state = _register_active_mutation(target, 'branch-fetch')
    cancel_event = mutation_state.get('cancel_event')
    try:
        result, fetch_error = _run_checked(
            ['git', '-C', str(repo_root), 'fetch', '--all', '--prune'],
            repo_root,
            env,
            GIT_NETWORK_TIMEOUT_SECONDS,
            'git fetch에 실패했습니다.',
            cancel_event=cancel_event,
            mutation_state=mutation_state,
        )
        if fetch_error:
            return {
                **fetch_error,
                'repo_target': target,
            }
        payload = _build_remote_branch_list_result(
            target,
            repo_root,
            env,
            fetch_performed=True,
        )
        payload['fetch_stdout'] = (result.stdout or '').strip()
        payload['fetch_stderr'] = (result.stderr or '').strip()
        return payload
    finally:
        _clear_active_mutation(target, mutation_state)
        mutation_lock.release()


def _validate_branch_name(repo_root, env, branch_name):
    result, error = _run_git_command(
        ['git', '-C', str(repo_root), 'check-ref-format', '--branch', branch_name],
        repo_root,
        10,
        env,
    )
    return not error and bool(result) and result.returncode == 0


def _read_local_branch_upstream(repo_root, env, branch_name):
    result, error = _run_git_command(
        [
            'git', '-C', str(repo_root), 'for-each-ref',
            '--format=%(upstream:short)',
            f'refs/heads/{branch_name}',
        ],
        repo_root,
        10,
        env,
    )
    if error or not result or result.returncode != 0:
        return ''
    return (result.stdout or '').strip().splitlines()[0].strip() if (result.stdout or '').strip() else ''


def switch_remote_branch(repo_target='workspace', *, remote='', branch='', fetch=True):
    """Safely switch to a remote tracking branch.

    Switching is intentionally blocked while the working tree is dirty so a
    mobile one-tap branch change cannot strand or carry uncommitted edits into
    another branch.
    """
    target = _normalize_repo_target(repo_target)
    requested_remote = str(remote or '').strip()
    requested_branch = str(branch or '').strip()
    if not requested_remote or not requested_branch:
        return {
            'error': '전환할 원격 저장소와 브랜치를 선택해주세요.',
            'error_code': 'git_switch_target_missing',
            'repo_target': target,
        }

    repo_root, error = _resolve_repo_root(target)
    if error:
        return {'error': error, 'error_code': 'repo_not_found', 'repo_target': target}
    env = _git_env()
    if requested_remote not in _list_remotes(repo_root, env):
        return {
            'error': f"원격 저장소 '{requested_remote}'을 찾을 수 없습니다.",
            'error_code': 'git_remote_missing',
            'repo_target': target,
        }
    if not _validate_branch_name(repo_root, env, requested_branch):
        return {
            'error': f"올바르지 않은 브랜치 이름입니다: {requested_branch}",
            'error_code': 'git_branch_invalid',
            'repo_target': target,
        }

    mutation_lock = _get_mutation_lock(target)
    if not mutation_lock.acquire(blocking=False):
        return _mutation_busy_result(target)
    mutation_state = _register_active_mutation(target, 'switch')
    cancel_event = mutation_state.get('cancel_event')
    try:
        changed_files_detail, _ = _read_changed_snapshot(repo_root, env)
        if changed_files_detail:
            return {
                'error': '작업 트리에 커밋되지 않은 변경이 있어 브랜치 전환을 중단했습니다. 변경사항을 커밋하거나 되돌린 후 다시 시도해주세요.',
                'error_code': 'git_switch_worktree_dirty',
                'repo_target': target,
                'changed_files_count': len(changed_files_detail),
            }

        fetch_stdout = ''
        fetch_stderr = ''
        if fetch:
            fetch_result, fetch_error = _run_checked(
                ['git', '-C', str(repo_root), 'fetch', '--prune', requested_remote],
                repo_root,
                env,
                GIT_NETWORK_TIMEOUT_SECONDS,
                'git fetch에 실패했습니다.',
                cancel_event=cancel_event,
                mutation_state=mutation_state,
            )
            if fetch_error:
                return {
                    **fetch_error,
                    'repo_target': target,
                }
            fetch_stdout = (fetch_result.stdout or '').strip()
            fetch_stderr = (fetch_result.stderr or '').strip()

        remote_ref = f'{requested_remote}/{requested_branch}'
        if not _ref_exists(repo_root, env, f'refs/remotes/{remote_ref}'):
            return {
                'error': f'{remote_ref} 원격 브랜치를 찾을 수 없습니다. 먼저 fetch 후 다시 시도해주세요.',
                'error_code': 'git_remote_ref_missing',
                'repo_target': target,
                'remote': requested_remote,
                'branch': requested_branch,
                'remote_ref': remote_ref,
            }

        local_ref = f'refs/heads/{requested_branch}'
        local_exists = _ref_exists(repo_root, env, local_ref)
        current_branch = _read_current_branch(repo_root, env)
        current_upstream = _read_upstream_branch(repo_root, env)
        if current_branch == requested_branch and current_upstream == remote_ref:
            payload = _build_remote_branch_list_result(target, repo_root, env, fetch_performed=fetch)
            payload.update({
                'switched': False,
                'already_current': True,
                'remote': requested_remote,
                'branch': requested_branch,
                'remote_ref': remote_ref,
                'fetch_stdout': fetch_stdout,
                'fetch_stderr': fetch_stderr,
            })
            return payload

        if local_exists:
            local_upstream = _read_local_branch_upstream(repo_root, env, requested_branch)
            if local_upstream and local_upstream != remote_ref:
                return {
                    'error': (
                        f"로컬 브랜치 '{requested_branch}'가 이미 {local_upstream}을 추적하고 있어 "
                        f'{remote_ref}로 자동 전환하지 않았습니다.'
                    ),
                    'error_code': 'git_switch_local_branch_conflict',
                    'repo_target': target,
                    'local_branch': requested_branch,
                    'local_upstream': local_upstream,
                    'remote_ref': remote_ref,
                }
            switch_cmd = ['git', '-C', str(repo_root), 'switch', requested_branch]
        else:
            switch_cmd = [
                'git', '-C', str(repo_root), 'switch', '--track',
                '-c', requested_branch, remote_ref,
            ]

        switch_result, switch_error = _run_checked(
            switch_cmd,
            repo_root,
            env,
            60,
            'git branch switch에 실패했습니다.',
            cancel_event=cancel_event,
            mutation_state=mutation_state,
        )
        if switch_error:
            return {
                **switch_error,
                'repo_target': target,
                'remote': requested_remote,
                'branch': requested_branch,
                'remote_ref': remote_ref,
            }

        if local_exists and not _read_local_branch_upstream(repo_root, env, requested_branch):
            upstream_result, upstream_error = _run_checked(
                [
                    'git', '-C', str(repo_root), 'branch',
                    '--set-upstream-to', remote_ref, requested_branch,
                ],
                repo_root,
                env,
                30,
                '브랜치 upstream 설정에 실패했습니다.',
                cancel_event=cancel_event,
                mutation_state=mutation_state,
            )
            if upstream_error:
                return {
                    **upstream_error,
                    'repo_target': target,
                    'remote': requested_remote,
                    'branch': requested_branch,
                    'remote_ref': remote_ref,
                }
            upstream_stdout = (upstream_result.stdout or '').strip()
            upstream_stderr = (upstream_result.stderr or '').strip()
        else:
            upstream_stdout = ''
            upstream_stderr = ''

        payload = _build_remote_branch_list_result(target, repo_root, env, fetch_performed=fetch)
        payload.update({
            'switched': True,
            'already_current': False,
            'remote': requested_remote,
            'branch': requested_branch,
            'remote_ref': remote_ref,
            'switch_stdout': (switch_result.stdout or '').strip(),
            'switch_stderr': (switch_result.stderr or '').strip(),
            'upstream_stdout': upstream_stdout,
            'upstream_stderr': upstream_stderr,
            'fetch_stdout': fetch_stdout,
            'fetch_stderr': fetch_stderr,
        })
        return payload
    finally:
        _clear_active_mutation(target, mutation_state)
        mutation_lock.release()
