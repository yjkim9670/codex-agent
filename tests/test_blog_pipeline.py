from datetime import datetime
import json
from pathlib import Path

import pytest

from codex_agent.services import blog_pipeline
from codex_agent.services import codex_chat


@pytest.fixture
def blog_environment(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    shared = tmp_path / 'shared-account-state'
    workspace.mkdir()
    (shared / 'accounts').mkdir(parents=True)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', workspace)
    monkeypatch.setattr(codex_chat, 'CODEX_ACCOUNTS_DIR', shared / 'accounts')
    monkeypatch.setattr(codex_chat, 'CODEX_REQUIRE_ACCOUNT_LOGIN', False)
    monkeypatch.setattr(codex_chat, 'get_active_account_id', lambda: 'default')
    monkeypatch.setattr(
        codex_chat,
        '_account_storage_context',
        lambda _account_id=None: {
            'account': {'id': 'default', 'label': 'Default'},
            'codex_home': tmp_path / 'codex-home',
        },
    )
    monkeypatch.setattr(codex_chat, '_account_has_active_codex_stream', lambda _account_id: False)
    return workspace


def test_blog_pipeline_is_disabled_until_configured(blog_environment):
    status = blog_pipeline.get_blog_pipeline_status()

    assert status['configured'] is False
    assert status['enabled'] is False
    assert blog_pipeline.run_blog_pipeline(force=True)['reason'] == 'not_configured'


def test_usage_panel_advances_the_same_blog_pipeline(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'usage-series',
        'enabled': True,
        'backlog': ['Usage 패널에서 시작하는 글'],
    })
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'blog-session'})
    monkeypatch.setattr(
        codex_chat, 'create_codex_stream',
        lambda *_args, **_kwargs: {'id': 'usage-blog-stream'},
    )

    result = codex_chat.submit_usage_keepalive(account_id='default')

    assert result['submitted'] is True
    assert result['stream']['id'] == 'usage-blog-stream'
    assert result['blog_pipeline']['stage'] == 'topic'
    state = blog_pipeline.get_blog_pipeline_status()['state']
    assert state['in_flight']['stage'] == 'topic'


@pytest.mark.parametrize('automatic', [True, False])
def test_lightweight_tasks_only_run_blog(blog_environment, monkeypatch, automatic):
    from codex_agent.services import metadata_sync

    monkeypatch.setattr(metadata_sync, 'preview', lambda: pytest.fail('Unexpected document inspection'))
    monkeypatch.setattr(metadata_sync.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected sync invocation'))
    calls = []

    def blog(**kwargs):
        calls.append(kwargs)
        return {'started': True, 'stream_id': 'blog-stream'}

    monkeypatch.setattr(blog_pipeline, 'run_blog_pipeline', blog)
    result = codex_chat._run_usage_blog_pipeline('default', automatic=automatic)
    assert calls == [{'force': not automatic, 'account_id': 'default'}]
    assert result['submitted'] is True
    assert result['stream']['id'] == 'blog-stream'
    assert 'metadata_sync' not in result


def test_blog_submission_preserves_automatic_window_claim(blog_environment, monkeypatch):
    snapshot_path = blog_environment / 'usage.json'
    snapshot = {'usage_keepalive': {'last_mode': 'automatic', 'last_status': 'queued',
                                  'automatic_cycle_targets': {'five_hour': 'reserved-window'}}}
    context = {'account': {'id': 'default'}, 'account_usage_snapshot_path': snapshot_path}
    monkeypatch.setattr(codex_chat, '_account_storage_context', lambda _: context)
    monkeypatch.setattr(codex_chat, '_load_account_usage_snapshot', lambda _: snapshot)
    monkeypatch.setattr(codex_chat, '_record_automatic_usage_refresh_history', lambda *a: None)
    monkeypatch.setattr(codex_chat, '_run_usage_blog_pipeline', lambda *a, **kw: {
        'submitted': True, 'stream': {'id': 'blog-stream'},
    })
    codex_chat._start_reserved_automatic_usage_blog('default')
    saved = json.loads(snapshot_path.read_text())['usage_keepalive']
    assert saved['last_status'] == 'submitted'
    assert saved['automatic_cycle_targets'] == {'five_hour': 'reserved-window'}
    assert saved['last_stream_id'] == 'blog-stream'
    assert 'last_metadata_sync' not in saved


def test_automatic_usage_reservation_requires_an_enabled_blog(blog_environment, monkeypatch):
    context = {'account': {'id': 'default'}, 'codex_home': blog_environment.parent / 'codex-home'}
    snapshot = {'five_hour': {'used_percent': 0, 'resets_at': '2026-09-19T17:00:00+09:00'}}
    monkeypatch.setattr(codex_chat, '_account_has_active_codex_stream', lambda _account_id: False)

    assert codex_chat._reserve_automatic_usage_blog_locked(context, snapshot)['reason'] == 'not_configured'

    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'automatic-series', 'enabled': True, 'backlog': ['자동 글'],
    })
    monkeypatch.setattr(codex_chat, '_usage_keepalive_global_claim', lambda *_args: (True, ''))
    result = codex_chat._reserve_automatic_usage_blog_locked(context, snapshot)

    assert result['submitted'] is True
    assert snapshot['usage_keepalive']['automatic_cycle_targets']['five_hour'].startswith('five_hour:zero-window:')


def test_blog_pipeline_advances_one_stage_and_records_tokens(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'series-a',
        'enabled': True,
        'cadence_minutes': 60,
        'backlog': ['첫 번째 글의 주제'],
    })
    monkeypatch.setattr(
        codex_chat,
        'create_session',
        lambda **_kwargs: {'id': 'blog-session'},
    )
    monkeypatch.setattr(
        codex_chat,
        'create_codex_stream',
        lambda *_args, **_kwargs: {'id': 'blog-stream'},
    )

    started = blog_pipeline.run_blog_pipeline(force=True)
    assert started['started'] is True
    assert started['stage'] == 'topic'

    in_flight = blog_pipeline.get_blog_pipeline_status()['state']['in_flight']
    assert in_flight['stream_id'] == 'blog-stream'

    assert blog_pipeline.record_blog_pipeline_completion(
        {
            'project_id': 'series-a',
            'run_id': started['run_id'],
            'stage': 'topic',
            'post_id': started['post_id'],
            'blog_root': str(blog_environment / 'blog'),
            'claim_path': str(
                    blog_pipeline._claim_path(
                        {'codex_home': blog_environment.parent / 'codex-home', 'account': {'id': 'default'}},
                    'series-a',
                )
            ),
        },
        True,
        token_usage={'input_tokens': 100, 'output_tokens': 25, 'total_tokens': 125},
    ) is True

    # The topic-stage model output is the sole source of the next article
    # title.  Legacy backlog entries are only inspirations.
    (blog_environment / 'blog' / 'topic_proposal.json').write_text(
        json.dumps({'title': '퇴근 후 15분으로 다음 날을 준비하는 방법', 'rationale': '독자에게 실용적입니다.'}),
        encoding='utf-8',
    )
    # Re-run completion now that the model artifact exists.  The first call
    # above intentionally exercises invalid-proposal recovery.
    state = blog_pipeline.get_blog_pipeline_status()['state']
    assert state['last_error'] == 'topic_proposal_invalid'
    started = blog_pipeline.run_blog_pipeline(force=True)
    assert started['stage'] == 'topic'
    (blog_environment / 'blog' / 'topic_proposal.json').write_text(
        json.dumps({'title': '퇴근 후 15분으로 다음 날을 준비하는 방법', 'rationale': '독자에게 실용적입니다.'}),
        encoding='utf-8',
    )
    assert blog_pipeline.record_blog_pipeline_completion(
        {
            'project_id': 'series-a', 'run_id': started['run_id'], 'stage': 'topic',
                'post_id': '', 'blog_root': str(blog_environment / 'blog'),
                'claim_path': str(blog_pipeline._claim_path(
                    {'codex_home': blog_environment.parent / 'codex-home', 'account': {'id': 'default'}}, 'series-a')),
        }, True,
    ) is True
    started = blog_pipeline.run_blog_pipeline(force=True)
    assert started['stage'] == 'brief'
    (blog_environment / 'blog' / 'posts' / started['post_id'] / 'brief.md').write_text('A focused brief')
    assert blog_pipeline.record_blog_pipeline_completion({
        'project_id': 'series-a', 'run_id': started['run_id'], 'stage': 'brief',
        'post_id': started['post_id'], 'blog_root': str(blog_environment / 'blog'),
        'claim_path': str(blog_pipeline._claim_path(
            {'codex_home': blog_environment.parent / 'codex-home', 'account': {'id': 'default'}}, 'series-a')),
    }, True, token_usage={'input_tokens': 100, 'output_tokens': 25, 'total_tokens': 125}) is True

    status = blog_pipeline.get_blog_pipeline_status()
    assert status['state']['in_flight'] is None
    assert status['state']['stage'] == 'research'
    assert status['recent_runs'][-1]['token_usage']['total_tokens'] == 125
    assert status['dashboard'] == {
        'current_topic': '퇴근 후 15분으로 다음 날을 준비하는 방법',
        'current_stage': 'research',
        'current_stage_number': 3,
        'completed_stage_count': 2,
        'total_stage_count': 6,
        'progress_percent': 33,
        'is_running': False,
        'running_stage': '',
        'completed_post_count': 0,
        'backlog_count': 1,
        'topic_inspiration_count': 1,
        'last_status': 'completed',
        'last_completed_at': status['state']['last_result']['completed_at'],
        'last_token_usage': {
            'input_tokens': 100,
            'cached_input_tokens': 0,
            'output_tokens': 25,
            'reasoning_output_tokens': 0,
            'total_tokens': 125,
        },
    }


def test_topic_run_discards_stale_proposal_before_manual_submission(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'fresh-topic', 'enabled': True, 'backlog': ['이전 참고 주제'],
    })
    proposal_path = blog_environment / 'blog' / 'topic_proposal.json'
    proposal_path.write_text(
        json.dumps({'title': '이전 실행의 주제', 'rationale': '남은 파일입니다.'}),
        encoding='utf-8',
    )
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'blog-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_args, **_kwargs: {'id': 'blog-stream'})

    started = blog_pipeline.run_blog_pipeline(force=True)

    assert started['stage'] == 'topic'
    assert not proposal_path.exists()


def test_pipeline_uses_ai_topic_before_and_after_each_article(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'rotation-series',
        'enabled': True,
        'topic_rotation_seeds': ['업무 기록을 남기는 방법'],
        'backlog': ['첫 글'],
    })
    fixed_now = datetime(2026, 9, 20, 9, 0, tzinfo=blog_pipeline.KST)
    monkeypatch.setattr(blog_pipeline, '_now', lambda: fixed_now)
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'blog-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_args, **_kwargs: {'id': 'blog-stream'})

    started = blog_pipeline.run_blog_pipeline(force=True)

    assert started['started'] is True
    assert started['stage'] == 'topic'
    (blog_environment / 'blog' / 'topic_proposal.json').write_text(
        json.dumps({'title': '냉장고를 비우기 전에 식단을 정리하는 간단한 순서', 'rationale': '연속성을 반영했습니다.'}),
        encoding='utf-8',
    )
    backlog = blog_pipeline._load_backlog(blog_environment / 'blog')
    assert len(backlog) == 1
    claim_path = str(blog_pipeline._claim_path(
        {'codex_home': blog_environment.parent / 'codex-home', 'account': {'id': 'default'}},
        'rotation-series',
    ))

    assert blog_pipeline.record_blog_pipeline_completion({
        'project_id': 'rotation-series', 'run_id': started['run_id'], 'stage': 'topic',
        'post_id': '', 'blog_root': str(blog_environment / 'blog'), 'claim_path': claim_path,
    }, True)
    started = blog_pipeline.run_blog_pipeline(force=True)
    for stage in ('brief', 'research', 'outline', 'draft', 'review'):
        for name in blog_pipeline._required_outputs(stage, started['post_id']):
            (blog_environment / 'blog' / name).write_text('{"verified":true,"pending_claims":[]}' if name.endswith('review.json') else '[{"title":"source","url":"https://example.com/evidence"}]' if name.endswith('sources.json') else '{}' if name.endswith('.json') else 'stage output')
        assert blog_pipeline.record_blog_pipeline_completion({
            'project_id': 'rotation-series',
            'run_id': started['run_id'],
            'stage': stage,
            'post_id': started['post_id'],
            'blog_root': str(blog_environment / 'blog'),
            'claim_path': claim_path,
        }, True)
        if stage != 'review':
            started = blog_pipeline.run_blog_pipeline(force=True)

    backlog = blog_pipeline._load_backlog(blog_environment / 'blog')
    assert [item for item in backlog if item.get('source') == 'completion_rotation'] == []
    assert blog_pipeline.get_blog_pipeline_status()['state']['completed_post_count'] == 1
    assert blog_pipeline.run_blog_pipeline(force=True)['stage'] == 'topic'


def test_blog_claim_is_shared_across_workbenches(blog_environment):
    project = blog_pipeline._normalize_project({'project_id': 'shared-series', 'enabled': True})
    context = {
        'account': {'id': 'local-account-a'},
        'codex_home': blog_environment.parent / 'same-codex-home',
    }
    now = datetime(2026, 9, 19, 12, 0, tzinfo=blog_pipeline.KST)

    first = blog_pipeline._claim_global(context, project, 'run-a', now, force=False)
    second = blog_pipeline._claim_global(
        {**context, 'account': {'id': 'local-account-b'}},
        project,
        'run-b',
        now, force=True,
    )

    assert first[0] is True
    assert second[0] is False
    assert second[1] == 'project_busy'


def test_blog_prompt_limits_stage_context(blog_environment):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'prompt-series',
        'enabled': True,
        'backlog': ['짧은 주제'],
    })
    root = blog_environment / 'blog'
    state = blog_pipeline._load_state(root, 'prompt-series')
    state.update({'stage': 'brief', 'active_post_id': 'test-post', 'active_topic': '짧은 주제'})
    project = blog_pipeline._load_project(root)
    prompt = blog_pipeline._build_prompt(project, state)

    assert 'blog/posts/' in prompt
    assert 'pipeline_state.json' in prompt
    assert 'Do not inspect chat history, the repository, or unrelated files.' in prompt
    assert 'Target 300-500 words.' in prompt


def test_topic_stage_generates_article_from_legacy_backlog(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,
        'project_id': 'ai-topic-series', 'enabled': True, 'backlog': ['기존에 정한 방향'],
    })
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'blog-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_args, **_kwargs: {'id': 'blog-stream'})

    started = blog_pipeline.run_blog_pipeline(force=True)
    assert started['stage'] == 'topic'
    root = blog_environment / 'blog'
    assert blog_pipeline._load_backlog(root)[0]['kind'] == 'topic_inspiration'
    assert 'Existing queued entries are inspirations' in blog_pipeline._build_prompt(
        blog_pipeline._load_project(root), blog_pipeline._load_state(root, 'ai-topic-series'))
    (root / 'topic_proposal.json').write_text(
        json.dumps({'title': '아침 준비 시간을 줄이는 현관 정리법', 'rationale': '기존 방향을 더 구체화했습니다.'}), encoding='utf-8')
    assert blog_pipeline.record_blog_pipeline_completion({
        'project_id': 'ai-topic-series', 'run_id': started['run_id'], 'stage': 'topic',
        'post_id': '', 'blog_root': str(root), 'claim_path': str(blog_pipeline._claim_path(
            {'codex_home': Path('/missing'), 'account': {'id': 'default'}}, 'ai-topic-series')),
    }, True)
    generated = [item for item in blog_pipeline._load_backlog(root) if item.get('kind') == 'article']
    assert generated[0]['title'] == '아침 준비 시간을 줄이는 현관 정리법'


def test_topic_prompt_prefers_broad_everyday_subjects(blog_environment):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,'project_id': 'broad-topics', 'enabled': True})
    root = blog_environment / 'blog'
    state = blog_pipeline._load_state(root, 'broad-topics')
    state['stage'] = 'topic'

    prompt = blog_pipeline._build_prompt(blog_pipeline._load_project(root), state)

    assert 'matching this direction' in prompt
    assert 'Do not propose an AI' not in prompt


@pytest.mark.parametrize('title', [
    'ChatGPT로 회의록을 빠르게 만드는 방법',
    '생성형 AI 시대에 필요한 업무 습관',
    'LLM을 활용한 개인 생산성 관리',
])
def test_topic_completion_rejects_ai_specialist_titles(blog_environment, title):
    root = blog_environment / 'blog'

    blog_pipeline.configure_blog_project({'exclude_ai_topics': True})
    assert blog_pipeline._queue_generated_topic(
        root, {'title': title, 'rationale': '범용 주제여야 합니다.'}, blog_pipeline._now()) is False
    assert blog_pipeline._load_backlog(root) == []


def test_completion_rejects_a_different_workspace_owner(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,'project_id': 'scoped-series', 'enabled': True})
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'blog-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_args, **_kwargs: {'id': 'blog-stream'})
    started = blog_pipeline.run_blog_pipeline(force=True)
    root = blog_environment / 'blog'

    assert blog_pipeline.record_blog_pipeline_completion({
        'project_id': 'scoped-series', 'run_id': started['run_id'], 'stage': 'topic',
        'blog_root': str(root), 'workspace_path': '/another/workbench/workspace',
    }, True) is False
    assert blog_pipeline.get_blog_pipeline_status()['state']['in_flight']['run_id'] == started['run_id']


def _interrupted_blog_run(workspace, monkeypatch, *, stream=None):
    from datetime import timedelta
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,'project_id': 'recovery-series', 'enabled': True})
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_kwargs: {'id': 'recovery-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_args, **_kwargs: {'id': 'recovery-stream'})
    monkeypatch.setattr(codex_chat, 'get_session', lambda _id: None)
    started = blog_pipeline.run_blog_pipeline(force=True)
    root = workspace / 'blog'
    state = blog_pipeline.get_blog_pipeline_status()['state']
    state['in_flight']['started_at'] = blog_pipeline.normalize_timestamp(
        blog_pipeline._now() - timedelta(hours=3))
    blog_pipeline._save_state(root, state)
    if stream:
        monkeypatch.setitem(codex_chat.state.codex_streams, 'recovery-stream', stream)
    return root, started


def test_interrupted_run_is_recovered_and_restarted_in_same_call(blog_environment, monkeypatch):
    root, original = _interrupted_blog_run(blog_environment, monkeypatch)
    result = blog_pipeline.run_blog_pipeline(force=False)
    assert result['started'] is True
    assert result['run_id'] != original['run_id']
    state = blog_pipeline.get_blog_pipeline_status()['state']
    assert state['last_error'] == ''
    assert state['last_result']['status'] == 'recovered'
    history = blog_pipeline._read_jsonl_tail(root / 'runs.jsonl')
    assert [item['status'] for item in history] == ['started', 'recovered', 'started']
    assert history[1]['stream_id'] == 'recovery-stream'


def test_long_running_stream_is_never_recovered(blog_environment, monkeypatch):
    _, original = _interrupted_blog_run(blog_environment, monkeypatch, stream={'done': False})
    result = blog_pipeline.run_blog_pipeline(force=True)
    assert result['reason'] == 'run_in_flight'
    assert blog_pipeline.get_blog_pipeline_status()['state']['in_flight']['run_id'] == original['run_id']


def test_missing_start_timestamp_can_be_recovered(blog_environment, monkeypatch):
    root, _ = _interrupted_blog_run(blog_environment, monkeypatch)
    state = blog_pipeline.get_blog_pipeline_status()['state']
    state['in_flight']['started_at'] = None
    blog_pipeline._save_state(root, state)
    assert blog_pipeline.run_blog_pipeline(force=True)['started'] is True


def test_foreign_live_owner_is_protected(blog_environment, monkeypatch):
    root, _ = _interrupted_blog_run(blog_environment, monkeypatch)
    state = blog_pipeline.get_blog_pipeline_status()['state']
    state['in_flight']['owner_pid'] = 123456
    blog_pipeline._save_state(root, state)
    monkeypatch.setattr(blog_pipeline.os, 'kill', lambda *_args: None)
    assert blog_pipeline.run_blog_pipeline(force=True)['reason'] == 'run_in_flight'


def test_saved_completion_restores_stage_instead_of_repeating_it(blog_environment, monkeypatch):
    root, original = _interrupted_blog_run(blog_environment, monkeypatch)
    (root / 'topic_proposal.json').write_text(json.dumps({'title': '하루 계획을 정리하는 방법'}))
    monkeypatch.setattr(codex_chat, 'get_session', lambda _id: {'messages': [{
        'role': 'assistant', 'content': '완료',
        'metadata': {'streaming': False, 'token_usage': {'total_tokens': 42}},
    }]})
    result = blog_pipeline.run_blog_pipeline(force=True)
    assert result['stage'] == 'brief'
    state = blog_pipeline.get_blog_pipeline_status()['state']
    assert state['last_result']['run_id'] == original['run_id']
    assert state['last_result']['status'] == 'completed'
    assert state['last_result']['token_usage']['total_tokens'] == 42


@pytest.mark.parametrize('reason, expected', [('run_in_flight', 'deferred'), ('stale_run_recovered', 'recovered'), ('start_failed', 'failed')])
def test_unsubmitted_automatic_work_releases_only_its_reservation(blog_environment, monkeypatch, reason, expected):
    snapshot_path = blog_environment / 'usage.json'
    claim_path = blog_environment / 'usage-claim.json'
    attempted_at = blog_pipeline.normalize_timestamp(None)
    snapshot = {'usage_keepalive': {
        'last_mode': 'automatic', 'last_status': 'queued', 'last_attempt_at': attempted_at,
        'automatic_cycle_targets': {'five_hour': 'target'},
    }}
    context = {'account': {'id': 'default'}, 'account_usage_snapshot_path': snapshot_path}
    monkeypatch.setattr(codex_chat, '_account_storage_context', lambda _id: context)
    monkeypatch.setattr(codex_chat, '_load_account_usage_snapshot', lambda _context: snapshot)
    monkeypatch.setattr(codex_chat, '_usage_keepalive_coordination_path', lambda _context: claim_path)
    monkeypatch.setattr(codex_chat, '_run_usage_blog_pipeline', lambda *_args, **_kw: {'submitted': False, 'reason': reason})
    monkeypatch.setattr(codex_chat, '_record_automatic_usage_refresh_history', lambda *_args: None)
    claim_path.write_text(json.dumps({'windows': {
        'five_hour': {'target': 'target', 'submitted_at': attempted_at, 'workspace_scope_id': codex_chat._WORKSPACE_SCOPE_ID},
        'weekly': {'target': 'unrelated'},
    }}))
    codex_chat._start_reserved_automatic_usage_blog('default')
    keepalive = json.loads(snapshot_path.read_text())['usage_keepalive']
    assert keepalive['last_status'] == expected
    assert 'automatic_cycle_targets' not in keepalive
    assert keepalive['next_retry_at']
    assert keepalive['last_error'] == ('start_failed' if expected == 'failed' else '')
    assert json.loads(claim_path.read_text())['windows'] == {'weekly': {'target': 'unrelated'}}


def test_done_stream_is_finalized_before_recovery(blog_environment, monkeypatch):
    root, original = _interrupted_blog_run(blog_environment, monkeypatch, stream={'done': True})
    finalized = []

    def finalize(stream_id):
        finalized.append(stream_id)
        (root / 'topic_proposal.json').write_text(json.dumps({'title': '주말 시간을 정리하는 방법'}))
        blog_pipeline.record_blog_pipeline_completion({
            'run_id': original['run_id'], 'project_id': 'recovery-series',
            'stage': 'topic', 'blog_root': str(root),
            'claim_path': blog_pipeline.get_blog_pipeline_status()['state']['in_flight']['claim_path'],
        }, True)

    monkeypatch.setattr(codex_chat, 'finalize_codex_stream', finalize)
    assert blog_pipeline.run_blog_pipeline(force=True)['stage'] == 'brief'
    assert finalized == ['recovery-stream']
    assert not any(item['status'] == 'recovered' for item in blog_pipeline._read_jsonl_tail(root / 'runs.jsonl'))


def test_partial_message_does_not_restore_completion(blog_environment, monkeypatch):
    _, _ = _interrupted_blog_run(blog_environment, monkeypatch)
    monkeypatch.setattr(codex_chat, 'get_session', lambda _id: {'messages': [{
        'role': 'assistant', 'content': '진행 중', 'metadata': {'streaming': True},
    }]})
    result = blog_pipeline.run_blog_pipeline(force=True)
    assert result['stage'] == 'topic'
    assert blog_pipeline.get_blog_pipeline_status()['state']['last_result']['status'] == 'recovered'


def test_newer_global_reservation_survives_old_worker(blog_environment, monkeypatch):
    snapshot_path = blog_environment / 'usage.json'
    claim_path = blog_environment / 'claim.json'
    snapshot = {'usage_keepalive': {
        'last_mode': 'automatic', 'last_status': 'queued', 'last_attempt_at': '2026-10-05T00:00:00+09:00',
        'automatic_cycle_targets': {'five_hour': 'target'},
    }}
    newer = {'target': 'target', 'submitted_at': '2026-10-05T01:00:00+09:00',
             'workspace_scope_id': codex_chat._WORKSPACE_SCOPE_ID}
    claim_path.write_text(json.dumps({'windows': {'five_hour': newer}}))
    context = {'account': {'id': 'default'}, 'account_usage_snapshot_path': snapshot_path}
    monkeypatch.setattr(codex_chat, '_account_storage_context', lambda _id: context)
    monkeypatch.setattr(codex_chat, '_load_account_usage_snapshot', lambda _context: snapshot)
    monkeypatch.setattr(codex_chat, '_usage_keepalive_coordination_path', lambda _context: claim_path)
    monkeypatch.setattr(codex_chat, '_run_usage_blog_pipeline', lambda *_args, **_kw: {'submitted': False, 'reason': 'run_in_flight'})
    monkeypatch.setattr(codex_chat, '_record_automatic_usage_refresh_history', lambda *_args: None)
    codex_chat._start_reserved_automatic_usage_blog('default')
    assert json.loads(claim_path.read_text())['windows']['five_hour'] == newer


def test_retry_wait_does_not_consume_global_claim(blog_environment, monkeypatch):
    from datetime import timedelta
    blog_pipeline.configure_blog_project({
        "pipeline_mode": "legacy", "allow_web_research": True,'project_id': 'retry-series', 'enabled': True})
    snapshot = {'usage_keepalive': {'next_retry_at': blog_pipeline.normalize_timestamp(
        blog_pipeline._now() + timedelta(minutes=30))}}
    monkeypatch.setattr(codex_chat, '_usage_keepalive_global_claim', lambda *_args: pytest.fail('Claim consumed during retry delay'))
    result = codex_chat._reserve_automatic_usage_blog_locked({'account': {'id': 'default'}}, snapshot)
    assert result['reason'] == 'retry_pending'


def test_completion_before_submission_record_is_restored_once(blog_environment, monkeypatch):
    snapshot_path = blog_environment / 'usage.json'
    snapshot = {'usage_keepalive': {'last_mode': 'automatic', 'last_status': 'queued'}}
    context = {'account': {'id': 'default'}, 'account_usage_snapshot_path': snapshot_path}
    monkeypatch.setattr(codex_chat, '_account_storage_context', lambda _id: context)
    monkeypatch.setattr(codex_chat, '_load_account_usage_snapshot', lambda _context: snapshot)
    monkeypatch.setattr(codex_chat, '_record_automatic_usage_refresh_history', lambda *_args: None)
    monkeypatch.setattr(codex_chat, '_run_usage_blog_pipeline', lambda *_args, **_kw: {
        'submitted': True, 'stream': {'id': 'instant-stream'}, 'blog_pipeline': {'run_id': 'instant-run'},
    })
    monkeypatch.setattr(blog_pipeline, 'get_blog_pipeline_status', lambda: {'state': {'last_result': {
        'run_id': 'instant-run', 'status': 'completed', 'token_usage': {'total_tokens': 17},
    }}})
    codex_chat._start_reserved_automatic_usage_blog('default')
    assert snapshot['usage_keepalive']['last_status'] == 'completed'
    codex_chat._record_automatic_usage_blog_completion('default', 'instant-stream', True)
    events = snapshot['usage_keepalive']['history']
    assert [event['event'] for event in events] == ['submitted', 'completed']
    assert events[-1]['token_usage']['total_tokens'] == 17


def _compact_start(workspace, monkeypatch, **settings):
    blog_pipeline.configure_blog_project({'enabled': True, 'pipeline_mode': 'compact', **settings})
    monkeypatch.setattr(codex_chat, 'create_session', lambda **_: {'id': 'compact-session'})
    monkeypatch.setattr(codex_chat, 'create_codex_stream', lambda *_, **__: {'id': 'compact-stream'})
    return blog_pipeline.run_blog_pipeline(force=True)


def _complete_stage(workspace, run, outputs=None, **kwargs):
    root = workspace / 'blog'
    for name, content in (outputs or {}).items():
        path = root / 'posts' / run['post_id'] / name
        path.write_text(content, encoding='utf-8')
    blog_pipeline.record_blog_pipeline_completion({**run, 'blog_root': str(root)}, True, **kwargs)
    return blog_pipeline.get_blog_pipeline_status()


def test_compact_three_stage_cycle_and_reader(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch, topic_direction='AI와 개발 생산성')
    assert run['stage'] == 'plan'
    status = _complete_stage(blog_environment, run, {'plan.json': '{"title":"AI 개발 기록", "needs_research":false}', 'brief.md':'독자 문제와 근거', 'outline.md':'구성'})
    assert status['state']['stage'] == 'draft'
    assert status['stages'] == ['plan', 'draft', 'review']
    run = blog_pipeline.run_blog_pipeline(force=True)
    status = _complete_stage(blog_environment, run, {'draft.md':'초고'}, token_usage={'input_tokens':100, 'cached_input_tokens':70, 'output_tokens':25, 'total_tokens':125})
    assert status['state']['stage'] == 'review'
    run = blog_pipeline.run_blog_pipeline(force=True)
    status = _complete_stage(blog_environment, run, {'review.md':'검수 완료', 'review.json':'{"verified":true,"pending_claims":[]}', 'final.md':'완성된 글'})
    assert status['state']['completed_post_count'] == 1
    assert status['posts'][0]['token_usage']['cached_input_tokens'] == 70
    assert blog_pipeline.get_blog_artifact(run['post_id'], 'final.md') == '완성된 글'


@pytest.mark.parametrize('outputs', [{}, {'plan.json':'{}','brief.md':'','outline.md':'구성'}])
def test_compact_missing_outputs_do_not_advance(blog_environment, monkeypatch, outputs):
    run = _compact_start(blog_environment, monkeypatch)
    status = _complete_stage(blog_environment, run, outputs)
    assert status['state']['stage'] == 'plan'
    assert status['state']['last_result']['status'] == 'failed'
    assert 'artifact_missing' in status['state']['last_error']


def test_unchanged_outputs_fail_on_retry(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch)
    outputs = {'plan.json':'{}','brief.md':'기획','outline.md':'구성'}
    _complete_stage(blog_environment, run, outputs)
    run = blog_pipeline.run_blog_pipeline(force=True)
    status = _complete_stage(blog_environment, run)
    assert 'unchanged' in status['state']['last_error']


def test_research_needed_without_web_stays_pending(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch)
    status = _complete_stage(blog_environment, run, {'plan.json':'{"title":"자료 조사 글","needs_research":true}','brief.md':'기획','outline.md':'구성'})
    assert status['state']['stage'] == 'research'
    assert status['state']['last_error'] == 'verification_pending: web_research_disabled'
    assert blog_pipeline.run_blog_pipeline(force=True)['reason'] == 'verification_pending'
    blog_pipeline.configure_blog_project({'allow_web_research':True})
    assert blog_pipeline.run_blog_pipeline(force=True)['stage'] == 'research'


def test_review_pending_never_counts_as_completed(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch)
    _complete_stage(blog_environment, run, {'plan.json':'{"title":"실용 글","needs_research":false}','brief.md':'기획','outline.md':'구성'})
    run = blog_pipeline.run_blog_pipeline(force=True)
    _complete_stage(blog_environment, run, {'draft.md':'초고'})
    run = blog_pipeline.run_blog_pipeline(force=True)
    status = _complete_stage(blog_environment, run, {'review.md':'출처 부족','review.json':'{"verified":false,"pending_claims":["수치"]}','final.md':'검증 전 원고'})
    assert status['state']['stage'] == 'review'
    assert status['state']['completed_post_count'] == 0
    assert status['posts'][0]['status'] == '검증 대기'


def test_automatic_budget_and_manual_override(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch, daily_run_budget=1)
    _complete_stage(blog_environment, run)
    state = blog_pipeline.get_blog_pipeline_status()['state']
    state['next_run_at'] = None
    blog_pipeline._save_state(blog_environment / 'blog', state)
    assert blog_pipeline.run_blog_pipeline(force=False)['reason'] == 'daily_budget_exceeded'
    assert blog_pipeline.run_blog_pipeline(force=True)['started']


def test_pause_only_blocks_automatic_blog(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch)
    _complete_stage(blog_environment, run)
    blog_pipeline.configure_blog_project({'automatic_paused':True})
    assert blog_pipeline.run_blog_pipeline()['reason'] == 'automatic_paused'
    assert blog_pipeline.run_blog_pipeline(force=True)['started']


@pytest.mark.parametrize('post_id, filename', [('..','final.md'), ('post','../../project.json'), ('post','secrets.txt')])
def test_blog_reader_rejects_paths(blog_environment, post_id, filename):
    with pytest.raises(ValueError):
        blog_pipeline.get_blog_artifact(post_id, filename)


def test_blog_reader_rejects_symlink(blog_environment):
    directory = blog_environment / 'blog' / 'posts' / 'post'
    directory.mkdir(parents=True)
    target = blog_environment / 'private.md'
    target.write_text('private')
    (directory / 'final.md').symlink_to(target)
    with pytest.raises(ValueError):
        blog_pipeline.get_blog_artifact('post', 'final.md')


def test_topic_allowed_files_without_post_and_ai_boundary(blog_environment):
    assert 'blog/topic_proposal.json' in blog_pipeline._stage_files(blog_environment / 'blog', {'stage':'topic'})
    assert not blog_pipeline._AI_TOPIC_PATTERN.search('daily email habits')
    assert blog_pipeline._AI_TOPIC_PATTERN.search('ChatGPT로 글 쓰기')


def test_automatic_interval_is_observed(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch)
    _complete_stage(blog_environment, run)
    assert blog_pipeline.run_blog_pipeline()['reason'] == 'not_due'


def test_research_requires_sources(blog_environment, monkeypatch):
    run = _compact_start(blog_environment, monkeypatch, allow_web_research=True)
    _complete_stage(blog_environment, run, {'plan.json':'{"title":"조사 글","needs_research":true}', 'brief.md':'기획', 'outline.md':'구성'})
    run = blog_pipeline.run_blog_pipeline(force=True)
    assert run['stage'] == 'research'
    status = _complete_stage(blog_environment, run, {'research.md':'근거 부족', 'sources.json':'[]'})
    assert status['state']['stage'] == 'research'
    assert status['state']['last_error'] == 'verification_pending: sources_required'


def test_blog_page_and_artifact_endpoint(blog_environment):
    from flask import Flask
    from codex_agent.blueprints.codex_chat import bp
    app = Flask('blog-test', template_folder=str(Path(blog_pipeline.__file__).parents[1] / 'templates'))
    app.register_blueprint(bp)
    client = app.test_client()
    assert client.get('/blog').status_code == 200
    assert b'blog-dashboard' in client.get('/blog').data
    directory = blog_environment / 'blog' / 'posts' / 'post'
    directory.mkdir(parents=True)
    (directory / 'final.md').write_text('<script>unsafe()</script>')
    response = client.get('/api/codex/blog/posts/post/final.md')
    assert response.json['content'] == '<script>unsafe()</script>'
    assert client.get('/api/codex/blog/posts/post/private.txt').status_code == 400
    assert client.get('/api/codex/blog/posts/missing/final.md').status_code == 404
