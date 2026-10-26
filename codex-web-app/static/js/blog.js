(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const labels = {plan:'기획·근거',topic:'주제 선정',brief:'기획',research:'조사',outline:'구성',draft:'초고',review:'검수',select:'새 글 준비'};
    const fields = ['enabled','automatic_paused','topic_direction','audience','style_guide','exclude_ai_topics','allow_web_research','topic_rotation_enabled','cadence_minutes','daily_run_budget','daily_token_budget'];
    let status = {}, reading = 0;
    async function api(url, options) {
        const response = await fetch(url, {cache:'no-store', ...options, headers:{'Content-Type':'application/json', ...options?.headers}});
        if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error(`API 응답을 읽을 수 없습니다 (HTTP ${response.status}). 로그인 또는 서버 버전을 확인하세요.`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || data.reason || `HTTP ${response.status}`);
        return data;
    }
    function tokens(t = {}) {return ['input_tokens','cached_input_tokens','output_tokens','total_tokens'].map(k => Number(t[k] || 0).toLocaleString()).join(' / ');}
    function row(body, values) {const tr = document.createElement('tr'); for (const value of values) {const td = document.createElement('td');td.textContent = value;tr.append(td);}body.append(tr);return tr;}
    function posts() {
        el('posts').replaceChildren();
        const query = el('search').value.toLowerCase();
        const list = (status.posts || []).filter(p => `${p.title} ${p.status}`.toLowerCase().includes(query));
        for (const p of list) {
            const tr = row(el('posts'), [`${p.title}\n${p.status}${p.error ? ` · ${p.error}` : ''}`,tokens(p.token_usage),`${Math.round(p.duration_seconds)}초`, '']);
            for (const file of p.files) {
                const button = document.createElement('button');button.type='button';button.textContent = file === 'final.md' ? '완성본 열기' : file;
                button.addEventListener('click', async () => {const request = ++reading;try {const data = await api(`/api/codex/blog/posts/${encodeURIComponent(p.id)}/${encodeURIComponent(file)}`);if (request !== reading) return;el('reader').hidden=false;el('reader-title').textContent=`${p.title} · ${file}`;el('article').textContent=data.content;el('reader').scrollIntoView({behavior:'smooth'});}catch(error){el('feedback').textContent=error.message;}});
                tr.lastChild.append(button);
            }
        }
        if (!list.length) row(el('posts'), ['표시할 집필 작업물이 없습니다.','','','']);
    }
    function render(fillSettings) {
        const d=status.dashboard || {}, p=status.project || {};
        el('progress').textContent = status.configured ? `${d.current_topic || '새 글 준비'} · ${labels[d.current_stage] || d.current_stage} · ${d.completed_stage_count}/${d.total_stage_count} · ${d.is_running ? '실행 중' : p.automatic_paused ? '자동 실행 일시정지' : '대기'}${status.state?.last_error ? ` · ${status.state.last_error}` : ''}` : '아직 설정되지 않았습니다. 블로그 설정에서 방향과 활성화를 저장하세요.';
        el('run').disabled=!status.enabled || Boolean(d.is_running);
        if (fillSettings) for (const key of fields) {const input=el(key);if(input.type === 'checkbox') input.checked=Boolean(p[key] ?? (key === 'topic_rotation_enabled'));else input.value=p[key] ?? ({cadence_minutes:360,daily_run_budget:6,daily_token_budget:300000}[key] || '');}
        posts();el('backlog').replaceChildren();
        for(const item of status.backlog || []) {const li=document.createElement('li');li.textContent=`${item.title} · ${item.status} · ${item.kind || ''}`;el('backlog').append(li);}
        el('runs').replaceChildren();
        for(const r of [...(status.recent_runs || [])].reverse()) row(el('runs'),[`${labels[r.stage] || r.stage} · ${r.status}`,`${r.at || ''} / ${Math.round(r.duration_seconds || 0)}초`,tokens(r.token_usage),`${r.prompt_chars || 0}자 / ${r.context_bytes || 0} B`,r.error || '']);
    }
    async function refresh(fillSettings = false) {try {status=await api('/api/codex/blog');render(fillSettings);el('feedback').textContent='현재 작업공간의 집필 상태를 불러왔습니다.';}catch(error){el('feedback').textContent=error.message;}}
    el('refresh').addEventListener('click', () => refresh());
    el('search').addEventListener('input', posts);
    el('settings').addEventListener('submit',async event => {event.preventDefault();const button=event.submitter;button.disabled=true;try {const payload={};for(const key of fields){const input=el(key);payload[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;}status=await api('/api/codex/blog',{method:'PUT',body:JSON.stringify(payload)});render(true);el('feedback').textContent='설정을 저장했습니다.';}catch(error){el('feedback').textContent=error.message;}finally{button.disabled=false;}});
    el('run').addEventListener('click',async()=>{el('run').disabled=true;try{await api('/api/codex/blog/run',{method:'POST',body:JSON.stringify({force:true})});await refresh();}catch(error){el('feedback').textContent=error.message;el('run').disabled=false;}});
    void refresh(true);
})();
