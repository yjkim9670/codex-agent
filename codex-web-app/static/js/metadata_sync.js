(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const labels = {running: '실행 중', success: '완료', failed: '실패', dry_run: '미리보기', skipped_no_candidates: '수정 대상 없음'};
    const apiBase = el('metadata-sync-dashboard').dataset.apiUrl || '/api/codex/metadata-sync';
    let selected = '', timer, loading = false;
    async function api(url, options) {
        const response = await fetch(url, {cache: 'no-store', ...options, headers: {Accept: 'application/json', ...options?.headers}});
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.toLowerCase().includes('application/json')) {
            const hint = response.redirected || [401, 403].includes(response.status)
                ? '로그인 상태와 접근 권한을 확인한 뒤 다시 조회하세요.'
                : [404, 405].includes(response.status)
                    ? '접속 중인 Workbench 서버가 최신 API를 지원하는지 확인하고 서버를 재시작하세요.'
                    : '접속 주소와 프록시 연결 상태를 확인하세요.';
            throw new Error(`문서 동기화 API가 JSON 대신 다른 형식의 응답을 반환했습니다 (HTTP ${response.status}). ${hint}`);
        }
        let data;
        try { data = await response.json(); }
        catch { throw new Error(`문서 동기화 API 응답을 읽을 수 없습니다 (HTTP ${response.status}). 다시 조회하세요.`); }
        if (!data || typeof data !== 'object' || Array.isArray(data)) {
            throw new Error('문서 동기화 API 응답 형식이 올바르지 않습니다. 서버 상태를 확인하세요.');
        }
        if (!response.ok) throw new Error(data.error || data.reason || `HTTP ${response.status}`);
        return data;
    }
    function feedback(message, error = false) {
        el('sync-feedback').textContent = message;
        el('sync-feedback').classList.toggle('error', error);
    }
    function renderCandidates(kind, candidates, reasons) {
        const body = el(kind === 'feature' ? 'preview-features' : 'preview-projects');
        if (!body) return;
        el(`${kind}-count`).textContent = `(${candidates.length})`;
        for (const candidate of candidates) {
            const row = document.createElement('tr');
            for (const value of [candidate.name, candidate.documents.join('\n') || '연결된 후보 문서 없음', candidate.reasons.map(reason => reasons[reason] || reason).join(', ') || '변경 영향 범위']) {
                const cell = document.createElement('td');
                cell.textContent = value; cell.style.whiteSpace = 'pre-line'; row.append(cell);
            }
            const cell = document.createElement('td'), choose = document.createElement('button');
            choose.type = 'button'; choose.className = 'link'; choose.textContent = '범위 선택';
            choose.setAttribute('aria-label', `${kind === 'project' ? '과제 ' : ''}${candidate.name} 범위 선택`);
            choose.addEventListener('click', () => { el('sync-scope').value = `${kind}:${candidate.name}`; el('sync-scope').focus(); });
            cell.append(choose); row.append(cell); body.append(row);
        }
        if (!candidates.length) {
            const cell = body.insertRow().insertCell();
            cell.colSpan = 4; cell.textContent = `현재 수정 후보 ${kind === 'feature' ? 'feature가' : '과제가'} 없습니다.`;
        }
    }
    async function preview() {
        const button = el('preview-refresh');
        button.disabled = true;
        el('preview-features').replaceChildren();
        el('feature-count').textContent = '';
        el('preview-projects')?.replaceChildren();
        if (el('project-count')) el('project-count').textContent = '';
        el('preview-other').hidden = true;
        el('preview-warnings').textContent = '';
        el('preview-status').classList.remove('error');
        el('preview-status').textContent = '현재 변경사항을 분석하는 중…';
        try {
            const data = await api(`${apiBase}/preview`);
            const reasons = {affected_scope: '코드·문서 변경 영향', stale_translation: '번역 갱신 필요', immediate_update_review: '즉시 검토 필요'};
            el('preview-status').textContent = `${data.generated_at_kst || ''} 기준 · 변경 경로 ${data.changed_paths_count}개 · ${data.since_ref ? `기준 커밋 ${data.since_ref.slice(0, 12)}` : '성공 배치 기준 커밋 없음: 현재 작업 트리만 비교'}`;
            renderCandidates('feature', data.features, reasons);
            renderCandidates('project', data.projects || [], reasons);
            el('preview-other').hidden = !data.other_documents.length;
            el('other-count').textContent = `(${data.other_documents.length})`;
            el('other-documents').textContent = data.other_documents.map(doc => `${doc.path} · ${(doc.reasons || []).map(reason => reasons[reason] || reason).join(', ')}`).join('\n');
            el('preview-warnings').textContent = [...data.warnings, ...data.immediate_update_reasons].join('\n');
        } catch (error) {
            el('preview-status').textContent = error.message;
            el('preview-status').classList.add('error');
        } finally { button.disabled = false; }
    }
    async function showDetail(id, focus = true) {
        selected = id;
        try {
            const data = await api(`${apiBase}/runs/${encodeURIComponent(id)}`);
            if (selected !== id) return;
            const meta = data.metadata || {};
            el('sync-detail').hidden = false;
            el('detail-title').textContent = `실행 상세 · ${id}`;
            const validation = meta.validation;
            el('detail-status').textContent = `${labels[meta.result] || meta.result || '알 수 없음'} · ${meta.published === true ? '원본 반영 완료' : meta.published === false ? '원본 미반영' : '반영 기록 없음'}${validation ? ` · 검증 ${validation.passed ? '통과' : '실패'}` : ''}${meta.error ? ` · ${meta.error}` : ''}${validation && validation.error ? ` · ${validation.error}` : ''}`;
            const container = el('changed-files');
            container.replaceChildren();
            const changes = Array.isArray(meta.changes) ? meta.changes : [];
            if (!changes.length) {
                const p = document.createElement('p');
                p.textContent = 'changes' in meta ? '기록된 문서 수정이 없습니다.' : '이전 실행에는 상세 변경 기록이 없습니다.';
                container.append(p);
            }
            for (const change of changes) {
                const details = document.createElement('details');
                const summary = document.createElement('summary');
                summary.textContent = `${change.path} · +${change.added_lines || 0} / −${change.removed_lines || 0}`;
                const pre = document.createElement('pre');
                pre.textContent = change.diff || 'diff 없음';
                details.append(summary, pre);
                container.append(details);
            }
            el('detail-summary').textContent = data.summary || '작업 요약이 없습니다.';
            el('detail-validation').textContent = data.validation_log || '검증 로그가 없습니다.';
            el('detail-error').textContent = data.error_log || '오류 로그가 없습니다.';
            if (focus) el('detail-title').focus();
        } catch (error) { feedback(error.message, true); }
    }
    async function refresh() {
        if (loading) return;
        loading = true;
        clearTimeout(timer);
        try {
            const data = await api(apiBase);
            el('project-path').textContent = `프로젝트: ${data.project}`;
            el('sync-start').disabled = !data.available || data.running;
            el('run-count').textContent = `(${data.runs.length})`;
            const body = el('sync-runs');
            body.replaceChildren();
            for (const run of data.runs) {
                const row = document.createElement('tr');
                const values = [run.started_at_kst || run.id, `${run.mode || '—'} / ${(run.scope || []).join(', ')}`, labels[run.result] || run.result || '알 수 없음', run.has_change_record ? `${run.changed_files}개` : '미기록'];
                for (const value of values) {
                    const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
                }
                const cell = document.createElement('td'), button = document.createElement('button');
                button.type = 'button'; button.className = 'link'; button.textContent = '상세 보기';
                button.setAttribute('aria-label', `${run.id} 상세 보기`);
                button.addEventListener('click', () => showDetail(run.id)); cell.append(button); row.append(cell); body.append(row);
            }
            if (!data.runs.length) { const row = body.insertRow(); const cell = row.insertCell(); cell.colSpan = 5; cell.textContent = '아직 실행 기록이 없습니다.'; }
            if (!data.available) feedback('TG Platform 실행기를 찾을 수 없습니다. 서버의 CODEX_COMMONTG_ROOT 설정을 확인하세요.', true);
            else if (data.running) feedback('문서 동기화가 실행 중입니다. 완료 후 이력을 확인하세요.');
            else feedback('실행 준비됨 · 버전 변경 방지 적용');
            if (selected) await showDetail(selected, false);
            if (data.running) timer = setTimeout(refresh, 10000);
        } catch (error) { feedback(error.message, true); }
        finally { loading = false; }
    }
    el('sync-form').addEventListener('submit', async event => {
        event.preventDefault(); el('sync-start').disabled = true;
        try {
            await api(`${apiBase}/run`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Workbench-Request': 'metadata-sync'}, body: JSON.stringify({scope: el('sync-scope').value.trim()})});
            feedback('수동 실행을 시작했습니다.');
            await refresh();
        } catch (error) { feedback(error.message, true); el('sync-start').disabled = false; }
    });
    el('sync-refresh').addEventListener('click', () => { refresh(); preview(); });
    el('preview-refresh').addEventListener('click', preview);
    refresh();
    preview();
})();
