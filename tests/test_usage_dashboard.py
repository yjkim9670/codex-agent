from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services import codex_chat as chat
from codex_agent.services import usage_dashboard as usage
from codex_agent.services.model_usage_analysis import analyze


def event(key='w:run', **extra):
    return {'event_id': key, 'recorded_at': '2026-10-01T10:01:00+09:00',
            'workspace_path': '/workspace', 'model': 'model', 'reasoning_effort': 'medium',
            'input_tokens': 90, 'output_tokens': 10, 'total_tokens': 100, 'duration_ms': 10000,
            **extra}


def test_rollout_duplicates_are_not_added_and_db_balance_is_not_dated():
    e = event()
    events, diagnostics = usage.merge_events([e, e], [{'db_tokens': 150, 'events': [event('rollout:thread')]}])
    assert len(events) == 1
    assert diagnostics['matched_rollout_tokens'] == 100
    assert diagnostics['unallocated_db_tokens'] == 50


def test_partial_or_ambiguous_ledger_match_is_quarantined():
    events, diagnostics = usage.merge_events([event(), event('other')], [{'db_tokens': 100, 'events': [event('rollout:thread')]}])
    assert len(events) == 2
    assert diagnostics['ambiguous_tokens'] == 100
    events, diagnostics = usage.merge_events([event(total_tokens=80)], [{'db_tokens': 100, 'events': [event('rollout:thread')]}])
    assert len(events) == 1
    assert diagnostics['ambiguous_tokens'] == 100


def test_missing_rollout_supplement_and_fork_quarantine():
    events, diagnostics = usage.merge_events([], [{'db_tokens': 100, 'events': [event('rollout:thread')]}])
    assert sum(e['total_tokens'] for e in events) == 100
    assert diagnostics['supplemental_tokens'] == 100
    assert not usage.merge_events([], [{'db_tokens': 100, 'events': [event()], 'forked': True}])[0]


def test_repeated_cumulative_samples_and_effort_changes(tmp_path):
    path = tmp_path/'rollout.jsonl'
    rows = []
    def add(kind, payload):
        rows.append({'timestamp': '2026-10-01T01:00:00Z', 'type': kind, 'payload': payload})
    add('session_meta', {'id': 'thread', 'cwd': '/workspace'})
    add('turn_context', {'model': 'model', 'effort': 'medium', 'turn_id': 'one'})
    for total in (100, 100, 200):
        add('event_msg', {'type': 'token_count', 'info': {'total_token_usage': {'total_tokens': total}}})
    add('turn_context', {'model': 'model', 'effort': 'low', 'turn_id': 'two'})
    add('event_msg', {'type': 'token_count', 'info': {'total_token_usage': {'total_tokens': 250}}})
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    result = usage._rollout(path, {'id': 'fallback'})
    assert [(e['reasoning_effort'],e['total_tokens']) for e in result['events']] == [('medium',200),('low',50)]


def test_collection_recovers_common_environment_and_is_idempotent(tmp_path, monkeypatch):
    home = tmp_path/'home'; home.mkdir()
    db_path=home/'state_5.sqlite'
    rollout=home/'rollout.jsonl'
    rollout.write_text('\n'.join(json.dumps(r) for r in [
        {'type': 'session_meta', 'timestamp': '2026-10-01T01:00:00Z', 'payload': {'id':'thread','cwd':'/CommonTG'}},
        {'type':'turn_context','timestamp':'2026-10-01T01:00:00Z','payload':{'model':'gpt-6.1-sol','effort':'medium','turn_id':'one'}},
        {'type':'event_msg','timestamp':'2026-10-01T01:01:00Z','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':90,'output_tokens':10,'total_tokens':100}}}},
    ]))
    with sqlite3.connect(db_path) as db:
        db.execute('create table threads (id text, rollout_path text, cwd text, tokens_used int, created_at int, updated_at int)')
        db.execute('insert into threads values (?,?,?,?,?,?)',('thread',str(rollout),'/CommonTG',100,1790816400,1790816460))
    root=tmp_path/'account';root.mkdir()
    context={'root':root,'account':{'id':'one'},'codex_home':home,'usage_events_path':root/'events.jsonl'}
    monkeypatch.setattr(usage,'discover_homes',lambda c,e:[home])
    monkeypatch.setattr(chat,'_read_auth_identity',lambda p:{'provider_account_id':'same'})
    now=datetime(2026,10,1,12,tzinfo=usage.KST)
    first=usage.collect(context,force=True,now=now)
    second=usage.collect(context,force=True,now=now)
    assert first['events']==second['events']
    assert first['diagnostics']['supplemental_tokens']==100
    assert first['events'][0]['workspace_path']=='/CommonTG'
    assert db_path.exists() and rollout.exists()
    monkeypatch.setattr(chat,'_read_auth_identity',lambda p:{'provider_account_id':'same' if p!=home else ''})
    later=usage.collect(context,force=True,now=datetime(2026,10,1,13,tzinfo=usage.KST))
    assert later['sources'][0]['status']=='account_unverified'
    assert not later['events']


def test_effort_filter_never_filters_overlap_detection(tmp_path):
    data={'events':[event(),event('w:low',reasoning_effort='low')],
          'codex_usage_calibration.json':{'records':[{
              'id':'run','created_at':event()['recorded_at'],'model':'model','raw_tokens':100,'learning_eligible':True,
              'limits_before':{'five_hour':{'resets_at':'same'}},
              'outcomes':{'five_hour':{'status':'observed','group_id':'group','group_size':1,'group_actual_percent':1,'observed_at':'2026-10-01T10:02:00+09:00'}}}]},
          'codex_usage_history.json':{'account_limit_samples':[{'limits_observed_at':'2026-10-01T10:02:00+09:00','five_hour_resets_at':'same'}]}}
    report=analyze(tmp_path,effort='medium',data=data,now=datetime(2026,10,1,12,tzinfo=usage.KST))
    assert report['total_tokens']==100
    assert report['windows']['five_hour']['excluded']['overlapping_local_execution']==1
    assert not report['windows']['five_hour']['models']


def test_empty_data_and_parameter_validation(tmp_path, monkeypatch):
    report=analyze(tmp_path,data={})
    assert report['total_tokens']==0
    assert report['calibration_first_at'] is None
    from flask import Flask
    from codex_agent.blueprints.usage_dashboard import bp
    app=Flask(__name__);app.register_blueprint(bp)
    assert app.test_client().get('/api/codex/usage/dashboard?days=91').status_code==400
    assert app.test_client().get('/api/codex/usage/dashboard?effort=invalid').status_code==400


def test_mixed_effort_group_is_not_attributed_even_in_all_mode(tmp_path):
    events=[event('w:first'),event('w:second',reasoning_effort='low',recorded_at='2026-10-01T10:01:30+09:00')]
    records=[{'id':e['event_id'].split(':',1)[1],'model':'model','raw_tokens':100,
              'created_at':e['recorded_at'],'learning_eligible':True,
              'outcomes':{'five_hour':{'status':'observed','group_id':'group','group_size':2}}} for e in events]
    result=analyze(tmp_path,data={'events':events,'codex_usage_calibration.json':{'records':records}},now=datetime(2026,10,1,12,tzinfo=usage.KST))
    assert result['total_tokens']==200
    assert len(result['model_efforts'])==2
    assert result['windows']['five_hour']['excluded']['mixed_effort_group']==1
    assert not result['windows']['five_hour']['models']
