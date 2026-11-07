"""Voice uses the standalone Chat's encrypted, session-bound dispatcher."""
import base64

from test_conversation_backend import setup
from codex_agent.services import voice_transcription as voice


def test_voice_encryption_upload_and_owner(setup, monkeypatch):
    app, browser, headers, _ = setup
    monkeypatch.setattr(voice, 'availability', lambda: None)
    captured = []
    monkeypatch.setattr(voice, 'create', lambda owner, stream: captured.append((owner, stream.read())) or 'job')
    monkeypatch.setattr(voice, 'get', lambda owner, job: {'state': 'done', 'text': '전사 결과'} if owner == captured[0][0] else None)
    monkeypatch.setattr(voice, 'cancel', lambda owner, job: owner == captured[0][0])
    assert browser.raw_open('/api/voice').status_code == 428
    config = browser.get('/api/voice').json
    assert config['max_prompt_chars'] == 60000
    assert config['error'] is None
    # Larger than the regular API limit; still encrypted and bounded.
    audio = b'audio' * 250000
    upload = browser.post('/api/voice', headers=headers, json={'audio': base64.b64encode(audio).decode()})
    assert upload.status_code == 202
    assert captured[0][1] == audio
    assert browser.get('/api/voice/job').json['text'] == '전사 결과'
    other = app.test_client()
    other.get('/')
    assert other.get('/api/voice/job').status_code == 404
    assert browser.delete('/api/voice/job', headers=headers).json == {'ok': True}
    assert browser.post('/api/voice', headers=headers, json={'audio': '@bad'}).status_code == 400
    assert browser.post('/api/voice', headers=headers, json={}).status_code == 400
    monkeypatch.setattr(voice, 'MAX_BYTES', 3)
    assert browser.post('/api/voice', headers=headers, json={'audio': base64.b64encode(b'four').decode()}).status_code == 413


def test_voice_shared_assets(setup):
    _, browser, _, _ = setup
    assert browser.get('/static/shared/voice.js').status_code == 200
    assert browser.get('/static/shared/voice.css').status_code == 200
    assert browser.get('/static/shared/other.js').status_code == 404
