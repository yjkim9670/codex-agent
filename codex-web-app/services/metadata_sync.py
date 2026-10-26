"""Manual entrypoint and durable history for the external CommonTG runner."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import tempfile

ROOT = Path(os.environ.get('CODEX_COMMONTG_ROOT', '/Users/dinya/works/Sensor_Projects/CommonTG-Verification-Platform'))
_LOCK = threading.Lock()
_PROCESS = None


def runtime():
    return ROOT / '.sync_runtime' / 'codex_daily_doc_sync'


def read_text(path, limit=256_000):
    if not path.is_file() or path.is_symlink():
        return ''
    with path.open(encoding='utf-8', errors='replace') as handle:
        text = handle.read(limit + 1)
    return text[:limit] + ('\n[truncated]' if len(text) > limit else '')


def read_json(path):
    try:
        return json.loads(read_text(path, 8_000_000))
    except (ValueError, OSError):
        return {}


def history():
    entries = []
    for path in sorted((runtime() / 'runs').glob('*/run_metadata.json'), reverse=True)[:200]:
        if path.is_symlink() or path.parent.is_symlink():
            continue
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        entries.append({**{key: data.get(key) for key in (
            'started_at_kst', 'finished_at_kst', 'mode', 'scope', 'result', 'published', 'error', 'validation')},
            'id': path.parent.name, 'changed_files': len(data.get('changes') or []),
            'has_change_record': 'changes' in data})
    return {'available': (ROOT / 'git_actions/scripts/run_metadata_doc_sync.py').is_file(),
            'project': str(ROOT), 'scheduler': 'launchd · KST 00:00',
            'running': bool((_PROCESS and _PROCESS.poll() is None) or (runtime() / 'run.lock').exists()),
            'runs': entries}


def detail(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id):
        raise ValueError('잘못된 실행 ID입니다.')
    folder = runtime() / 'runs' / run_id
    if folder.is_symlink() or not folder.is_dir():
        raise FileNotFoundError(run_id)
    return {'metadata': read_json(folder / 'run_metadata.json'),
            'summary': read_text(folder / 'codex_final_response.md'),
            'validation_log': read_text(folder / 'validation.log'),
            'error_log': read_text(folder / 'codex_stderr.log', 20_000)}


def preview():
    """Collect current daily candidates without running Codex or updating sync state."""
    collector = ROOT / 'git_actions/scripts/collect_metadata_doc_sync_context.py'
    if not collector.is_file():
        raise FileNotFoundError('TG Platform 변경 영향 분석기를 찾을 수 없습니다.')
    state = read_json(runtime() / 'state.json')
    since_ref = state.get('last_success_head', '') if isinstance(state, dict) else ''
    with tempfile.TemporaryDirectory(prefix='workbench-doc-preview-') as folder:
        output = Path(folder) / 'context.json'
        command = [sys.executable, str(collector), '--mode', 'daily', '--scope', 'all',
                   '--skip-validation', '--output', str(output)]
        if since_ref:
            command.extend(['--since-ref', since_ref])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('변경 영향 분석에 실패했습니다. TG Platform 저장소 상태를 확인하세요.')
        context = json.loads(output.read_text(encoding='utf-8'))
    groups = {
        kind: {name: {'name': name, 'documents': [], 'reasons': []}
               for name in context.get('affected_scopes', {}).get(key, [])}
        for kind, key in (('feature', 'features'), ('project', 'projects'))
    }
    other_docs = []
    for doc in context.get('candidate_docs', []):
        kind = doc.get('scope_type')
        if kind not in groups:
            other_docs.append(doc)
            continue
        name = doc['scope_name']
        entry = groups[kind].setdefault(name, {'name': name, 'documents': [], 'reasons': []})
        entry['documents'].append(doc['path'])
        entry['reasons'] = sorted(set(entry['reasons']) | set(doc.get('reasons', [])))
    return {'generated_at_kst': context.get('generated_at_kst'), 'since_ref': since_ref,
            'features': [groups['feature'][name] for name in sorted(groups['feature'])],
            'projects': [groups['project'][name] for name in sorted(groups['project'])],
            'other_documents': other_docs, 'warnings': context.get('warnings', []),
            'immediate_update_reasons': context.get('immediate_update_reasons', []),
            'changed_paths_count': len(context.get('changed_paths', {}).get('all', []))}


def start(scope):
    global _PROCESS
    if not isinstance(scope, str) or not re.fullmatch(r'(?:feature|design_tool|tool|project):[A-Za-z0-9_-]+', scope):
        raise ValueError('feature:vcd 또는 project:HPA처럼 좁은 범위를 입력하세요.')
    runner = ROOT / 'git_actions/scripts/run_metadata_doc_sync.py'
    if not runner.is_file():
        raise FileNotFoundError('TG Platform 실행기를 찾을 수 없습니다.')
    with _LOCK:
        if (_PROCESS and _PROCESS.poll() is None) or (runtime() / 'run.lock').exists():
            return {'started': False, 'reason': '이미 문서 동기화가 실행 중입니다.'}
        runtime().mkdir(parents=True, exist_ok=True)
        with (runtime() / 'workbench_manual.log').open('a', encoding='utf-8') as output:
            _PROCESS = subprocess.Popen([sys.executable, str(runner), '--mode', 'manual', '--scope', scope],
                                        cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        return {'started': True, 'pid': _PROCESS.pid}


def run_lightweight_sync(account_id):
    """Run the existing guarded batch before a lightweight blog stage.

    This runs in the usage worker, outside its account-snapshot lock. The
    external runner retains ownership of the repository lock and checkpoint.
    """
    from . import codex_chat

    runner = ROOT / 'git_actions/scripts/run_metadata_doc_sync.py'
    if codex_chat.is_internal_multiuser_mode() or not runner.is_file():
        return {'status': 'unavailable'}
    context = codex_chat._account_storage_context(account_id)
    if context is None:
        return {'status': 'deferred', 'reason': 'account_not_found'}
    if codex_chat._account_has_active_codex_stream(account_id):
        return {'status': 'deferred', 'reason': 'account_busy'}
    if (_PROCESS and _PROCESS.poll() is None) or (runtime() / 'run.lock').exists():
        return {'status': 'deferred', 'reason': 'metadata_sync_busy'}
    try:
        candidates = preview()
        if not (any(group['documents'] for kind in ('features', 'projects')
                    for group in candidates[kind]) or candidates['other_documents']
                or candidates['immediate_update_reasons']):
            if (runtime() / 'run.lock').exists():
                return {'status': 'deferred', 'reason': 'metadata_sync_busy'}
            return {'status': 'no_changes', 'reason': 'skipped_no_candidates'}
        environment = dict(os.environ, CODEX_HOME=str(context['codex_home']))
        result = subprocess.run(
            [sys.executable, str(runner), '--mode', 'daily', '--scope', 'all'],
            cwd=ROOT, env=environment, capture_output=True, text=True,
        )
        if result.returncode:
            return {'status': 'failed', 'reason': 'metadata_sync_failed'}
        # The runner may find no candidates after the preview (another batch
        # could have advanced its checkpoint). Only its explicit skip counts.
        if result.stdout.strip() == 'Skipped Codex because there were no candidate docs or immediate update reasons.':
            return {'status': 'no_changes', 'reason': 'skipped_no_candidates'}
        matches = re.findall(r'^Run directory: (.+)$', result.stdout, re.MULTILINE)
        if not matches:
            return {'status': 'failed', 'reason': 'metadata_sync_result_missing'}
        folder = Path(matches[-1]).resolve()
        if folder.parent != (runtime() / 'runs').resolve():
            return {'status': 'failed', 'reason': 'metadata_sync_result_invalid'}
        record = read_json(folder / 'run_metadata.json')
        if (not isinstance(record, dict) or record.get('result') != 'success'
                or not isinstance(record.get('changes'), list)):
            return {'status': 'failed', 'reason': 'metadata_sync_failed'}
        return {'status': 'completed' if record['changes'] else 'no_changes',
                'run_id': folder.name, 'changed_files': len(record['changes']),
                'token_usage': record.get('codex_usage') or {}}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return {'status': 'failed', 'reason': 'metadata_sync_failed'}
