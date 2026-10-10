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


@pytest.fixture(autouse=True)
def isolated_git_discovery(tmp_path, monkeypatch):
    # TMPDIR can live inside the checkout; do not discover its ancestor Git repo.
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))


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


def test_non_git_workspace_changes_and_preserved_user_edits(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / 'notes.txt').write_text('user edit')
    (tmp_path / 'deleted.txt').write_text('original')
    before = team.workspace_snapshot(tmp_path)
    assert before['kind'] == 'filesystem'
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/new.py').write_text('worker edit')
    (tmp_path / 'deleted.txt').unlink()
    changes, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'src/new.py, deleted.txt')
    assert changes == ['deleted.txt', 'src', 'src/new.py']
    assert violations == []
    assert (tmp_path / 'notes.txt').read_text() == 'user edit'
    (tmp_path / 'notes.txt').write_text('unexpected worker edit')
    _, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'src/**, deleted.txt')
    assert violations == ['notes.txt']


def test_non_git_modes_and_symlinks(tmp_path):
    external = tmp_path.parent / (tmp_path.name + '-external')
    external.mkdir()
    (external / 'unmonitored').write_text('external')
    (tmp_path / 'link').symlink_to(external, target_is_directory=True)
    script = tmp_path / 'script.sh'
    script.write_text('echo hello')
    script.chmod(0o644)
    before = team.workspace_snapshot(tmp_path)
    assert not any('unmonitored' in path for path in before['files'])
    script.chmod(0o755)
    (tmp_path / 'link').unlink()
    (tmp_path / 'link').symlink_to('missing-target')
    assert team.scope_changes(before, team.workspace_snapshot(tmp_path), 'script.sh') == (
        ['link', 'script.sh'], ['link'])


@pytest.mark.parametrize('limit,value', [('MAX_SNAPSHOT_ENTRIES', 0), ('MAX_SNAPSHOT_BYTES', 1),
                                       ('MAX_SNAPSHOT_SECONDS', 0)])
def test_non_git_snapshot_limits_fail_closed(tmp_path, monkeypatch, limit, value):
    (tmp_path / 'file').write_text('content')
    monkeypatch.setattr(team, limit, value)
    with pytest.raises(team.WorkspaceGuardError, match='한도 초과'):
        team.workspace_snapshot(tmp_path)


def test_non_git_unreadable_file_fails_closed(tmp_path, monkeypatch):
    (tmp_path / 'file').write_text('content')
    def denied(*args, **kwargs):
        raise PermissionError('denied')
    monkeypatch.setattr(team.os, 'open', denied)
    with pytest.raises(team.WorkspaceGuardError, match='denied'):
        team.workspace_snapshot(tmp_path)


def test_non_git_nested_repository_files_and_head(tmp_path):
    repo = tmp_path / 'project'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'test@example.org')
    git(repo, 'config', 'user.name', 'Tester')
    source = repo / 'file.py'
    source.write_text('original')
    (repo / '.gitignore').write_text('generated.txt\n')
    (repo / 'generated.txt').write_text('before')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'initial')
    before = team.workspace_snapshot(tmp_path)
    source.write_text('worker edit')
    changes, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'project/file.py')
    assert changes == ['project/file.py'] and violations == []
    (repo / 'generated.txt').write_text('unexpected generated change')
    _, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'project/file.py')
    assert violations == ['project/generated.txt']
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'unexpected commit')
    _, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'project/**')
    assert '[git HEAD changed: project]' in violations


def test_non_git_without_git_executable(tmp_path, monkeypatch):
    (tmp_path / 'file').write_text('before')
    def missing(*args, **kwargs):
        raise FileNotFoundError('git')
    monkeypatch.setattr(team.subprocess, 'run', missing)
    before = team.workspace_snapshot(tmp_path)
    (tmp_path / 'file').write_text('after')
    assert team.scope_changes(before, team.workspace_snapshot(tmp_path), 'file') == (['file'], [])


def test_non_git_unborn_nested_repository(tmp_path):
    repo = tmp_path / 'project'
    repo.mkdir()
    git(repo, 'init', '-q')
    assert team.workspace_snapshot(tmp_path)['repositories'] == {'project': None}


def test_workspace_guard_mode_change_is_flagged(tmp_path):
    before = team.workspace_snapshot(tmp_path)
    git(tmp_path, 'init', '-q')
    _, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path), 'src/**')
    assert '[workspace guard changed]' in violations


def test_git_failure_does_not_silently_disable_guard(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 128, b'', b'fatal: permission denied')
    monkeypatch.setattr(team.subprocess, 'run', broken)
    with pytest.raises(team.WorkspaceGuardError, match='Git 검사 실패'):
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


def test_git_subdirectory_scope_uses_execution_relative_paths(tmp_path):
    git(tmp_path, 'init', '-q')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/x.py').write_text('before')
    before = team.workspace_snapshot(tmp_path / 'src')
    (tmp_path / 'src/x.py').write_text('after')
    changes, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path / 'src'), 'x.py')
    assert changes == ['x.py'] and violations == []
    (tmp_path / 'outside.txt').write_text('unexpected')
    _, violations = team.scope_changes(before, team.workspace_snapshot(tmp_path / 'src'), 'x.py')
    assert '../outside.txt' in violations
