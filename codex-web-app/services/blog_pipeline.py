"""Small, durable blog-writing pipeline.

The pipeline intentionally keeps the orchestration state outside chat history.
Each run advances one stage and asks Codex to touch only the files for that
stage.  A shared account/project claim prevents copies of Workbench from
starting the same project at the same time.
"""

from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
import uuid

from ..config import KST
from ..utils.time import normalize_timestamp, parse_timestamp
from . import codex_chat


_LOGGER = logging.getLogger(__name__)

_BLOG_DIR_NAME = 'blog'
_PROJECT_FILENAME = 'project.json'
_STATE_FILENAME = 'pipeline_state.json'
_BACKLOG_FILENAME = 'backlog.json'
_CONTINUITY_FILENAME = 'continuity.json'
_MEMORY_FILENAME = 'editorial_memory.md'
_RUNS_FILENAME = 'runs.jsonl'
_POSTS_DIR_NAME = 'posts'
_STAGES = ('brief', 'research', 'outline', 'draft', 'review')
_TOPIC_STAGE = 'topic'
_TOPIC_PROPOSAL_FILENAME = 'topic_proposal.json'
_DEFAULT_CADENCE_MINUTES = 360
_MIN_CADENCE_MINUTES = 60
_MAX_CADENCE_MINUTES = 10080
_RUN_LEASE_SECONDS = 2 * 60 * 60
_RETRY_DELAY_MINUTES = 30
_MAX_RUN_HISTORY = 512
_MAX_PROJECT_TEXT = 12000
_DEFAULT_TOPIC_ROTATION_SEEDS = (
    '바쁜 일상에서도 무너지지 않는 한 주 계획 세우기',
    '집중이 자주 끊길 때 다시 업무에 몰입하는 방법',
    '작은 지출을 부담 없이 점검하는 월간 습관',
    '가족·동료와 오해 없이 부탁하고 답하는 대화법',
    '새로운 습관을 오래 유지하기 위한 환경 만들기',
)


def _now():
    return datetime.now(KST)


def _blog_root():
    return Path(codex_chat.WORKSPACE_DIR) / _BLOG_DIR_NAME


def _project_path(root):
    return root / _PROJECT_FILENAME


def _state_path(root):
    return root / _STATE_FILENAME


def _backlog_path(root):
    return root / _BACKLOG_FILENAME


def _continuity_path(root):
    return root / _CONTINUITY_FILENAME


def _memory_path(root):
    return root / _MEMORY_FILENAME


def _runs_path(root):
    return root / _RUNS_FILENAME


def _posts_path(root):
    return root / _POSTS_DIR_NAME


def _topic_proposal_path(root):
    return root / _TOPIC_PROPOSAL_FILENAME


def _read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return default
    return value


def _write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    temporary.replace(path)


def _read_jsonl_tail(path, limit=20):
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    items = []
    for line in lines[-max(1, int(limit)):]:
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _append_jsonl(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def _project_defaults():
    return {
        'version': 1,
        'project_id': 'main-blog',
        'name': 'Main blog',
        'enabled': False,
        'language': '한국어',
        'audience': '',
        'style_guide': '',
        'allow_web_research': False,
        'cadence_minutes': _DEFAULT_CADENCE_MINUTES,
        'model': '',
        'reasoning_effort': 'low',
        # Kept as an editorial inspiration list for compatibility.  A model,
        # not deterministic string concatenation, chooses each next topic.
        'topic_rotation_enabled': True,
        'topic_rotation_seeds': list(_DEFAULT_TOPIC_ROTATION_SEEDS),
        'updated_at': normalize_timestamp(None),
    }


def _project_id(value):
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[^a-z0-9._-]+', '-', normalized)
    normalized = re.sub(r'-{2,}', '-', normalized).strip('.-_')
    return normalized[:64]


def _normalize_project(raw, existing=None):
    base = dict(_project_defaults())
    if isinstance(existing, dict):
        base.update(existing)
    if isinstance(raw, dict):
        for key in base:
            if key in raw:
                base[key] = raw[key]
    project_id = _project_id(base.get('project_id')) or 'main-blog'
    try:
        cadence = int(base.get('cadence_minutes') or _DEFAULT_CADENCE_MINUTES)
    except (TypeError, ValueError):
        cadence = _DEFAULT_CADENCE_MINUTES
    cadence = max(_MIN_CADENCE_MINUTES, min(_MAX_CADENCE_MINUTES, cadence))
    # Accept the old daily fields when loading existing projects.  They are
    # deliberately not emitted again, so saving a project migrates it.
    raw = raw if isinstance(raw, dict) else {}
    existing = existing if isinstance(existing, dict) else {}
    if 'topic_rotation_enabled' not in raw:
        if 'daily_topic_enabled' in raw:
            base['topic_rotation_enabled'] = raw['daily_topic_enabled']
        elif 'topic_rotation_enabled' not in existing and 'daily_topic_enabled' in existing:
            base['topic_rotation_enabled'] = existing['daily_topic_enabled']
    if 'topic_rotation_seeds' not in raw:
        if 'daily_topic_seeds' in raw:
            base['topic_rotation_seeds'] = raw['daily_topic_seeds']
        elif 'topic_rotation_seeds' not in existing and 'daily_topic_seeds' in existing:
            base['topic_rotation_seeds'] = existing['daily_topic_seeds']
    raw_seeds = base.get('topic_rotation_seeds')
    if not isinstance(raw_seeds, list):
        raw_seeds = []
    topic_rotation_seeds = []
    for seed in raw_seeds:
        normalized_seed = str(seed or '').strip()
        if normalized_seed and normalized_seed not in topic_rotation_seeds:
            topic_rotation_seeds.append(normalized_seed[:300])
    if not topic_rotation_seeds:
        topic_rotation_seeds = list(_DEFAULT_TOPIC_ROTATION_SEEDS)
    return {
        'version': 1,
        'project_id': project_id,
        'name': str(base.get('name') or project_id).strip()[:120],
        'enabled': bool(base.get('enabled')),
        'language': str(base.get('language') or '한국어').strip()[:40],
        'audience': str(base.get('audience') or '').strip()[:2000],
        'style_guide': str(base.get('style_guide') or '').strip()[:_MAX_PROJECT_TEXT],
        'allow_web_research': bool(base.get('allow_web_research')),
        'cadence_minutes': cadence,
        'model': str(base.get('model') or '').strip()[:80],
        'reasoning_effort': str(base.get('reasoning_effort') or 'low').strip()[:40],
        'topic_rotation_enabled': bool(base.get('topic_rotation_enabled')),
        'topic_rotation_seeds': topic_rotation_seeds[:40],
        'updated_at': normalize_timestamp(None),
    }


def _default_state(project_id):
    return {
        'version': 1,
        'project_id': project_id,
        'stage': 'select',
        'active_post_id': '',
        'active_topic': '',
        'revision': 0,
        'next_run_at': None,
        'in_flight': None,
        'last_run_at': None,
        'last_result': None,
        'last_error': '',
        'completed_post_count': 0,
        'updated_at': normalize_timestamp(None),
    }


def _ensure_scaffold(root, project=None):
    root.mkdir(parents=True, exist_ok=True)
    _posts_path(root).mkdir(parents=True, exist_ok=True)
    if not _project_path(root).exists():
        _write_json_atomic(_project_path(root), _normalize_project(project))
    if not _state_path(root).exists():
        current_project = _read_json(_project_path(root), {}) or {}
        _write_json_atomic(_state_path(root), _default_state(current_project.get('project_id') or 'main-blog'))
    if not _backlog_path(root).exists():
        _write_json_atomic(_backlog_path(root), {'version': 1, 'items': []})
    if not _continuity_path(root).exists():
        _write_json_atomic(_continuity_path(root), {
            'version': 1,
            'facts': [],
            'terms': [],
            'open_loops': [],
            'recent_posts': [],
        })
    if not _memory_path(root).exists():
        _memory_path(root).write_text(
            '# Editorial memory\n\nKeep only durable style, audience, and continuity rules here.\n',
            encoding='utf-8',
        )


def _load_project(root):
    payload = _read_json(_project_path(root))
    return _normalize_project(payload or {}) if isinstance(payload, dict) else None


def _load_state(root, project_id):
    payload = _read_json(_state_path(root), {})
    state = dict(_default_state(project_id))
    if isinstance(payload, dict):
        state.update(payload)
    state['project_id'] = project_id
    state['stage'] = state.get('stage') if state.get('stage') in ('select', _TOPIC_STAGE, *_STAGES) else 'select'
    # State is workspace-local.  Derive its owner from the state root rather
    # than a process-global setting: completion callbacks carry an explicit
    # root and must never make a different Workbench look like its owner.
    workspace_path = str(Path(root).resolve().parent)
    state['workspace_path'] = workspace_path
    state['workspace_scope_id'] = hashlib.sha1(workspace_path.encode('utf-8')).hexdigest()[:12]
    return state


def _save_state(root, state):
    state = dict(state)
    state['updated_at'] = normalize_timestamp(None)
    _write_json_atomic(_state_path(root), state)


def _load_backlog(root):
    payload = _read_json(_backlog_path(root), {'items': []})
    items = payload.get('items') if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    normalized = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            title = item.strip()
            item = {'id': f'item-{index + 1}', 'title': title}
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or item.get('topic') or '').strip()
        if not title:
            continue
        normalized.append({
            **item,
            'id': str(item.get('id') or f'item-{index + 1}').strip()[:80],
            'title': title[:300],
            'status': str(item.get('status') or 'queued').strip().lower(),
        })
    return normalized


def _save_backlog(root, items):
    _write_json_atomic(_backlog_path(root), {'version': 1, 'items': items})


def _migrate_backlog_to_inspirations(root):
    """Turn legacy queued titles into input for the next AI topic choice.

    This intentionally preserves user-provided titles instead of silently
    dropping them, while ensuring that a previously queued title cannot bypass
    the new topic-generation step.
    """
    items = _load_backlog(root)
    changed = False
    for item in items:
        if item.get('status') == 'queued' and item.get('kind') != 'article':
            item['kind'] = 'topic_inspiration'
            item['source'] = item.get('source') or 'legacy_backlog'
            changed = True
    if changed:
        _save_backlog(root, items)
    return items


def _queue_generated_topic(root, proposal, now):
    title = str(proposal.get('title') or '').strip()[:300]
    if not title:
        return False
    items = _load_backlog(root)
    # A completion callback may be retried; title de-duplication makes the
    # transition idempotent without suppressing genuinely later topics.
    if any(item.get('kind') == 'article' and item.get('title') == title
           and item.get('status') not in {'done', 'cancelled'} for item in items):
        return True
    items.append({
        'id': f'ai-topic-{uuid.uuid4().hex[:16]}',
        'title': title,
        'status': 'queued',
        'kind': 'article',
        'source': 'ai_generated',
        'rationale': str(proposal.get('rationale') or '').strip()[:1200],
        'created_at': normalize_timestamp(now),
    })
    _save_backlog(root, items)
    return True


def _discard_topic_proposal(root):
    """Ensure a topic run can only consume the proposal it just requested."""
    try:
        _topic_proposal_path(root).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        _LOGGER.warning('Unable to remove a previous topic proposal', exc_info=True)


def _slug(value):
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[^0-9a-z가-힣]+', '-', normalized)
    normalized = re.sub(r'-{2,}', '-', normalized).strip('-')
    return normalized[:48] or 'untitled'


def _select_topic(root, state):
    if state.get('active_post_id'):
        return state
    items = _load_backlog(root)
    selected = next((item for item in items if item.get('kind') == 'article'
                     and item.get('status') not in {'done', 'cancelled'}), None)
    if not selected:
        return state
    post_id = f"{_now().strftime('%Y%m%d')}-{_slug(selected['title'])}"
    candidate = post_id
    suffix = 2
    while (_posts_path(root) / candidate).exists():
        candidate = f'{post_id}-{suffix}'
        suffix += 1
    post_dir = _posts_path(root) / candidate
    post_dir.mkdir(parents=True, exist_ok=True)
    selected['status'] = 'in_progress'
    selected['selected_at'] = normalize_timestamp(None)
    _save_backlog(root, items)
    state['stage'] = 'brief'
    state['active_post_id'] = candidate
    state['active_topic'] = selected['title']
    state['active_backlog_id'] = selected['id']
    return state


def _post_dir(root, post_id):
    normalized = str(post_id or '').strip()
    if not normalized or normalized in {'.', '..'} or '/' in normalized or '\\' in normalized:
        return None
    return _posts_path(root) / normalized


def _stage_files(root, state):
    post_dir = _post_dir(root, state.get('active_post_id'))
    post_prefix = f'blog/posts/{state.get("active_post_id")}'
    if post_dir is None:
        return []
    files = {
        _TOPIC_STAGE: [
            'blog/project.json', 'blog/continuity.json', 'blog/backlog.json',
            'blog/editorial_memory.md', 'blog/topic_proposal.json',
        ],
        'brief': [
            'blog/project.json', 'blog/continuity.json', 'blog/backlog.json',
            f'{post_prefix}/brief.md',
        ],
        'research': [
            'blog/project.json', 'blog/continuity.json', f'{post_prefix}/brief.md',
            f'{post_prefix}/research.md', f'{post_prefix}/sources.json',
        ],
        'outline': [
            'blog/project.json', 'blog/continuity.json', f'{post_prefix}/brief.md',
            f'{post_prefix}/research.md', f'{post_prefix}/outline.md',
        ],
        'draft': [
            'blog/project.json', 'blog/continuity.json', 'blog/editorial_memory.md',
            f'{post_prefix}/brief.md', f'{post_prefix}/outline.md', f'{post_prefix}/draft.md',
        ],
        'review': [
            'blog/project.json', 'blog/continuity.json', 'blog/editorial_memory.md',
            f'{post_prefix}/research.md', f'{post_prefix}/outline.md', f'{post_prefix}/draft.md',
            f'{post_prefix}/review.md', f'{post_prefix}/final.md',
        ],
    }
    return files.get(state.get('stage'), [])


def _build_prompt(project, state):
    stage = state.get('stage')
    post_id = state.get('active_post_id')
    post_prefix = f'blog/posts/{post_id}'
    files = _stage_files(_blog_root(), state)
    allowed = '\n'.join(f'- {item}' for item in files)
    common = (
        'You are one stage in a durable blog-writing pipeline. Work only inside the '
        '`blog/` directory and only on the files listed below. Do not inspect chat '
        'history, the repository, or unrelated files. Do not edit pipeline_state.json '
        'or runs.jsonl; the Workbench updates those files after completion. Keep the '
        'result concise and practical. Do not install packages, run builds, or make '
        'external changes.\n\n'
        f'Project language: {project.get("language")}.\n'
        f'Active post: {post_id}.\n'
        f'Current topic: {state.get("active_topic")}.\n\n'
        'Allowed files for this stage:\n'
        f'{allowed}\n\n'
    )
    if stage == _TOPIC_STAGE:
        task = (
            'Read project.json, continuity.json, editorial_memory.md, and backlog.json. '
            'Generate one timely, specific next article topic that fits the project. '
            'Favor broadly useful everyday themes such as work habits, communication, '
            'healthful routines, personal finance basics, learning, home life, and '
            'relationships. Rotate across these areas over time. Do not make AI, '
            'software, or technology the default subject; use them only when the '
            'project context or an inspiration clearly calls for them. '
            'does not repeat completed or in-progress articles. Existing queued entries '
            'are inspirations, not fixed titles: improve, combine, or replace them as '
            'appropriate. Create or replace blog/topic_proposal.json as valid JSON only, '
            'with exactly these useful fields: "title" (a concrete Korean article title, '
            'max 120 characters) and "rationale" (one short Korean paragraph). Do not '
            'write an article, brief, or markdown file in this stage.'
        )
    elif stage == 'brief':
        task = (
            'Read project.json, continuity.json, and backlog.json. Create or replace '
            f'blog/posts/{post_id}/brief.md with a focused brief: reader problem, '
            'promise, angle, key claims to validate, and a 5-part target structure. '
            'Do not research or draft the full article. Target 300-500 words.'
        )
    elif stage == 'research':
        research_mode = (
            'Web research is allowed only because project.json enables it; use a small '
            'number of authoritative sources and record URLs in sources.json.'
            if project.get('allow_web_research') else
            'Web research is disabled. Use only the supplied project context and clearly '
            'mark claims that need later verification; do not invent citations.'
        )
        task = (
            f'Read {post_prefix}/brief.md and continuity.json. Create or replace '
            f'{post_prefix}/research.md with only the evidence needed for the '
            f'article, and create or replace {post_prefix}/sources.json. '
            f'{research_mode} Keep the research memo under 700 words.'
        )
    elif stage == 'outline':
        task = (
            f'Read {post_prefix}/brief.md, {post_prefix}/research.md, and continuity.json. '
            f'Create or replace {post_prefix}/outline.md with a lean section '
            'outline, thesis, transitions, and a note for unresolved claims. Do not '
            'write article prose. Target 250-450 words.'
        )
    elif stage == 'draft':
        task = (
            f'Read {post_prefix}/brief.md, {post_prefix}/outline.md, project.json, '
            'continuity.json, and editorial_memory.md. Create or replace '
            f'{post_prefix}/draft.md as a complete blog draft. Follow the '
            'style guide, avoid unsupported claims, and keep headings and paragraphs '
            'readable. Do not add a long preamble or explain your process.'
        )
    else:
        task = (
            f'Read {post_prefix}/draft.md, {post_prefix}/outline.md, {post_prefix}/research.md, '
            'project.json, continuity.json, and editorial_memory.md. Create or replace '
            f'{post_prefix}/review.md with concise factual, continuity, structure, '
            f'and style findings. Then create or replace {post_prefix}/final.md '
            'with the corrected publishable article. Update continuity.json only with '
            'durable facts, terms, or open loops, keeping it compact (under 2,000 words). '
            'Do not claim publication or external verification.'
        )
    return common + task


def _account_identity_material(context):
    identity = codex_chat._read_auth_identity(context.get('codex_home'))
    provider_id = str(identity.get('provider_account_id') or '').strip()
    if provider_id:
        return f'provider-account:{provider_id}'
    try:
        auth_bytes = (Path(context['codex_home']) / 'auth.json').read_bytes()
    except OSError:
        auth_bytes = str(Path(context.get('codex_home') or '').resolve()).encode('utf-8')
    return 'auth-fingerprint:' + hashlib.sha256(auth_bytes).hexdigest()


def _claim_path(context, project_id):
    material = f'{_account_identity_material(context)}:blog-project:{project_id}'
    key = hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]
    return Path(codex_chat.CODEX_ACCOUNTS_DIR).parent / 'blog_pipeline' / f'{key}.json'


def _claim_global(context, project, run_id, now, force=False):
    path = _claim_path(context, project['project_id'])
    with codex_chat._acquire_path_file_lock(path):
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        active = payload.get('active') if isinstance(payload.get('active'), dict) else None
        active_until = parse_timestamp(active.get('lease_until')) if active else None
        if active and active_until and active_until > now:
            return False, 'project_busy', path
        next_allowed = parse_timestamp(payload.get('next_allowed_at'))
        if not force and next_allowed and next_allowed > now:
            return False, 'not_due', path
        payload.update({
            'version': 1,
            'project_id': project['project_id'],
            'updated_at': normalize_timestamp(now),
            'active': {
                'run_id': run_id,
                'workspace_scope_id': codex_chat._WORKSPACE_SCOPE_ID,
                'workspace_path': str(codex_chat.WORKSPACE_DIR),
                'started_at': normalize_timestamp(now),
                'lease_until': normalize_timestamp(now + timedelta(seconds=_RUN_LEASE_SECONDS)),
                'stream_id': '',
            },
        })
        _write_json_atomic(path, payload)
    return True, '', path


def _update_claim_stream(claim_path, run_id, stream_id):
    if not claim_path:
        return
    with codex_chat._acquire_path_file_lock(claim_path):
        payload = _read_json(claim_path, {})
        active = payload.get('active') if isinstance(payload, dict) else None
        if not isinstance(active, dict) or active.get('run_id') != run_id:
            return
        active['stream_id'] = stream_id
        payload['updated_at'] = normalize_timestamp(None)
        _write_json_atomic(claim_path, payload)


def _finish_claim(claim_path, project, run_id, succeeded, now):
    if not claim_path:
        return
    with codex_chat._acquire_path_file_lock(claim_path):
        payload = _read_json(claim_path, {})
        active = payload.get('active') if isinstance(payload, dict) else None
        if not isinstance(active, dict) or active.get('run_id') != run_id:
            return
        payload['active'] = None
        payload['last_run_id'] = run_id
        payload['last_completed_at'] = normalize_timestamp(now)
        payload['last_status'] = 'completed' if succeeded else 'failed'
        payload['next_allowed_at'] = normalize_timestamp(
            now + timedelta(minutes=(project['cadence_minutes'] if succeeded else _RETRY_DELAY_MINUTES))
        )
        payload['updated_at'] = normalize_timestamp(now)
        _write_json_atomic(claim_path, payload)


def _normalize_tokens(token_usage):
    usage = token_usage if isinstance(token_usage, dict) else {}
    return {
        'input_tokens': int(usage.get('input_tokens') or 0),
        'cached_input_tokens': int(usage.get('cached_input_tokens') or 0),
        'output_tokens': int(usage.get('output_tokens') or 0),
        'reasoning_output_tokens': int(usage.get('reasoning_output_tokens') or 0),
        'total_tokens': int(usage.get('total_tokens') or 0),
    }


def _status_payload(root=None):
    root = Path(root or _blog_root())
    project_payload = _read_json(_project_path(root))
    if not isinstance(project_payload, dict):
        return {
            'configured': False,
            'enabled': False,
            'path': str(root),
            'project': None,
            'state': None,
            'recent_runs': [],
        }
    project = _normalize_project(project_payload)
    state = _load_state(root, project['project_id'])
    stage = str(state.get('stage') or 'select')
    stage_number = _STAGES.index(stage) + 1 if stage in _STAGES else 0
    completed_stage_count = max(0, stage_number - 1)
    in_flight = state.get('in_flight') if isinstance(state.get('in_flight'), dict) else None
    last_result = state.get('last_result') if isinstance(state.get('last_result'), dict) else {}
    queued_count = sum(
        1 for item in _load_backlog(root)
        if item.get('kind') == 'article' and item.get('status') not in {'done', 'cancelled'}
    )
    inspiration_count = sum(
        1 for item in _load_backlog(root)
        if item.get('kind') == 'topic_inspiration' and item.get('status') not in {'done', 'cancelled'}
    )
    dashboard = {
        'current_topic': str(state.get('active_topic') or ''),
        'current_stage': stage,
        'current_stage_number': stage_number,
        'completed_stage_count': completed_stage_count,
        'total_stage_count': len(_STAGES),
        'progress_percent': int((completed_stage_count / len(_STAGES)) * 100),
        'is_running': bool(in_flight and in_flight.get('run_id')),
        'running_stage': str((in_flight or {}).get('stage') or ''),
        'completed_post_count': max(0, int(state.get('completed_post_count') or 0)),
        'backlog_count': queued_count,
        'topic_inspiration_count': inspiration_count,
        'last_status': str(last_result.get('status') or ''),
        'last_completed_at': last_result.get('completed_at') or state.get('last_run_at'),
        'last_token_usage': _normalize_tokens(last_result.get('token_usage')),
    }
    return {
        'configured': True,
        'enabled': bool(project.get('enabled')),
        'path': str(root),
        'workspace': {
            'path': state['workspace_path'],
            'scope_id': state['workspace_scope_id'],
        },
        'project': project,
        'state': state,
        'backlog_count': dashboard['backlog_count'],
        'dashboard': dashboard,
        'recent_runs': _read_jsonl_tail(_runs_path(root)),
        'artifacts': sorted(
            str(path.relative_to(root)).replace('\\', '/')
            for path in root.rglob('*')
            if path.is_file() and path.name not in {_STATE_FILENAME, _RUNS_FILENAME}
        )[:200],
    }


def get_blog_pipeline_status():
    return _status_payload()


def configure_blog_project(payload):
    if not isinstance(payload, dict):
        raise ValueError('블로그 설정은 JSON 객체여야 합니다.')
    root = _blog_root()
    root.mkdir(parents=True, exist_ok=True)
    with codex_chat._acquire_path_file_lock(_project_path(root)):
        current = _read_json(_project_path(root), {})
        project = _normalize_project(payload, existing=current if isinstance(current, dict) else None)
        previous_project_id = _project_id(current.get('project_id')) if isinstance(current, dict) else ''
        state = _load_state(root, previous_project_id or project['project_id'])
        if state.get('in_flight') and project['project_id'] != state.get('project_id'):
            raise ValueError('실행 중인 프로젝트의 project_id는 변경할 수 없습니다.')
        if previous_project_id and previous_project_id != project['project_id']:
            state = _default_state(project['project_id'])
        _ensure_scaffold(root, project)
        _write_json_atomic(_project_path(root), project)
        if isinstance(payload.get('backlog'), list):
            items = []
            for index, item in enumerate(payload['backlog']):
                if isinstance(item, str):
                    item = {'id': f'item-{index + 1}', 'title': item}
                if not isinstance(item, dict):
                    continue
                title = str(item.get('title') or item.get('topic') or '').strip()
                if title:
                    items.append({
                        **item,
                        'id': str(item.get('id') or f'item-{index + 1}'),
                        'title': title,
                        # Newly configured titles are creative direction for
                        # the model, not a way around AI topic selection.
                        'kind': 'topic_inspiration',
                        'status': str(item.get('status') or 'queued'),
                    })
            _save_backlog(root, items)
        state['project_id'] = project['project_id']
        _save_state(root, state)
    return _status_payload(root)


def _start_pipeline_run(force=False, account_id=None):
    root = _blog_root()
    if not _project_path(root).exists():
        return {'started': False, 'reason': 'not_configured'}
    project = _load_project(root)
    if not project or not project.get('enabled'):
        return {'started': False, 'reason': 'disabled'}
    account_id = account_id or codex_chat.get_active_account_id()
    context = codex_chat._account_storage_context(account_id)
    if context is None:
        return {'started': False, 'reason': 'account_not_found'}
    if codex_chat._account_has_active_codex_stream(context['account']['id']):
        return {'started': False, 'reason': 'account_busy'}
    if codex_chat.CODEX_REQUIRE_ACCOUNT_LOGIN and not codex_chat._codex_home_has_auth(context['codex_home']):
        return {'started': False, 'reason': 'account_login_required'}

    run_id = uuid.uuid4().hex
    now = _now()
    claim_path = None
    with codex_chat._acquire_path_file_lock(_state_path(root)):
        state = _load_state(root, project['project_id'])
        _migrate_backlog_to_inspirations(root)
        in_flight = state.get('in_flight')
        if isinstance(in_flight, dict) and in_flight.get('run_id'):
            started_at = parse_timestamp(in_flight.get('started_at'))
            if started_at and started_at + timedelta(seconds=_RUN_LEASE_SECONDS) <= now:
                stale_run_id = str(in_flight.get('run_id'))
                stale_claim_path = in_flight.get('claim_path')
                state['in_flight'] = None
                state['last_error'] = 'stale_run_recovered'
                state['next_run_at'] = normalize_timestamp(
                    now + timedelta(minutes=_RETRY_DELAY_MINUTES)
                )
                state['last_result'] = {
                    'run_id': stale_run_id,
                    'status': 'recovered',
                    'completed_at': normalize_timestamp(now),
                }
                _save_state(root, state)
                _finish_claim(
                    Path(stale_claim_path) if stale_claim_path else None,
                    project,
                    stale_run_id,
                    False,
                    now,
                )
                return {'started': False, 'reason': 'stale_run_recovered'}
            return {'started': False, 'reason': 'run_in_flight', 'run_id': in_flight.get('run_id')}
        next_run_at = parse_timestamp(state.get('next_run_at'))
        if not force and next_run_at and next_run_at > now:
            return {'started': False, 'reason': 'not_due', 'next_run_at': state.get('next_run_at')}
        claimed, reason, claim_path = _claim_global(context, project, run_id, now, force=force)
        if not claimed:
            return {'started': False, 'reason': reason, 'claim_path': str(claim_path)}
        if state.get('stage') == 'select':
            # A validated proposal is consumed on the next run.  If none is
            # ready, topic generation runs first and has no post directory.
            if any(item.get('kind') == 'article' and item.get('status') not in {'done', 'cancelled'}
                   for item in _load_backlog(root)):
                state = _select_topic(root, state)
            else:
                state['stage'] = _TOPIC_STAGE
        # topic_proposal.json is an output artifact, not durable pipeline
        # state.  Leaving it in place makes a later manual run accept the
        # previous run's title if the new model run does not replace it.
        if state.get('stage') == _TOPIC_STAGE:
            _discard_topic_proposal(root)
        elif state.get('stage') != _TOPIC_STAGE:
            state = _select_topic(root, state)
        if state.get('stage') == 'select' or (
                state.get('stage') != _TOPIC_STAGE and not state.get('active_post_id')):
            _finish_claim(claim_path, project, run_id, False, now)
            _save_state(root, state)
            return {'started': False, 'reason': 'backlog_empty'}
        stage = state['stage']
        post_id = state.get('active_post_id') or ''
        state['in_flight'] = {
            'run_id': run_id,
            'stage': stage,
            'post_id': post_id,
            'started_at': normalize_timestamp(now),
            'stream_id': '',
            'claim_path': str(claim_path),
        }
        state['next_run_at'] = normalize_timestamp(now + timedelta(minutes=project['cadence_minutes']))
        state['last_error'] = ''
        _save_state(root, state)

    session = None
    try:
        session = codex_chat.create_session(
            title=f'Blog pipeline · {post_id} · {stage}',
            metadata={
                'session_type': 'blog_pipeline',
                'internal': True,
                'blog_project_id': project['project_id'],
                'blog_run_id': run_id,
            },
        )
        stream = codex_chat.create_codex_stream(
            session['id'],
            _build_prompt(project, state),
            model_override=project.get('model') or None,
            reasoning_override=project.get('reasoning_effort') or None,
            account_id=context['account']['id'],
            usage_operation='blog_pipeline',
            operation_metadata={
                'project_id': project['project_id'],
                'run_id': run_id,
                'stage': stage,
                'post_id': post_id,
                'blog_root': str(root),
                'claim_path': str(claim_path),
                'workspace_path': str(Path(codex_chat.WORKSPACE_DIR).resolve()),
                'workspace_scope_id': codex_chat._WORKSPACE_SCOPE_ID,
            },
        )
    except Exception as exc:
        _LOGGER.exception('Blog pipeline run failed to start')
        record_blog_pipeline_completion({
            'project_id': project['project_id'],
            'run_id': run_id,
            'stage': stage,
            'post_id': post_id,
            'blog_root': str(root),
            'claim_path': str(claim_path),
        }, False, str(exc), {})
        if session:
            try:
                codex_chat.delete_session(session['id'])
            except Exception:
                _LOGGER.debug('Failed to remove failed blog pipeline session', exc_info=True)
        return {'started': False, 'reason': 'start_failed', 'error': str(exc)[:1000]}

    with codex_chat._acquire_path_file_lock(_state_path(root)):
        current = _load_state(root, project['project_id'])
        if isinstance(current.get('in_flight'), dict) and current['in_flight'].get('run_id') == run_id:
            current['in_flight']['stream_id'] = stream.get('id') or ''
            _save_state(root, current)
    _update_claim_stream(claim_path, run_id, stream.get('id') or '')
    return {
        'started': True,
        'run_id': run_id,
        'stream_id': stream.get('id'),
        'stage': stage,
        'post_id': post_id,
        'project_id': project['project_id'],
    }


def run_blog_pipeline(force=False, account_id=None):
    return _start_pipeline_run(force=bool(force), account_id=account_id)


def _mark_backlog_done(root, state, now):
    backlog_id = str(state.get('active_backlog_id') or '').strip()
    if not backlog_id:
        return
    items = _load_backlog(root)
    changed = False
    for item in items:
        if item.get('id') != backlog_id:
            continue
        item['status'] = 'done'
        item['completed_at'] = normalize_timestamp(now)
        item['post_id'] = state.get('active_post_id') or ''
        changed = True
        break
    if changed:
        _save_backlog(root, items)


def record_blog_pipeline_completion(operation, succeeded, error='', token_usage=None):
    if not isinstance(operation, dict):
        return False
    root = Path(str(operation.get('blog_root') or _blog_root())).resolve()
    project_id = _project_id(operation.get('project_id'))
    run_id = str(operation.get('run_id') or '').strip()
    if not project_id or not run_id:
        return False
    project = _load_project(root)
    if not project or project.get('project_id') != project_id:
        return False
    now = _now()
    with codex_chat._acquire_path_file_lock(_state_path(root)):
        state = _load_state(root, project_id)
        expected_workspace_path = str((root.parent if root.name == _BLOG_DIR_NAME else root).resolve())
        expected_workspace_scope = hashlib.sha1(
            expected_workspace_path.encode('utf-8')
        ).hexdigest()[:12]
        if (operation.get('workspace_path') and
                str(operation.get('workspace_path')) != expected_workspace_path):
            _LOGGER.warning('Ignoring blog completion from a different workspace: %s', operation.get('workspace_path'))
            return False
        if (operation.get('workspace_scope_id') and
                str(operation.get('workspace_scope_id')) != expected_workspace_scope):
            _LOGGER.warning('Ignoring blog completion with a different workspace scope: %s', operation.get('workspace_scope_id'))
            return False
        in_flight = state.get('in_flight') if isinstance(state.get('in_flight'), dict) else {}
        if in_flight.get('run_id') != run_id:
            return state.get('last_result', {}).get('run_id') == run_id if isinstance(state.get('last_result'), dict) else False
        stage = str(operation.get('stage') or in_flight.get('stage') or state.get('stage') or '').strip()
        state['in_flight'] = None
        state['last_run_at'] = normalize_timestamp(now)
        state['last_error'] = '' if succeeded else str(error or '')[:1000]
        state['last_result'] = {
            'run_id': run_id,
            'stage': stage,
            'post_id': str(operation.get('post_id') or in_flight.get('post_id') or ''),
            'status': 'completed' if succeeded else 'failed',
            'completed_at': normalize_timestamp(now),
            'token_usage': _normalize_tokens(token_usage),
        }
        if succeeded and stage == _TOPIC_STAGE:
            proposal = _read_json(_topic_proposal_path(root), {})
            if not isinstance(proposal, dict) or not _queue_generated_topic(root, proposal, now):
                succeeded = False
                state['last_error'] = 'topic_proposal_invalid'
                state['last_result']['status'] = 'failed'
                state['last_result']['error'] = 'topic_proposal_invalid'
                state['next_run_at'] = normalize_timestamp(now + timedelta(minutes=_RETRY_DELAY_MINUTES))
            else:
                state['stage'] = 'select'
                state['revision'] = int(state.get('revision') or 0) + 1
        elif succeeded and stage in _STAGES:
            if stage == 'review':
                _mark_backlog_done(root, state, now)
                state['completed_post_count'] = int(state.get('completed_post_count') or 0) + 1
                state['stage'] = 'select'
                state['active_post_id'] = ''
                state['active_topic'] = ''
                state.pop('active_backlog_id', None)
            else:
                state['stage'] = _STAGES[_STAGES.index(stage) + 1]
            state['revision'] = int(state.get('revision') or 0) + 1
        else:
            state['next_run_at'] = normalize_timestamp(now + timedelta(minutes=_RETRY_DELAY_MINUTES))
        _save_state(root, state)
        _append_jsonl(_runs_path(root), {
            'run_id': run_id,
            'project_id': project_id,
            'stage': stage,
            'post_id': operation.get('post_id') or in_flight.get('post_id') or '',
            'status': 'completed' if succeeded else 'failed',
            'at': normalize_timestamp(now),
            'token_usage': _normalize_tokens(token_usage),
            'error': '' if succeeded else str(error or '')[:1000],
        })
    claim_path = operation.get('claim_path')
    _finish_claim(Path(claim_path) if claim_path else None, project, run_id, bool(succeeded), now)
    return True
