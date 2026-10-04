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


def test_automatic_usage_reservation_requires_an_enabled_blog(blog_environment, monkeypatch):
    context = {'account': {'id': 'default'}, 'codex_home': blog_environment.parent / 'codex-home'}
    snapshot = {'five_hour': {'used_percent': 0, 'resets_at': '2026-09-19T17:00:00+09:00'}}
    monkeypatch.setattr(codex_chat, '_account_has_active_codex_stream', lambda _account_id: False)

    assert codex_chat._reserve_automatic_usage_blog_locked(context, snapshot)['reason'] == 'not_configured'

    blog_pipeline.configure_blog_project({
        'project_id': 'automatic-series', 'enabled': True, 'backlog': ['자동 글'],
    })
    monkeypatch.setattr(codex_chat, '_usage_keepalive_global_claim', lambda *_args: (True, ''))
    result = codex_chat._reserve_automatic_usage_blog_locked(context, snapshot)

    assert result['submitted'] is True
    assert snapshot['usage_keepalive']['automatic_cycle_targets']['five_hour'].startswith('five_hour:zero-window:')


def test_blog_pipeline_advances_one_stage_and_records_tokens(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({
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
        'current_stage_number': 2,
        'completed_stage_count': 1,
        'total_stage_count': 5,
        'progress_percent': 20,
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
    blog_pipeline.configure_blog_project({'project_id': 'broad-topics', 'enabled': True})
    root = blog_environment / 'blog'
    state = blog_pipeline._load_state(root, 'broad-topics')
    state['stage'] = 'topic'

    prompt = blog_pipeline._build_prompt(blog_pipeline._load_project(root), state)

    assert 'Favor broadly useful everyday themes' in prompt
    assert 'Do not propose an AI, ChatGPT, prompt, LLM, coding, software, or technology' in prompt


@pytest.mark.parametrize('title', [
    'ChatGPT로 회의록을 빠르게 만드는 방법',
    '생성형 AI 시대에 필요한 업무 습관',
    'LLM을 활용한 개인 생산성 관리',
])
def test_topic_completion_rejects_ai_specialist_titles(blog_environment, title):
    root = blog_environment / 'blog'

    assert blog_pipeline._queue_generated_topic(
        root, {'title': title, 'rationale': '범용 주제여야 합니다.'}, blog_pipeline._now()) is False
    assert blog_pipeline._load_backlog(root) == []


def test_completion_rejects_a_different_workspace_owner(blog_environment, monkeypatch):
    blog_pipeline.configure_blog_project({'project_id': 'scoped-series', 'enabled': True})
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
    blog_pipeline.configure_blog_project({'project_id': 'recovery-series', 'enabled': True})
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
    blog_pipeline.configure_blog_project({'project_id': 'retry-series', 'enabled': True})
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
