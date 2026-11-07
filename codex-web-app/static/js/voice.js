(() => {
    const el = id => document.getElementById(id);
    const adapter = window.workbenchVoice || {};
    const input = el(adapter.inputId || 'codex-chat-input'), panel = el('voice-panel'), status = el('voice-status');
    const result = el('voice-result'), label = el('voice-result-label'), limit = el('voice-limit');
    const start = el('voice-start'), stop = el('voice-stop'), retry = el('voice-retry');
    const download = el('voice-download'), cancel = el('voice-cancel'), insert = el('voice-insert');
    let recorder, stream, timer, blob, job, generation = 0, maximum = 4000, baseline, selection, sessionId, csrfToken;
    if (!input || !panel || !start) return;
    const currentSession = adapter.getSession || (() => state.activeSessionId);
    const requestVoice = (path, options) => adapter.request ? adapter.request(path, options) : fetch(path, options);
    const mutationHeaders = () => ({'X-Codex-CSRF-Token': csrfToken || ''});
    const setStatus = text => { status.textContent = text; };
    const tracksOff = () => { stream?.getTracks().forEach(track => track.stop()); stream = null; clearInterval(timer); };
    const codepoints = text => Array.from(text).length;
    function updateLimit() {
        const available = Math.max(0, maximum - codepoints(input.value));
        limit.textContent = `입력창에 추가 가능한 글자: ${available}자 · 전사 결과: ${codepoints(result.value)}자`;
        insert.disabled = !result.value || codepoints(result.value) > available;
    }
    function clean() {
        generation++; tracksOff();
        if (recorder && recorder.state !== 'inactive') recorder.stop();
        recorder = null;
        if (job) requestVoice(`/api/codex/voice/${job}`, {method:'DELETE', headers:mutationHeaders()}).catch(() => {});
        job = null; blob = null; start.disabled = false; if (panel.open) panel.close(); start.focus();
        stop.hidden = retry.hidden = download.hidden = insert.hidden = result.hidden = label.hidden = true;
        result.value = ''; limit.textContent = '';
    }
    async function upload() {
        const version = ++generation;
        retry.hidden = download.hidden = true;
        setStatus('녹음을 업로드하고 전사하고 있습니다.');
        try {
            const data = adapter.uploadBody ? await adapter.uploadBody(blob) : new FormData();
            if (!adapter.uploadBody) data.append('audio', blob, 'recording');
            if (version !== generation) return;
            const response = await requestVoice('/api/codex/voice', {method:'POST', headers:mutationHeaders(), body:data});
            const body = await response.json();
            if (!response.ok) throw new Error(body.error || '업로드에 실패했습니다.');
            if (version !== generation) { requestVoice(`/api/codex/voice/${body.id}`, {method:'DELETE', headers:mutationHeaders()}).catch(() => {}); return; }
            job = body.id;
            while (version === generation) {
                await new Promise(resolve => setTimeout(resolve, 1500));
                if (version !== generation) return;
                const poll = await requestVoice(`/api/codex/voice/${job}`, {cache:'no-store'});
                const current = await poll.json();
                if (version !== generation) return;
                if (!poll.ok) throw new Error(current.error || '작업을 확인할 수 없습니다.');
                if (current.state === 'error' || current.state === 'cancelled') throw new Error(current.error || '전사가 취소되었습니다.');
                if (current.state === 'done') {
                    result.value = current.text || ''; result.hidden = label.hidden = insert.hidden = false;
                    setStatus('전사 결과를 확인한 후 직접 삽입하세요. 자동 전송되지 않습니다.');
                    updateLimit(); return;
                }
            }
        } catch (error) {
            if (version !== generation) return;
            if (job) requestVoice(`/api/codex/voice/${job}`, {method:'DELETE', headers:mutationHeaders()}).catch(() => {});
            job = null; setStatus(`${error.message} 녹음은 이 탭이 열린 동안 재시도하거나 다운로드할 수 있습니다.`);
            retry.hidden = download.hidden = false;
        }
    }
    start.addEventListener('click', async () => {
        panel.showModal(); start.disabled = true;
        setStatus('음성 입력을 준비하고 있습니다.');
        const version = ++generation;
        baseline = input.value; selection = [input.selectionStart, input.selectionEnd];
        sessionId = currentSession();
        try {
            const response = await requestVoice('/api/codex/voice', {cache:'no-store'}); const config = await response.json();
            if (version !== generation) return;
            if (!response.ok || config.error) throw new Error(config.error || '음성 전사를 사용할 수 없습니다.');
            csrfToken = config.csrf_token;
            maximum = config.max_prompt_chars;
            if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('HTTPS 또는 localhost와 녹음을 지원하는 브라우저가 필요합니다.');
            const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
            if (!mime) throw new Error('지원되는 녹음 형식이 없습니다. 브라우저를 업데이트하세요.');
            setStatus('마이크 권한을 요청하고 있습니다.');
            const acquired = await navigator.mediaDevices.getUserMedia({audio:true});
            if (version !== generation) { acquired.getTracks().forEach(track => track.stop()); return; }
            stream = acquired;
            const recording = new MediaRecorder(stream, {mimeType:mime});
            recorder = recording;
            const chunks = []; let bytes = 0, started = Date.now();
            recording.ondataavailable = event => {
                if (version !== generation) return;
                if (event.data.size) { chunks.push(event.data); bytes += event.data.size; }
                if (bytes > config.max_bytes && recording.state === 'recording') recording.stop();
            };
            recording.onerror = () => {
                if (version !== generation) return;
                generation++; tracksOff(); stop.hidden = true;
                setStatus('녹음 중 오류가 발생했습니다. 취소 후 다시 시도하세요.');
            };
            recording.onstop = () => {
                if (version !== generation) return;
                tracksOff(); stop.hidden = true;
                blob = new Blob(chunks, {type:mime});
                if (!blob.size || blob.size > config.max_bytes) { setStatus('녹음이 비었거나 크기 제한을 초과했습니다.'); return; }
                upload();
            };
            recording.start(1000); stop.hidden = false;
            setStatus('녹음 중 0:00 / 5:00'); stop.focus();
            timer = setInterval(() => {
                const seconds = Math.floor((Date.now() - started) / 1000);
                setStatus(`녹음 중 ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')} / 5:00${seconds >= 270 ? ' · 곧 자동 중지됩니다.' : ''}`);
                if (seconds >= config.max_seconds && recording.state === 'recording') recording.stop();
            }, 250);
        } catch (error) { if (version === generation) { tracksOff(); setStatus(error.message || '마이크 권한을 확인하세요.'); } }
    });
    stop.addEventListener('click', () => { if (recorder?.state === 'recording') recorder.stop(); });
    cancel.addEventListener('click', clean);
    panel.addEventListener('cancel', event => { event.preventDefault(); clean(); });
    panel.addEventListener('close', () => { if (start.disabled) clean(); });
    retry.addEventListener('click', upload);
    download.addEventListener('click', () => { const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href=url; a.download=blob.type.includes('mp4') ? 'recording.m4a' : 'recording.webm'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
    result.addEventListener('input', updateLimit); input.addEventListener('input', updateLimit);
    insert.addEventListener('click', () => {
        updateLimit(); if (insert.disabled) return;
        const changed = baseline !== input.value || sessionId !== currentSession();
        if (changed && !confirm('녹음 중 초안 또는 세션이 변경되었습니다. 현재 입력창의 커서 위치에 삽입할까요?')) return;
        const [from, to] = changed ? [input.selectionStart, input.selectionEnd] : selection;
        const next = input.value.slice(0,from) + result.value + input.value.slice(to);
        if (codepoints(next) > maximum) { setStatus('입력 제한을 초과합니다. 전사 결과를 수정하세요.'); return; }
        const cursor = from + result.value.length;
        input.value = next; input.dispatchEvent(new Event('input', {bubbles:true})); clean(); input.focus(); input.setSelectionRange(cursor, cursor);
    });
    window.addEventListener('pagehide', () => {
        generation++; tracksOff();
        if (recorder && recorder.state !== 'inactive') recorder.stop();
        if (job) requestVoice(`/api/codex/voice/${job}`, {method:'DELETE', headers:mutationHeaders(), keepalive:true}).catch(() => {});
    });
})();
