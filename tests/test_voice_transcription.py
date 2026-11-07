import io
import json
import subprocess
import threading
import sys
import time
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services import voice_transcription as voice


@pytest.fixture(autouse=True)
def isolated_voice_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, '_CONFIG_PATH', tmp_path / 'config.json')
    for key in voice._settings():
        monkeypatch.delenv(key, raising=False)


def wait_for(owner, job_id):
    for _ in range(200):
        job = voice.get(owner, job_id)
        if job['state'] not in ('uploading', 'processing'):
            return job
        time.sleep(.05)
    pytest.fail('voice job did not finish')


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    model = tmp_path / 'model.bin'
    model.write_bytes(b'model')
    whisper = tmp_path / 'whisper'
    whisper.write_text('#!/bin/sh\nwhile [ "$1" != "-of" ]; do shift; done\nshift\nprintf "테스트 결과" > "$1.txt"\n')
    whisper.chmod(0o755)
    monkeypatch.setenv('CODEX_VOICE_ENABLED', 'true')
    monkeypatch.setenv('CODEX_VOICE_MODEL', str(model))
    monkeypatch.setenv('CODEX_VOICE_WHISPER_CLI', str(whisper))
    voice._jobs.clear()
    yield
    voice._jobs.clear()


def test_valid_audio_and_owner_isolation(fake_model):
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 16000)
    data.seek(0)
    job_id = voice.create(('a', 'token'), data)
    assert voice.get(('b', 'token'), job_id) is None
    assert not voice.cancel(('b', 'token'), job_id)
    job = wait_for(('a', 'token'), job_id)
    assert job == {'state': 'done', 'text': '테스트 결과'}
    assert voice.cancel(('a', 'token'), job_id)
    assert voice.get(('a', 'token'), job_id) == {'state': 'cancelled'}


def test_invalid_and_oversized_audio(fake_model, monkeypatch):
    job_id = voice.create('owner', io.BytesIO(b'not audio'))
    assert wait_for('owner', job_id)['state'] == 'error'
    monkeypatch.setattr(voice, 'MAX_BYTES', 3)
    with pytest.raises(ValueError, match='20 MiB'):
        voice.create('owner', io.BytesIO(b'1234'))


def test_disabled(monkeypatch):
    monkeypatch.delenv('CODEX_VOICE_ENABLED', raising=False)
    assert '비활성화' in voice.availability()


def test_local_config_and_environment_precedence(fake_model, monkeypatch):
    settings = voice._settings()
    voice._CONFIG_PATH.write_text(json.dumps(settings))
    for key in settings:
        monkeypatch.delenv(key, raising=False)
    assert voice.availability() is None
    monkeypatch.setenv('CODEX_VOICE_ENABLED', ' false ')
    assert '비활성화' in voice.availability()
    monkeypatch.setenv('CODEX_VOICE_ENABLED', ' TRUE ')
    assert voice.availability() is None
    monkeypatch.setenv('CODEX_VOICE_MODEL', '/missing/model.bin')
    assert '모델' in voice.availability()


def test_relative_model_path_is_independent_of_cwd(fake_model, monkeypatch, tmp_path):
    settings = voice._settings()
    settings['CODEX_VOICE_MODEL'] = 'model.bin'
    voice._CONFIG_PATH.write_text(json.dumps(settings))
    monkeypatch.delenv('CODEX_VOICE_MODEL')
    monkeypatch.chdir(tmp_path.parent)
    assert voice._validated_settings()['CODEX_VOICE_MODEL'] == str(tmp_path / 'model.bin')


@pytest.mark.parametrize('config', ['{', '[]', '{"CODEX_VOICE_ENABLED": true}'])
def test_invalid_local_config_has_actionable_error(config):
    voice._CONFIG_PATH.write_text(config)
    assert 'config.json' in voice.availability()


def test_missing_executable_is_reported(fake_model, monkeypatch):
    monkeypatch.setenv('CODEX_VOICE_FFMPEG', '/missing/ffmpeg')
    assert 'ffmpeg 실행 파일' in voice.availability()


@pytest.mark.parametrize('container,codec', [('webm', 'libopus'), ('mp4', 'aac')])
def test_browser_audio_without_duration_metadata(fake_model, container, codec):
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
               'anullsrc=r=48000:cl=mono', '-t', '0.2', '-c:a', codec]
    if container == 'mp4':
        command += ['-movflags', 'frag_keyframe+empty_moov']
    else:
        command += ['-live', '1']
    audio = subprocess.check_output(command + ['-f', container, 'pipe:1'], timeout=10)
    if container == 'webm':
        duration = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
            'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 'pipe:0'],
            input=audio, timeout=10)
        assert duration.strip() == b'N/A'
    job_id = voice.create('browser', io.BytesIO(audio))
    assert wait_for('browser', job_id) == {'state': 'done', 'text': '테스트 결과'}


def test_overlength_audio_is_rejected_after_bounded_decode(fake_model, monkeypatch):
    monkeypatch.setattr(voice, 'MAX_SECONDS', 1)
    audio = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
        '-i', 'anullsrc=r=16000:cl=mono', '-t', '4', '-f', 'wav', 'pipe:1'], timeout=10)
    job_id = voice.create('owner', io.BytesIO(audio))
    job = wait_for('owner', job_id)
    assert job['state'] == 'error'
    assert '5분' in job['error']


def test_job_keeps_validated_settings_and_cleans_files(fake_model, monkeypatch):
    settings = voice._validated_settings()
    commands = []
    directories = []

    def command(job, args, timeout):
        commands.append(args)
        monkeypatch.setenv('CODEX_VOICE_MODEL', '/changed/model.bin')
        if args[0] == settings['CODEX_VOICE_FFPROBE']:
            return b'1'
        if args[0] == settings['CODEX_VOICE_WHISPER_CLI']:
            prefix = Path(args[args.index('-of') + 1])
            directories.append(prefix.parent)
            prefix.with_suffix('.txt').write_text('result')
        return b''

    monkeypatch.setattr(voice, '_command', command)
    job_id = voice.create('owner', io.BytesIO(b'audio'))
    assert wait_for('owner', job_id) == {'state': 'done', 'text': 'result'}
    assert commands[-1][commands[-1].index('-m') + 1] == settings['CODEX_VOICE_MODEL']
    for _ in range(100):
        if not directories[0].exists():
            break
        time.sleep(.01)
    assert not directories[0].exists()


def test_command_timeout_reaps_child_process(monkeypatch):
    processes = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(voice.subprocess, 'Popen', capture)
    job = {'cancel': False, 'process': None}
    with pytest.raises(subprocess.TimeoutExpired):
        voice._command(job, [sys.executable, '-c', 'import time; time.sleep(10)'], .05)
    assert processes[0].poll() is not None
    assert job['process'] is None


def test_cancellation_keeps_concurrency_slot_until_worker_exits(fake_model, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked_command(job, args, timeout):
        entered.set()
        assert release.wait(5)
        if job['cancel']:
            raise RuntimeError('cancelled')
        return b''

    monkeypatch.setattr(voice, '_command', blocked_command)
    job_id = voice.create('owner', io.BytesIO(b'audio'))
    try:
        assert entered.wait(2)
        with pytest.raises(ValueError, match='진행 중'):
            voice.create('second', io.BytesIO(b'audio'))
        assert voice.cancel('owner', job_id)
        with pytest.raises(ValueError, match='진행 중'):
            voice.create('second', io.BytesIO(b'audio'))
    finally:
        release.set()
    assert wait_for('owner', job_id) == {'state': 'cancelled'}


def test_voice_routes_real_upload_and_result_deletion(fake_model):
    from flask import Flask
    from codex_agent.blueprints.codex_chat import bp
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.register_blueprint(bp)
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 1600)
    data.seek(0)
    client = app.test_client()
    origin = {'Origin': 'http://localhost', 'X-Codex-CSRF-Token': client.get('/api/codex/voice').json['csrf_token']}
    response = client.post('/api/codex/voice', data={'audio': (data, 'recording')}, headers=origin)
    assert response.status_code == 202
    url = '/api/codex/voice/' + response.json['id']
    for _ in range(200):
        response = client.get(url)
        if response.json['state'] != 'processing':
            break
        time.sleep(.05)
    assert response.json == {'state': 'done', 'text': '테스트 결과'}
    assert response.headers['Cache-Control'] == 'no-store'
    assert app.test_client().get(url).status_code == 404
    assert client.delete(url, headers=origin).status_code == 204
    assert client.get(url).json == {'state': 'cancelled'}


def test_voice_routes_enforce_origin_and_session_owner(fake_model, monkeypatch):
    from flask import Flask
    from codex_agent.blueprints.codex_chat import bp
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.register_blueprint(bp)
    monkeypatch.setattr(voice, 'create', lambda owner, stream: 'job123')
    monkeypatch.setattr(voice, 'get', lambda owner, job_id: {'state': 'done'} if owner[1] == 'correct' else None)
    client = app.test_client()
    config = client.get('/api/codex/voice')
    assert config.json['error'] is None
    assert config.headers['Cache-Control'] == 'no-store'
    denied = client.post('/api/codex/voice', data={'audio': (io.BytesIO(b'a'), 'a.webm')}, headers={'Origin': 'https://other.example'})
    assert denied.status_code == 403
    with client.session_transaction() as session:
        session['voice_owner'] = 'correct'
    assert client.get('/api/codex/voice/job123').json == {'state': 'done'}
    assert client.get('/api/codex/voice/job123').headers['Cache-Control'] == 'no-store'
    other = app.test_client()
    assert other.get('/api/codex/voice/job123').status_code == 404
    assert client.delete('/api/codex/voice/job123', headers={'Origin': 'https://other.example'}).status_code == 403


@pytest.mark.parametrize('origin,fetch_site', [
    ('https://workbench.example', 'same-origin'),
    ('https://workbench.example:3443', 'same-origin'),
    (None, None),  # Clients without Origin still need the session token.
])
def test_voice_mutations_through_proxy(fake_model, monkeypatch, origin, fetch_site):
    from flask import Flask
    from codex_agent.blueprints.codex_chat import bp
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.register_blueprint(bp)
    owners = []
    monkeypatch.setattr(voice, 'create', lambda owner, stream: owners.append(owner) or 'proxyjob')
    monkeypatch.setattr(voice, 'cancel', lambda owner, job_id: owner == owners[0])
    client = app.test_client()
    # External HTTPS origin, internal HTTP Host, no forwarded-header trust.
    base = 'http://127.0.0.1:3004'
    token = client.get('/api/codex/voice', base_url=base).json['csrf_token']
    assert client.get('/api/codex/voice', base_url=base).json['csrf_token'] == token
    headers = {'X-Codex-CSRF-Token': token}
    if origin:
        headers['Origin'] = origin
    if fetch_site:
        headers['Sec-Fetch-Site'] = fetch_site
    response = client.post('/api/codex/voice', base_url=base,
                           data={'audio': (io.BytesIO(b'a'), 'a.webm')}, headers=headers)
    assert response.status_code == 202
    assert client.delete('/api/codex/voice/proxyjob', base_url=base, headers=headers).status_code == 204


@pytest.mark.parametrize('case', ['missing', 'wrong', 'non-ascii', 'other-session', 'cross-site', 'forged-forwarded'])
def test_voice_rejects_invalid_csrf_before_mutations(fake_model, monkeypatch, case):
    from flask import Flask
    from codex_agent.blueprints.codex_chat import bp
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.register_blueprint(bp)
    calls = []
    monkeypatch.setattr(voice, 'create', lambda *args: calls.append('create'))
    monkeypatch.setattr(voice, 'cancel', lambda *args: calls.append('cancel'))
    client = app.test_client()
    token = client.get('/api/codex/voice').json['csrf_token']
    headers = {'Origin': 'http://localhost', 'X-Codex-CSRF-Token': token}
    if case == 'missing':
        headers.pop('X-Codex-CSRF-Token')
    elif case == 'wrong':
        headers['X-Codex-CSRF-Token'] = 'invalid'
    elif case == 'non-ascii':
        headers['X-Codex-CSRF-Token'] = '잘못된 토큰'
    elif case == 'other-session':
        client = app.test_client()
    elif case == 'cross-site':
        headers.update({'Origin': 'https://attacker.example', 'Sec-Fetch-Site': 'cross-site'})
    else:
        headers = {'Origin': 'https://attacker.example', 'X-Forwarded-Host': 'attacker.example', 'X-Forwarded-Proto': 'https'}
    response = client.post('/api/codex/voice', data={'audio': (io.BytesIO(b'a'), 'a.webm')}, headers=headers)
    assert response.status_code == 403
    assert response.json['error_code'] == 'voice_csrf_rejected'
    assert client.delete('/api/codex/voice/job', headers=headers).status_code == 403
    assert calls == []
