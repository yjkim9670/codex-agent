"""Local, bounded voice transcription jobs. Audio and text are never logged."""
import json
import os
import signal
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 300
TTL = 600
_lock = threading.RLock()
_jobs = {}
_CONFIG_PATH = Path(__file__).resolve().parents[2] / '.local' / 'voice' / 'config.json'


def _settings():
    """Read server-owned local settings; explicit environment values win."""
    try:
        settings = json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
    except FileNotFoundError:
        settings = {}
    except (OSError, ValueError):
        raise ValueError('음성 전사 설정 파일을 읽을 수 없습니다. .local/voice/config.json을 확인하세요.') from None
    if not isinstance(settings, dict) or any(not isinstance(value, str) for value in settings.values()):
        raise ValueError('음성 전사 설정 값은 문자열이어야 합니다. .local/voice/config.json을 확인하세요.')
    return {
        key: os.environ.get(key, settings.get(key, default)).strip()
        for key, default in (
            ('CODEX_VOICE_ENABLED', 'false'), ('CODEX_VOICE_MODEL', ''),
            ('CODEX_VOICE_FFMPEG', 'ffmpeg'), ('CODEX_VOICE_FFPROBE', 'ffprobe'),
            ('CODEX_VOICE_WHISPER_CLI', 'whisper-cli'),
        )
    }


def _validated_settings():
    settings = _settings()
    if settings['CODEX_VOICE_ENABLED'].lower() not in ('1', 'true', 'yes', 'on'):
        raise ValueError('음성 전사가 서버에서 비활성화되어 있습니다. 서버의 음성 전사 설정을 확인하세요.')
    for name in ('ffmpeg', 'ffprobe', 'whisper-cli'):
        key = 'CODEX_VOICE_' + name.upper().replace('-', '_')
        executable = shutil.which(settings[key])
        if not executable:
            raise ValueError(f'{name} 실행 파일을 찾을 수 없습니다.')
        settings[key] = str(Path(executable).resolve())
    model = settings['CODEX_VOICE_MODEL']
    model_path = Path(model).expanduser()
    if not model_path.is_absolute():
        model_path = _CONFIG_PATH.parent / model_path
    if not model or not model_path.is_file():
        raise ValueError('음성 전사 모델이 설정되지 않았거나 파일을 찾을 수 없습니다.')
    settings['CODEX_VOICE_MODEL'] = str(model_path.resolve())
    return settings


def _cleanup_orphans():
    # Only remove private directories created by dead Workbench processes.
    root = Path(tempfile.gettempdir())
    for path in root.glob('workbench-voice-*-*'):
        match = re.fullmatch(r'workbench-voice-(\d+)-[a-zA-Z0-9_]+', path.name)
        if not match:
            continue
        try:
            info = path.lstat()
            if path.is_symlink() or not path.is_dir() or info.st_uid != os.getuid():
                continue
            os.kill(int(match.group(1)), 0)
        except ProcessLookupError:
            shutil.rmtree(path, ignore_errors=True)
        except (OSError, ValueError):
            continue


_cleanup_orphans()


def availability():
    try:
        _validated_settings()
    except ValueError as exc:
        return str(exc)
    return None


def _prune():
    now = time.monotonic()
    for job_id, job in list(_jobs.items()):
        if job['state'] in ('done', 'error', 'cancelled') and now - job['updated'] > TTL:
            del _jobs[job_id]


def create(owner, stream):
    settings = _validated_settings()
    with _lock:
        _prune()
        if any(j['state'] in ('uploading', 'processing') for j in _jobs.values()):
            raise ValueError('다른 음성 전사가 진행 중입니다. 잠시 후 다시 시도하세요.')
        if len(_jobs) >= 100:
            raise ValueError('음성 전사 작업이 가득 찼습니다. 잠시 후 다시 시도하세요.')
        job_id = uuid.uuid4().hex
        job = {'owner': owner, 'state': 'uploading', 'updated': time.monotonic(), 'process': None, 'cancel': False}
        _jobs[job_id] = job
    try:
        directory = tempfile.mkdtemp(prefix=f'workbench-voice-{os.getpid()}-')
        source = Path(directory) / 'audio'
        size = 0
        with source.open('xb') as target:
            os.chmod(source, 0o600)
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('녹음 파일은 20 MiB 이하여야 합니다.')
                target.write(chunk)
        if not size:
            raise ValueError('녹음 파일이 비어 있습니다.')
        with _lock:
            job['state'] = 'processing'
        threading.Thread(target=_run, args=(job_id, directory, settings), daemon=True).start()
        return job_id
    except Exception:
        with _lock:
            _jobs.pop(job_id, None)
        if 'directory' in locals():
            shutil.rmtree(directory, ignore_errors=True)
        raise


def _command(job, args, timeout):
    with _lock:
        if job['cancel']:
            raise RuntimeError('cancelled')
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        job['process'] = process
    try:
        output, _ = process.communicate(timeout=timeout)
        if process.returncode:
            raise RuntimeError('processing failed')
        return output
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        with _lock:
            job['process'] = None


def _expire(job_id, job):
    with _lock:
        if _jobs.get(job_id) is job and job['state'] in ('done', 'error', 'cancelled'):
            _jobs.pop(job_id, None)


def _run(job_id, directory, settings):
    job = _jobs[job_id]
    try:
        source = str(Path(directory) / 'audio')
        wav = str(Path(directory) / 'audio.wav')
        # MediaRecorder WebM often has no duration metadata. Decode a bounded
        # amount first and measure PCM, including enough to detect overlength.
        _command(job, [settings['CODEX_VOICE_FFMPEG'], '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', source, '-map', '0:a:0', '-vn', '-t', str(MAX_SECONDS + 2), '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', wav], 120)
        duration = float(_command(job, [settings['CODEX_VOICE_FFPROBE'], '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', wav], 30).strip())
        if not 0 < duration <= MAX_SECONDS + 1:
            raise ValueError('녹음 길이는 5분 이하여야 합니다.')
        prefix = str(Path(directory) / 'result')
        _command(job, [settings['CODEX_VOICE_WHISPER_CLI'], '-m', settings['CODEX_VOICE_MODEL'], '-l', 'ko', '-f', wav, '-otxt', '-of', prefix], 600)
        result = Path(prefix + '.txt').read_text(encoding='utf-8').strip()
        with _lock:
            if not job['cancel']:
                job.update(state='done', text=result)
    except Exception as exc:
        with _lock:
            if not job['cancel']:
                job.update(state='error', error=str(exc) if isinstance(exc, ValueError) and '녹음' in str(exc) else '음성 파일을 처리하지 못했습니다. 파일과 서버 설정을 확인하세요.')
    finally:
        shutil.rmtree(directory, ignore_errors=True)
        with _lock:
            if job['cancel']:
                job.update(state='cancelled')
            job['updated'] = time.monotonic()
        expiry = threading.Timer(TTL, _expire, args=(job_id, job))
        expiry.daemon = True
        expiry.start()


def get(owner, job_id):
    with _lock:
        _prune()
        job = _jobs.get(job_id)
        if not job or job['owner'] != owner:
            return None
        return {key: job[key] for key in ('state', 'text', 'error') if key in job}


def cancel(owner, job_id):
    with _lock:
        job = _jobs.get(job_id)
        if not job or job['owner'] != owner:
            return False
        job['cancel'] = True
        job.pop('text', None)
        job['updated'] = time.monotonic()
        if job['state'] not in ('uploading', 'processing'):
            job['state'] = 'cancelled'
        if job['process'] and job['process'].poll() is None:
            try:
                os.killpg(job['process'].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True
