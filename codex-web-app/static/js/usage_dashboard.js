'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const form = $('filters');
  const nf = new Intl.NumberFormat('ko-KR');
  const num = n => n == null ? '미확인' : nf.format(n);
  const rate = n => n == null ? '관측 부족' : n.toFixed(3);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const name = model => model.replace(/^gpt-/, 'GPT-').replace(/-(sol|terra|astra|luna)$/, ' $1');
  const palette = ['#0071e3','#8856d9','#32a49b','#e79932','#df677e','#6e6e73'];
  let report, windowName = 'five_hour', sequence = 0, abort;
  const dateLabel = value => value ? new Date(value).toLocaleString('ko-KR') : '미확인';
  function options(target, values, label) {
    const value = target.value;
    target.innerHTML = `<option value="${target.id === 'environments' ? 'all' : ''}">${label}</option>` + values.map(([v,l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
    if ([...target.options].some(o => o.value === value)) target.value = value;
  }
  function rows() {
    if (report.effort === 'all') return Object.entries(report.model_efforts).map(([key,r]) => ({key, model:r.model, effort:r.reasoning_effort, tokens:r.total_tokens}));
    return Object.entries(report.models).map(([key,r]) => ({key, model:key, effort:report.effort, tokens:r.total_tokens}));
  }
  function quota(w, key) { return (report.effort === 'all' ? report.windows[w].model_efforts : report.windows[w].models)[key] || {}; }
  function compare() {
    const items = rows().sort((a,b) => (quota(windowName,b.key).pp_per_million_tokens || 0) - (quota(windowName,a.key).pp_per_million_tokens || 0));
    const max = Math.max(...items.map(r => quota(windowName,r.key).pp_per_million_tokens || 0), 1);
    $('comparison').innerHTML = items.map((row,i) => {
      const q = quota(windowName,row.key);
      return `<div class="bar-row"><button type="button" class="bar-label" data-key="${esc(row.key)}">${esc(name(row.model))}<br><small>${esc(row.effort)}</small></button><div class="bar-track"><div class="bar-fill" style="width:${(q.pp_per_million_tokens || 0)/max*100}%;background:${palette[i%palette.length]}"></div></div><div class="bar-value"><strong>${rate(q.pp_per_million_tokens)}</strong> ${q.groups ? '%p' : ''}<br>${num(q.groups || 0)}구간 · ${q.groups >= 3 ? '관측값' : '관측 부족'}</div></div>`;
    }).join('') || '<p class="empty">선택한 조건의 사용 기록이 없습니다.</p>';
    showGroups();
  }
  function showGroups(key) {
    const window = report.windows[windowName];
    const groups = window.groups.filter(g => !key || (report.effort === 'all' ? `${g.model}/${g.reasoning_effort}` : g.model) === key);
    $('groups').innerHTML = `<p class="note">${Object.entries(window.excluded).map(([k,v]) => `${esc(k)}: ${v}`).join(' · ') || '제외 구간 없음'}</p><div class="table-wrap"><table><thead><tr><th>모델 / effort</th><th>관측 시각</th><th>토큰</th><th>차감 %p</th></tr></thead><tbody>${groups.map(g => `<tr><td>${esc(name(g.model))} / ${esc(g.reasoning_effort)}</td><td>${esc(dateLabel(g.observed_at))}</td><td>${num(g.tokens)}</td><td>${rate(g.deduction_pp)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function chart(container, series, max, format) {
    const left=48, top=18, width=430, height=150;
    const start=new Date(report.start).getTime(), end=new Date(report.end).getTime();
    const x=t => left+(new Date(t).getTime()-start)/Math.max(1,end-start)*width;
    const y=v => top+height-(v/Math.max(1,max))*height;
    let svg = `<svg viewBox="0 0 510 210" role="img" aria-label="${esc(container === 'token-chart' ? '날짜별 모델 토큰 추이' : '계정 5시간 주간 한도 사용률 추이')}">`;
    [0,.5,1].forEach(v => { svg += `<line x1="${left}" x2="${left+width}" y1="${y(max*v)}" y2="${y(max*v)}" stroke="#ededf0"/><text x="${left-7}" y="${y(max*v)+4}" text-anchor="end">${esc(format(max*v))}</text>`; });
    series.forEach((s,i) => {
      let d='', previous;
      s.points.forEach(p => {
        d += `${previous && previous.reset && previous.reset === p.reset ? 'L' : 'M'}${x(p.at).toFixed(1)},${y(p.value).toFixed(1)} `;
        svg += `<circle cx="${x(p.at).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="2.3" fill="${palette[i%palette.length]}"><title>${esc(s.label)} · ${esc(dateLabel(p.at))}: ${esc(num(p.value))}</title></circle>`;
        previous=p;
      });
      svg += `<path d="${d}" fill="none" stroke="${palette[i%palette.length]}" stroke-width="2"/>`;
    });
    svg += `<text x="${left}" y="198">${esc(report.start.slice(5,10))}</text><text x="${left+width}" y="198" text-anchor="end">${esc(report.end.slice(5,10))}</text></svg>`;
    const allPoints=series.flatMap(s=>s.points.map(p=>({label:s.label,...p})));
    $(container).innerHTML = svg + `<div class="legend">${series.map((s,i)=>`<span><i class="dot" style="background:${palette[i%palette.length]}"></i>${esc(s.label)}</span>`).join('')}</div>` + (allPoints.length ? `<details><summary>그래프 데이터 표 보기</summary><div class="table-wrap"><table><thead><tr><th>시각</th><th>항목</th><th>값</th></tr></thead><tbody>${allPoints.map(p=>`<tr><td>${esc(dateLabel(p.at))}</td><td>${esc(p.label)}</td><td>${esc(num(p.value))}</td></tr>`).join('')}</tbody></table></div></details>` : '<p class="empty">관측 기록이 없습니다.</p>');
  }
  function render() {
    options($('accounts'), report.accounts.accounts.map(a => [a.id,a.label]), '활성 계정');
    options($('environments'), report.environments.map(v => [v,v]), '전체 환경');
    const effort=form.elements.effort;
    const selected=effort.value;
    const efforts=[...new Set(['medium','low','high','xhigh',...report.efforts])];
    effort.innerHTML='<option value="all">전체</option>'+efforts.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
    effort.value=selected;
    $('status').textContent = `수집 ${dateLabel(report.collected_at)} · 한도 조회 ${dateLabel(report.limits_observed_at)} · 한국시간 ${report.start.slice(0,10)} ~ ${report.end.slice(0,10)} · 1분마다 화면 갱신`;
    $('summary').innerHTML=[['수집 토큰',num(report.total_tokens)],['현재 5시간 사용률',report.current_limits.five_hour?.used_percent == null ? '미확인' : `${report.current_limits.five_hour.used_percent}%`],['현재 주간 사용률',report.current_limits.weekly?.used_percent == null ? '미확인' : `${report.current_limits.weekly.used_percent}%`],['수집 환경',num(report.environments.length)]].map(([label,value])=>`<div class="metric"><span>${label}</span><strong>${esc(value)}</strong></div>`).join('');
    compare();
    $('model-rows').innerHTML=rows().sort((a,b)=>b.tokens-a.tokens).map(row=>{
      const f=quota('five_hour',row.key),w=quota('weekly',row.key);
      return `<tr><td>${esc(name(row.model))} / ${esc(row.effort)}</td><td>${num(row.tokens)}</td><td>${num(f.tokens || 0)}</td><td>${rate(f.pp_per_million_tokens)}</td><td>${num(f.groups || 0)}</td><td>${num(w.tokens || 0)}</td><td>${rate(w.pp_per_million_tokens)}</td><td>${num(w.groups || 0)}</td></tr>`;
    }).join('');
    const models=Object.keys(report.models);
    const tokenSeries=models.map(m=>({label:name(m),points:Object.entries(report.daily).map(([day,values])=>({at:`${day}T00:00:00+09:00`,value:values[m] || 0,reset:'daily'}))}));
    chart('token-chart',tokenSeries,Math.max(1,...tokenSeries.flatMap(s=>s.points.map(p=>p.value))),v=>`${(v/1e6).toFixed(1)}M`);
    chart('quota-chart',['five_hour','weekly'].map((w,i)=>({label:i?'주간':'5시간',points:report.quota_samples.filter(s=>s[`${w}_used_percent`] != null).map(s=>({at:s.limits_observed_at,value:s[`${w}_used_percent`],reset:s[`${w}_resets_at`]})).sort((a,b)=>new Date(a.at)-new Date(b.at))})),100,v=>`${v}%`);
    const d=report.collection_diagnostics;
    $('collection-note').textContent=`5분 주기 자동 수집 · 실행 완료 후 재대조 · 90일 보관 · 로그 보완 ${num(d.supplemental_tokens || 0)} 토큰 · 날짜/모델 미배분 DB 잔액 ${num(d.unallocated_db_tokens || 0)} 토큰 · 검토 필요 ${num((d.ambiguous_tokens || 0)+(d.quarantined_tokens || 0))} 토큰`;
    const statuses={ok:'정상',error:'수집 오류',account_unverified:'계정 미확인 · 제외',no_session_db:'실행 로그 수집'};
    $('source-rows').innerHTML=report.sources.map(s=>`<tr><td title="${esc(s.home)}">${esc(s.home)}</td><td>${esc(dateLabel(s.last_record_at))}</td><td>${num(s.threads)}</td><td>${esc(statuses[s.status] || s.status)}${s.error ? ` · ${esc(s.error)}` : ''}</td></tr>`).join('');
    $('warnings').textContent=[...report.collection_errors,report.account_refresh_error].filter(Boolean).join(' · ');
    const r=report.reconciliation;
    $('reconciliation-summary').textContent=`비교 가능 ${r.comparable_days}일 · 계정 − 수집 원장 ${num(r.comparable_difference_tokens)} 토큰 · 계정 데이터 없는 날 ${r.account_missing_days}일`;
    $('reconciliation-rows').innerHTML=r.daily.map(d=>`<tr><td>${esc(d.date)}${d.is_partial_day ? ' (진행 중)' : ''}</td><td>${num(d.account_tokens)}</td><td>${num(d.local_tokens)}</td><td>${num(d.difference_tokens)}</td></tr>`).join('');
    $('usage-dashboard').dataset.loaded='true';
  }
  async function load() {
    const current=++sequence;
    if(abort) abort.abort();
    abort=new AbortController();
    $('status').textContent='기록을 불러오는 중…';
    try {
      const response=await fetch(`/api/codex/usage/dashboard?${new URLSearchParams(new FormData(form))}`,{signal:abort.signal});
      const data=await response.json();
      if(!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      if(current!==sequence) return;
      report=data;render();
    } catch(error) {
      if(error.name==='AbortError') return;
      $('status').textContent=`통계를 불러오지 못했습니다: ${error.message}`;
      $('status').classList.add('warning');
    }
  }
  form.addEventListener('submit',e=>e.preventDefault());
  form.addEventListener('change',load);
  $('refresh').addEventListener('click',load);
  document.querySelectorAll('[data-window]').forEach(button=>button.addEventListener('click',()=>{
    windowName=button.dataset.window;
    document.querySelectorAll('[data-window]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    if(report) compare();
  }));
  $('comparison').addEventListener('click',e=>{
    const button=e.target.closest('[data-key]');
    if(button){showGroups(button.dataset.key);$('group-details').open=true;}
  });
  setInterval(()=>{if(!document.hidden) load();},60000);
  load();
})();
