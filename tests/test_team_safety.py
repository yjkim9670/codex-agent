"""Team P1 safety regression: no paid model calls."""
import importlib.util
import json
import subprocess
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[1] / 'codex-web-app/services/team_execution.py'
spec = importlib.util.spec_from_file_location('team_safety', path)
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)


def checks(items=None):
    return json.dumps({'status':'completed','validation':items if items is not None else
                       [{'command':'pytest','exit_code':0,'status':'passed'}]})


def test_worker_validation_contract():
    assert team.parse_worker_report(checks())['status']=='completed'
    with pytest.raises(ValueError): team.parse_worker_report('all good')
    with pytest.raises(ValueError): team.parse_worker_report(checks([]))
    with pytest.raises(ValueError):
        team.parse_worker_report(checks([{'command':'pytest','exit_code':1,'status':'passed'}]))
    failed = team.parse_worker_report(checks([{'command':'pytest','exit_code':1,'status':'failed'}]))
    assert failed['validation'][0]['status']=='failed'
    skipped = team.parse_worker_report(checks([{'command':'pytest','exit_code':None,'status':'skipped'}]))
    assert skipped['validation'][0]['status']=='skipped'


def test_malformed_json():
    with pytest.raises(ValueError): team.parse_tasks(chr(96)*3)


def git(path,*args):
    return subprocess.run(['git','-C',str(path),*args],check=True,capture_output=True)


def test_changed_files_and_preserved_existing_changes(tmp_path):
    git(tmp_path,'init','-q')
    git(tmp_path,'config','user.email','test@example.org')
    git(tmp_path,'config','user.name','Tester')
    (tmp_path/'src').mkdir()
    (tmp_path/'src'/'x.py').write_text('original')
    (tmp_path/'unrelated.py').write_text('original')
    git(tmp_path,'add','.')
    git(tmp_path,'commit','-qm','initial')
    (tmp_path/'unrelated.py').write_text('user edit')
    before=team.workspace_snapshot(tmp_path)
    (tmp_path/'src'/'x.py').write_text('worker edit')
    changes,violations=team.scope_changes(before,team.workspace_snapshot(tmp_path),'src/**')
    assert changes==['src/x.py'] and violations==[]
    (tmp_path/'unrelated.py').write_text('unexpected worker edit')
    changes,violations=team.scope_changes(before,team.workspace_snapshot(tmp_path),'src/**')
    assert violations==['unrelated.py']
    (tmp_path/'unexpected.txt').write_text('untracked')
    changes,violations=team.scope_changes(before,team.workspace_snapshot(tmp_path),'src/**')
    assert 'unexpected.txt' in violations
    git(tmp_path,'add','.')
    git(tmp_path,'commit','-qm','unexpected commit')
    changes,violations=team.scope_changes(before,team.workspace_snapshot(tmp_path),'src/**')
    assert '[git HEAD changed]' in violations


@pytest.mark.parametrize('scope',['*','**','**/*','../x','/tmp/other','C:/bad','src//foo'])
def test_scope_validation(scope):
    with pytest.raises(team.WorkspaceGuardError):
        team.scope_changes({'head':None,'files':{}},{'head':None,'files':{}},scope)


def test_non_git_workspace_fails_closed(tmp_path):
    with pytest.raises(team.WorkspaceGuardError):
        team.workspace_snapshot(tmp_path)


def test_recorded_cli_check_failures_override_worker_claims():
    events = [
        {'item_type': 'command_execution',
         'detail': 'status=completed command=pytest -q exit_code=1 stdout=failed'},
        {'item_type': 'command_execution',
         'detail': 'status=completed command=grep absent-file exit_code=1'},
        {'item_type': 'command_execution',
         'detail': 'status=completed command=npm test exit_code=2'},
    ]
    assert team.observed_failed_validation_events(events) == [
        'pytest -q (exit_code=1)', 'npm test (exit_code=2)'
    ]
    assert team.observed_failed_validation_events([]) == []
