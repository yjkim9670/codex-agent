"""Read-only local collectors and account-scoped, observed usage statistics.

Original ledgers/SQLite databases/rollouts are never rewritten. The derived
cache is atomically replaced under the existing cross-process account lock.
"""
from collections import Counter
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from zoneinfo import ZoneInfo

from .model_usage_analysis import analyze
from .usage_reconciliation import build_usage_reconciliation

KST = ZoneInfo('Asia/Seoul')
_LOG = logging.getLogger(__name__)
_WAKE = threading.Event()
_STARTED = False
_START_LOCK = threading.Lock()
_SKIP = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'tmp',
         '.playwright-browsers', 'build', 'dist', '.pytest_cache', 'Library', '.Trash'}


def _read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {} if default is None else default


def _stamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, KST)
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp missing timezone')
    return result.astimezone(KST)


def _walk(root, depth=8):
    root = Path(root)
    if not root.is_dir():
        return
    for base, dirs, files in os.walk(root, followlinks=False):
        level = len(Path(base).relative_to(root).parts)
        dirs[:] = [d for d in dirs if d not in _SKIP and (not d.startswith('.') or d in {'.agent_state', '.codex'})] if level < depth else []
        yield Path(base), files


def discover_homes(context, events):
    from ..config import is_internal_multiuser_mode, WORKSPACE_DIR, _get_login_codex_home
    homes = {Path(context[k]).resolve() for k in ('codex_home', 'queued_codex_home', 'app_server_codex_home') if context.get(k)}
    if is_internal_multiuser_mode():
        # Never scan other internal users or the host user's home.
        roots = [Path(WORKSPACE_DIR)]
    else:
        login = _get_login_codex_home()
        if login:
            homes.add(login.resolve())
        configured = os.environ.get('CODEX_USAGE_DISCOVERY_ROOTS')
        roots = ([Path(p).expanduser() for p in configured.split(os.pathsep) if p] if configured else
                 ([login.parent / 'works'] if login else [Path(WORKSPACE_DIR)]))
        roots += [Path(e['workspace_path']) for e in events if e.get('workspace_path')]
    for root in set(roots):
        for base, files in _walk(root):
            if any(f.startswith('state_') and f.endswith('.sqlite') for f in files):
                homes.add(base.resolve())
    return sorted(homes, key=str)


def _rollout(path, fallback):
    """Derive deltas within each turn, not repeated cumulative token samples."""
    segments = {}
    previous = Counter()
    model = effort = 'unknown'
    thread = fallback['id']
    workspace = fallback.get('cwd', '')
    turn = 'unknown'
    begin = None
    forked = False
    errors = 0
    with Path(path).open(encoding='utf-8') as source:
        for line in source:
            try:
                event = json.loads(line)
                payload = event.get('payload') or {}
                at = _stamp(event['timestamp'])
                if event.get('type') == 'session_meta':
                    thread = payload.get('id') or thread
                    workspace = payload.get('cwd') or workspace
                    forked = bool(payload.get('forked_from_id'))
                if event.get('type') == 'turn_context':
                    model = payload.get('model') or 'unknown'
                    effort = payload.get('effort') or payload.get('reasoning_effort') or 'unknown'
                    turn = payload.get('turn_id') or at.isoformat()
                    begin = at
                info = payload.get('info') or {}
                usage = info.get('total_token_usage')
                if payload.get('type') != 'token_count' or not isinstance(usage, dict):
                    continue
                current = Counter({k: max(0, int(usage.get(k) or 0)) for k in
                                   ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens')})
                if current['total_tokens'] < previous['total_tokens']:
                    errors += 1
                delta = {k: max(0, current[k] - previous[k]) for k in current}
                previous = current
                if not delta['total_tokens']:
                    continue
                key = (turn, model, effort)
                row = segments.setdefault(key, {
                    'event_id': f'rollout:{thread}:{turn}:{model}:{effort}',
                    'thread_id': thread, 'workspace_path': workspace, 'model': model,
                    'reasoning_effort': effort, 'recorded_at': at.isoformat(),
                    'begin_at': (begin or at).isoformat(), 'source': 'rollout',
                    'input_tokens': 0, 'cached_input_tokens': 0,
                    'output_tokens': 0, 'total_tokens': 0,
                })
                for k, v in delta.items():
                    row[k] += v
                row['recorded_at'] = at.isoformat()
                row['duration_ms'] = max(0, int((at - _stamp(row['begin_at'])).total_seconds() * 1000))
            except (ValueError, KeyError, TypeError):
                errors += 1
    return {'id': thread, 'events': list(segments.values()), 'forked': forked, 'parse_errors': errors,
            'db_tokens': max(0, int(fallback.get('tokens_used') or 0))}


def merge_events(ledger, threads):
    """Only unique exact token/component/time matches suppress a rollout.

    Ambiguous matches are quarantined, rather than increasing totals. DB-only
    cumulative balances remain unallocated because their dates/mix are unknown.
    """
    result = {e['event_id']: e for e in ledger}
    index = {}
    temporal = {}
    for event in result.values():
        signature = tuple(event.get(k) for k in ('workspace_path', 'model', 'reasoning_effort', 'total_tokens', 'input_tokens', 'output_tokens'))
        index.setdefault(signature, []).append(event)
        temporal.setdefault(signature[:3], []).append(event)
    used = set()
    diagnostics = Counter()
    for thread in threads:
        if thread.get('forked') or thread.get('parse_errors'):
            diagnostics['quarantined_tokens'] += sum(e['total_tokens'] for e in thread['events'])
            diagnostics['quarantined_threads'] += 1
            continue
        log_tokens = sum(e['total_tokens'] for e in thread['events'])
        diagnostics['unallocated_db_tokens'] += max(0, thread['db_tokens'] - thread.get('log_total_tokens', log_tokens))
        for event in thread['events']:
            signature = tuple(event.get(k) for k in ('workspace_path', 'model', 'reasoning_effort', 'total_tokens', 'input_tokens', 'output_tokens'))
            finish = _stamp(event['recorded_at'])
            candidates = [e for e in index.get(signature, []) if e['event_id'] not in used and
                          abs((_stamp(e['recorded_at']) - finish).total_seconds()) <= 120]
            if len(candidates) == 1:
                used.add(candidates[0]['event_id'])
                diagnostics['matched_rollout_tokens'] += event['total_tokens']
            elif candidates:
                diagnostics['ambiguous_tokens'] += event['total_tokens']
            else:
                nearby = [e for e in temporal.get(signature[:3], []) if e['event_id'] not in used and
                          abs((_stamp(e['recorded_at']) - finish).total_seconds()) <= 120]
                if nearby:
                    diagnostics['ambiguous_tokens'] += event['total_tokens']
                    continue
                result[event['event_id']] = event
                diagnostics['supplemental_tokens'] += event['total_tokens']
    return list(result.values()), dict(diagnostics)


def collect(context, *, force=False, now=None):
    from . import codex_chat as chat
    now = now or datetime.now(KST)
    path = Path(context['root']) / 'codex_usage_collection.json'
    with chat._acquire_path_file_lock(path):
        old = _read(path)
        if old.get('version') == 2 and old.get('collected_at') and (now - _stamp(old['collected_at'])).total_seconds() < (2 if force else 300):
            return old
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=89)
        ledger = []
        sources = []
        errors = []
        try:
            with Path(context['usage_events_path']).open(encoding='utf-8') as source:
                for number, line in enumerate(source, 1):
                    try:
                        event = json.loads(line)
                        if _stamp(event['recorded_at']) >= cutoff:
                            ledger.append(event)
                    except (ValueError, KeyError, TypeError):
                        errors.append(f'원장 {number}행: 잘못된 기록')
        except FileNotFoundError:
            pass
        identity = chat._read_auth_identity(context['codex_home']).get('provider_account_id')
        cached = old.get('files', {}) if old.get('version') == 2 else {}
        files = {}
        threads = {}
        for home in discover_homes(context, ledger):
            if not home.is_dir():
                continue
            state = {'home': str(home), 'status': 'ok', 'threads': 0, 'last_record_at': None}
            try:
                source_identity = chat._read_auth_identity(home).get('provider_account_id')
                if not identity or source_identity != identity:
                    state['status'] = 'account_unverified'
                    sources.append(state)
                    continue
                databases = sorted(home.glob('state_*.sqlite'))
                if not databases:
                    state['status'] = 'no_session_db'
                for database in databases:
                    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2) as db:
                        db.row_factory = sqlite3.Row
                        rows = db.execute('SELECT id, rollout_path, cwd, tokens_used, created_at, updated_at FROM threads WHERE updated_at >= ?', (int(cutoff.timestamp()),)).fetchall()
                    for raw in rows:
                        row = dict(raw)
                        state['threads'] += 1
                        at = _stamp(row['updated_at']).isoformat()
                        state['last_record_at'] = max(state['last_record_at'] or at, at)
                        rollout = Path(row['rollout_path'])
                        if not rollout.is_file():
                            for folder in ('sessions', 'archived_sessions'):
                                if folder in rollout.parts:
                                    offset = rollout.parts.index(folder)
                                    relocated = home.joinpath(*rollout.parts[offset:])
                                    if relocated.is_file():
                                        rollout = relocated
                                        break
                        if not rollout.is_file():
                            candidate = {'id': row['id'], 'events': [], 'db_tokens': row['tokens_used']}
                        else:
                            stat = rollout.stat()
                            key = str(rollout)
                            fingerprint = [stat.st_size, stat.st_mtime_ns, row['tokens_used']]
                            previous = cached.get(key, {})
                            candidate = previous.get('thread') if previous.get('fingerprint') == fingerprint else _rollout(rollout, row)
                            files[key] = {'fingerprint': fingerprint, 'thread': candidate}
                        candidate['log_total_tokens'] = candidate.get('log_total_tokens', sum(e['total_tokens'] for e in candidate['events']))
                        candidate['events'] = [e for e in candidate['events'] if _stamp(e['recorded_at']) >= cutoff]
                        prior = threads.get(row['id'])
                        if prior is None or sum(e['total_tokens'] for e in candidate['events']) > sum(e['total_tokens'] for e in prior['events']):
                            threads[row['id']] = candidate
                # Logs without a DB entry (including archived/session-only homes).
                for directory in ('sessions', 'archived_sessions'):
                    for rollout in (home / directory).rglob('*.jsonl'):
                        stat = rollout.stat()
                        if stat.st_mtime < cutoff.timestamp() or str(rollout) in files:
                            continue
                        fingerprint = [stat.st_size, stat.st_mtime_ns, 0]
                        previous = cached.get(str(rollout), {})
                        candidate = previous.get('thread') if previous.get('fingerprint') == fingerprint else _rollout(rollout, {'id': rollout.stem})
                        candidate['log_total_tokens'] = candidate.get('log_total_tokens', sum(e['total_tokens'] for e in candidate['events']))
                        candidate['events'] = [e for e in candidate['events'] if _stamp(e['recorded_at']) >= cutoff]
                        files[str(rollout)] = {'fingerprint': fingerprint, 'thread': candidate}
                        if candidate['id'] not in threads:
                            threads[candidate['id']] = candidate
            except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
                state['status'] = 'error'
                state['error'] = str(exc)
            sources.append(state)
        events, diagnostics = merge_events(ledger, threads.values())
        events = [e for e in events if cutoff <= _stamp(e['recorded_at']) <= now]
        result = {'version': 2, 'collected_at': now.isoformat(), 'retention_days': 90,
                  'account_id': context['account']['id'], 'events': events, 'sources': sources,
                  'diagnostics': diagnostics, 'errors': errors, 'files': files}
        chat._write_json_atomic(path, result)
        return result


def dashboard(account_id=None, days=30, effort='medium', environment='all'):
    from . import codex_chat as chat
    context = chat._account_storage_context(account_id)
    if not context:
        raise ValueError('알 수 없는 계정입니다.')
    collected = collect(context)
    data = {'events': collected['events']}
    errors = list(collected['errors'])
    for name in ('codex_usage_calibration.json', 'codex_usage_history.json', 'codex_account_usage_snapshot.json'):
        try:
            data[name] = _read(Path(context['root']) / name)
        except (ValueError, OSError) as exc:
            errors.append(f'{name}: {exc}')
            data[name] = {}
    report = analyze(Path(context['root']), days, effort, environment, data=data)
    all_days = {}
    for event in collected['events']:
        day = _stamp(event['recorded_at']).date().isoformat()
        all_days.setdefault(day, {'total_tokens': 0})['total_tokens'] += event.get('total_tokens', 0)
    report.update({
        'collected_at': collected['collected_at'], 'sources': collected['sources'],
        'collection_diagnostics': collected['diagnostics'], 'collection_errors': errors,
        'environments': sorted({e.get('workspace_path') for e in collected['events'] if e.get('workspace_path')}),
        'efforts': sorted({e.get('reasoning_effort') or 'unknown' for e in collected['events']}),
        'accounts': chat.get_codex_accounts_summary(),
        'quota_samples': [s for s in data['codex_usage_history.json'].get('account_limit_samples', [])
                          if s.get('limits_observed_at') and report['start'] <= _stamp(s['limits_observed_at']).isoformat() <= report['end']],
        'account_refresh_error': data['codex_account_usage_snapshot.json'].get('error'),
        'limits_observed_at': data['codex_account_usage_snapshot.json'].get('last_success_at'),
        'reconciliation': build_usage_reconciliation(data['codex_account_usage_snapshot.json'], {'by_day': all_days}, days=days),
    })
    return report


def request_collection():
    _WAKE.set()


def ensure_collection_worker():
    from ..config import is_internal_multiuser_mode
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
        def work():
            from . import codex_chat as chat
            while True:
                forced = _WAKE.is_set()
                _WAKE.clear()
                try:
                    def collect_accounts():
                        for account in chat.get_codex_accounts_summary()['accounts']:
                            context = chat._account_storage_context(account['id'])
                            if context:
                                collect(context, force=forced)
                    if is_internal_multiuser_mode():
                        from ..config import CODEX_INTERNAL_USER_MAP_PATH
                        from .multiuser import InternalUser, activate_user, deactivate_user, load_ip_user_map, storage_key_for_ip
                        for ip, record in load_ip_user_map(CODEX_INTERNAL_USER_MAP_PATH).items():
                            user = InternalUser(record['username'], record['role'], ip, storage_key_for_ip(ip), record.get('profile_configured', False))
                            token = activate_user(user)
                            try:
                                collect_accounts()
                            finally:
                                deactivate_user(token)
                    else:
                        collect_accounts()
                except Exception:
                    _LOG.exception('automatic usage collection failed')
                _WAKE.wait(60)
        threading.Thread(target=work, name='codex-usage-collector', daemon=True).start()
