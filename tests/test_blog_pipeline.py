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
        json.dumps({'title': 'AI가 만든 다음 글', 'rationale': '독자에게 실용적입니다.'}),
        encoding='utf-8',
    )
    # Re-run completion now that the model artifact exists.  The first call
    # above intentionally exercises invalid-proposal recovery.
    state = blog_pipeline.get_blog_pipeline_status()['state']
    assert state['last_error'] == 'topic_proposal_invalid'
    started = blog_pipeline.run_blog_pipeline(force=True)
    assert started['stage'] == 'topic'
    (blog_environment / 'blog' / 'topic_proposal.json').write_text(
        json.dumps({'title': 'AI가 만든 다음 글', 'rationale': '독자에게 실용적입니다.'}),
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
        'current_topic': 'AI가 만든 다음 글',
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
        json.dumps({'title': 'AI가 만든 첫 글', 'rationale': '연속성을 반영했습니다.'}),
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
        json.dumps({'title': 'AI가 새로 만든 주제', 'rationale': '기존 방향을 더 구체화했습니다.'}), encoding='utf-8')
    assert blog_pipeline.record_blog_pipeline_completion({
        'project_id': 'ai-topic-series', 'run_id': started['run_id'], 'stage': 'topic',
        'post_id': '', 'blog_root': str(root), 'claim_path': str(blog_pipeline._claim_path(
            {'codex_home': Path('/missing'), 'account': {'id': 'default'}}, 'ai-topic-series')),
    }, True)
    generated = [item for item in blog_pipeline._load_backlog(root) if item.get('kind') == 'article']
    assert generated[0]['title'] == 'AI가 새로 만든 주제'


def test_topic_prompt_prefers_broad_everyday_subjects(blog_environment):
    blog_pipeline.configure_blog_project({'project_id': 'broad-topics', 'enabled': True})
    root = blog_environment / 'blog'
    state = blog_pipeline._load_state(root, 'broad-topics')
    state['stage'] = 'topic'

    prompt = blog_pipeline._build_prompt(blog_pipeline._load_project(root), state)

    assert 'Favor broadly useful everyday themes' in prompt
    assert 'Do not make AI, software, or technology the default subject' in prompt


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
