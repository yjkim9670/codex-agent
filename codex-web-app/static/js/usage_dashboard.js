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
  const chartStates = new Map();
  const dateLabel = value => value ? new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul'}) : '미확인';
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
  const reliable = q => q.groups >= 3 && Number.isFinite(q.pp_per_million_tokens) && q.pp_per_million_tokens >= 0;
  const observedRate = q => reliable(q) ? rate(q.pp_per_million_tokens) : '—';
  function compare() {
    const items = rows().filter(row => reliable(quota(windowName, row.key))).sort((a,b) => (quota(windowName,b.key).pp_per_million_tokens || 0) - (quota(windowName,a.key).pp_per_million_tokens || 0));
    const max = Math.max(...items.map(r => quota(windowName,r.key).pp_per_million_tokens || 0), 1);
    $('comparison').innerHTML = items.map((row,i) => {
      const q = quota(windowName,row.key);
      return `<div class="bar-row"><button type="button" class="bar-label" data-key="${esc(row.key)}">${esc(name(row.model))}<br><small>${esc(row.effort)}</small></button><div class="bar-track"><div class="bar-fill" style="width:${(q.pp_per_million_tokens || 0)/max*100}%;background:${palette[i%palette.length]}"></div></div><div class="bar-value"><strong>${rate(q.pp_per_million_tokens)}</strong> ${q.groups ? '%p' : ''}<br>${num(q.groups || 0)}구간 · 관측값</div></div>`;
    }).join('') || '<p class="empty">검증 구간 3개 이상인 모델/effort가 없습니다. 전체 사용량은 모델 상세에서 확인하세요.</p>';
    showGroups();
  }
  function showGroups(key) {
    const window = report.windows[windowName];
    const groups = window.groups.filter(g => !key || (report.effort === 'all' ? `${g.model}/${g.reasoning_effort}` : g.model) === key);
    $('groups').innerHTML = `<p class="note">${Object.entries(window.excluded).map(([k,v]) => `${esc(k)}: ${v}`).join(' · ') || '제외 구간 없음'}</p><div class="table-wrap"><table><thead><tr><th>모델 / effort</th><th>관측 시각</th><th>토큰</th><th>차감 %p</th></tr></thead><tbody>${groups.map(g => `<tr><td>${esc(name(g.model))} / ${esc(g.reasoning_effort)}</td><td>${esc(dateLabel(g.observed_at))}</td><td>${num(g.tokens)}</td><td>${rate(g.deduction_pp)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  const dayMs = 86400000;
  const dayDate = day => new Date(`${day}T00:00:00Z`);
  const isoDay = date => date.toISOString().slice(0,10);
  function periodBuckets(kind) {
    const first = dayDate(report.start.slice(0,10)), last = dayDate(report.end.slice(0,10));
    const buckets = new Map();
    for (let time = +first; time <= +last; time += dayMs) {
      const day = isoDay(new Date(time)), anchor = new Date(time);
      if (kind === 'month') anchor.setUTCDate(1);
      else anchor.setUTCDate(anchor.getUTCDate() - (anchor.getUTCDay() + 6) % 7);
      const key = isoDay(anchor);
      if (!buckets.has(key)) {
        const finish = new Date(+anchor);
        if (kind === 'month') finish.setUTCMonth(finish.getUTCMonth()+1);
        else finish.setUTCDate(finish.getUTCDate()+7);
        buckets.set(key, {key, finish: isoDay(new Date(+finish-dayMs)), from: day, to: day, tokens: 0, days: 0});
      }
      const bucket = buckets.get(key), values = report.daily[day];
      bucket.to = day;
      bucket.tokens += Object.values(values || {}).reduce((total,value) => total+value,0);
      if (values) bucket.days++;
    }
    return [...buckets.values()].map(bucket => ({...bucket,
      partial: bucket.from !== bucket.key || bucket.to !== bucket.finish || bucket.to === report.end.slice(0,10)
    }));
  }
  function periodRows(buckets, kind) {
    return [...buckets].reverse().map(bucket => `<tr><td>${esc(kind === 'month' ? bucket.key.slice(0,7) : `${bucket.key} 주`)}${bucket.partial ? ' <small>일부 기간</small>' : ''}<br><small>${esc(bucket.from)} ~ ${esc(bucket.to)}</small></td><td>${num(bucket.tokens)}</td><td>${num(bucket.days)}일</td></tr>`).join('');
  }
  function chart(container, series, max, format, settings = {}) {
    const host = $(container), state = chartStates.get(container) || {zoom:1};
    Object.assign(state, {series,max,format,settings});
    chartStates.set(container, state);
    const oldScroll = host.querySelector('.chart-scroll')?.scrollLeft || 0;
    const left=58, top=18, width=Math.max(180, host.clientWidth-85)*state.zoom, height=150;
    const bars = settings.buckets;
    const start=+new Date(report.start), end=+new Date(report.end);
    const x=t => left+(new Date(t).getTime()-start)/Math.max(1,end-start)*width;
    const y=v => top+height-(v/Math.max(1,max))*height;
    const timestamps=[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>new Date(a)-new Date(b));
    const positions=timestamps.map((at,i)=>bars ? left+(i+.5)*width/bars.length : x(at));
    const label = settings.label;
    let svg = `<svg width="${width+85}" height="220" viewBox="0 0 ${width+85} 220" role="img" aria-label="${esc(label)}">`;
    [0,.5,1].forEach(v => { svg += `<line x1="${left}" x2="${left+width}" y1="${y(max*v)}" y2="${y(max*v)}" stroke="#ededf0"/><text x="${left-7}" y="${y(max*v)+4}" text-anchor="end">${esc(format(max*v))}</text>`; });
    series.forEach((s,i) => {
      let d='', previous;
      s.points.forEach((p,j) => {
        const px=bars ? positions[j] : x(p.at), py=y(p.value), color=palette[i%palette.length];
        if (bars) {
          const barWidth=Math.min(64,width/bars.length*.65);
          svg += `<rect class="period-bar" data-tokens="${p.value}" x="${px-barWidth/2}" y="${py}" width="${barWidth}" height="${top+height-py}" fill="${color}" fill-opacity="${bars[j].partial ? '.55' : '.9'}"/>`;
        } else {
          d += `${previous && previous.reset && previous.reset === p.reset ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)} `;
          svg += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="2.3" fill="${color}"/>`;
        }
        previous=p;
      });
      if (!bars) svg += `<path d="${d}" fill="none" stroke="${palette[i%palette.length]}" stroke-width="2"/>`;
    });
    if (bars) {
      const step=Math.max(1,Math.ceil(bars.length/Math.max(1,Math.floor(width/85))));
      bars.forEach((b,i)=>{if(i%step===0) svg+=`<text x="${positions[i]}" y="198" text-anchor="middle">${esc(settings.kind==='month' ? b.key.slice(0,7) : b.key.slice(5))}${b.partial ? '*' : ''}</text>`;});
    } else {
      const step = Math.max(1, Math.ceil((end-start)/dayMs / Math.max(1,Math.floor(width/85))));
      for (let time=start; time <= end; time += step*dayMs) {
        svg += `<text x="${x(time)}" y="198" text-anchor="middle">${new Date(time+9*3600000).toISOString().slice(5,10)}</text>`;
      }
    }
    svg += `<line class="chart-crosshair" x1="0" x2="0" y1="${top}" y2="${top+height}" visibility="hidden"/></svg>`;
    const allPoints=series.flatMap(s=>s.points.map(p=>({label:s.label,...p})));
    host.innerHTML = `<div class="chart-viewport"><div class="chart-scroll" tabindex="0" role="region" aria-label="${esc(label)} 가로 스크롤; 좌우 방향키로 값 탐색">${svg}</div><div class="chart-tooltip" role="status" aria-live="polite" hidden></div></div>` + `<div class="legend">${series.map((s,i)=>`<span><i class="dot" style="background:${palette[i%palette.length]}"></i>${esc(s.label)}</span>`).join('')}${bars ? '<span>* 일부 기간 · 옅은 막대로 표시</span>' : ''}</div>` + (allPoints.length ? (bars ? '' : `<details><summary>그래프 데이터 표 보기</summary><div class="table-wrap"><table><thead><tr><th>시각</th><th>항목</th><th>값</th></tr></thead><tbody>${allPoints.map(p=>`<tr><td>${esc(dateLabel(p.at))}</td><td>${esc(p.label)}</td><td>${esc(num(p.value))}</td></tr>`).join('')}</tbody></table></div></details>`) : '<p class="empty">관측 기록이 없습니다.</p>');
    const scroller=host.querySelector('.chart-scroll'), plot=host.querySelector('svg');
    const tooltip=host.querySelector('.chart-tooltip'), crosshair=host.querySelector('.chart-crosshair');
    scroller.scrollLeft=oldScroll;
    let active=-1;
    const hide=()=>{tooltip.hidden=true;crosshair.setAttribute('visibility','hidden');};
    function show(index, pointerX) {
      active=index;
      const at=timestamps[index], px=positions[index], bucket=bars?.[index];
      crosshair.setAttribute('x1',px);crosshair.setAttribute('x2',px);crosshair.setAttribute('visibility','visible');
      tooltip.innerHTML=`<strong>${esc(bucket ? (settings.kind==='month' ? bucket.key.slice(0,7) : `${bucket.key} 주`) : dateLabel(at))}</strong>` + (bucket ? `<div>${esc(bucket.from)} ~ ${esc(bucket.to)}${bucket.partial ? ' · 일부 기간' : ''}</div>` : '') + series.map((s,i)=>{
        const p=s.points.find(p=>p.at===at);
        return p ? `<div class="tooltip-row"><span><i class="dot" style="background:${palette[i%palette.length]}"></i>${esc(s.label)}</span><b>${esc(num(p.value))}${container==='quota-chart' ? '%' : ' 토큰'}</b></div>` : '';
      }).join('') + (bucket ? `<div>기록 있는 날 ${bucket.days}일</div>` : '');
      tooltip.hidden=false;
      const available=host.querySelector('.chart-viewport').clientWidth;
      const localX=pointerX ?? px-scroller.scrollLeft;
      tooltip.style.left=`${Math.max(0,Math.min(localX+12,available-tooltip.offsetWidth))}px`;
    }
    plot.addEventListener('pointermove',e=>{
      const bounds=plot.getBoundingClientRect(), px=e.clientX-bounds.left, py=e.clientY-bounds.top;
      if (!timestamps.length || px<left || px>left+width || py<top || py>top+height) {hide();return;}
      let index=0;
      positions.forEach((value,i)=>{if(Math.abs(value-px)<Math.abs(positions[index]-px)) index=i;});
      show(index,e.clientX-scroller.getBoundingClientRect().left);
      // Track the cursor itself, while the panel identifies the nearest observed timestamp.
      crosshair.setAttribute('x1',px);crosshair.setAttribute('x2',px);
    });
    scroller.addEventListener('pointerleave',hide);
    scroller.addEventListener('scroll',hide);
    scroller.addEventListener('blur',hide);
    scroller.addEventListener('keydown',e=>{
      if(e.key==='Escape') hide();
      if(!timestamps.length || !['ArrowLeft','ArrowRight'].includes(e.key)) return;
      e.preventDefault();
      const next=active<0 ? 0 : Math.max(0,Math.min(timestamps.length-1,active+(e.key==='ArrowRight'?1:-1)));
      const px=positions[next];
      if(px<scroller.scrollLeft+left || px>scroller.scrollLeft+scroller.clientWidth-25) scroller.scrollLeft=Math.max(0,px-scroller.clientWidth/2);
      show(next);
    });
    $(`${container}-zoom-level`).textContent=`${state.zoom}×`;
    document.querySelector(`[data-chart="${container}"][data-zoom="out"]`).disabled=state.zoom===1;
    document.querySelector(`[data-chart="${container}"][data-zoom="in"]`).disabled=state.zoom===8;
  }
  function tokenTick(value) {
    if (value >= 1e6) return `${(value/1e6).toFixed(1)}M`;
    if (value >= 1e3) return `${(value/1e3).toFixed(1)}K`;
    return num(Math.round(value));
  }
  function renderCharts() {
    const days=[];
    for(let time=+dayDate(report.start.slice(0,10));time<=+dayDate(report.end.slice(0,10));time+=dayMs) days.push(isoDay(new Date(time)));
    const tokenSeries=Object.keys(report.models).map(m=>({label:name(m),points:days.map(day=>({at:`${day}T00:00:00+09:00`,value:report.daily[day]?.[m] || 0,reset:'daily'}))}));
    chart('token-chart',tokenSeries,Math.max(1,...tokenSeries.flatMap(s=>s.points.map(p=>p.value))),tokenTick,{label:'날짜별 모델 토큰'});
    chart('quota-chart',['five_hour','weekly'].map((w,i)=>({label:i?'주간':'5시간',points:report.quota_samples.filter(s=>s[`${w}_used_percent`] != null).map(s=>({at:s.limits_observed_at,value:s[`${w}_used_percent`],reset:s[`${w}_resets_at`]})).sort((a,b)=>new Date(a.at)-new Date(b.at))})),100,v=>`${v}%`,{label:'계정 한도 사용률'});
    for (const [kind,id,label] of [['month','monthly-chart','월간 사용량'],['week','weekly-chart','주간 사용량']]) {
      const buckets=periodBuckets(kind);
      $(`${kind==='month' ? 'monthly' : 'weekly'}-rows`).innerHTML=periodRows(buckets,kind);
      chart(id,[{label:'수집 토큰',points:buckets.map(b=>({at:`${b.key}T00:00:00+09:00`,value:b.tokens}))}],Math.max(1,...buckets.map(b=>b.tokens)),tokenTick,{label,buckets,kind});
    }
  }

  function render() {
    options($('accounts'), report.accounts.accounts.map(a => [a.id,a.label]), '활성 계정');
    options($('environments'), report.environments.map(v => [v,v]), '전체 환경');
    const effort=form.elements.effort;
    const selected=effort.value;
    const efforts=[...new Set(['medium','low','high','xhigh',...report.efforts])];
    effort.innerHTML='<option value="all">전체 모델 / effort</option>'+efforts.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
    effort.value=selected;
    $('status').textContent = `수집 ${dateLabel(report.collected_at)} · 한도 조회 ${dateLabel(report.limits_observed_at)} · 한국시간 ${report.start.slice(0,10)} ~ ${report.end.slice(0,10)} · 1분마다 화면 갱신`;
    $('summary').innerHTML=[['수집 토큰',num(report.total_tokens)],['현재 5시간 사용률',report.current_limits.five_hour?.used_percent == null ? '미확인' : `${report.current_limits.five_hour.used_percent}%`],['현재 주간 사용률',report.current_limits.weekly?.used_percent == null ? '미확인' : `${report.current_limits.weekly.used_percent}%`],['수집 환경',num(report.environments.length)]].map(([label,value])=>`<div class="metric"><span>${label}</span><strong>${esc(value)}</strong></div>`).join('');
    compare();
    $('model-rows').innerHTML=rows().sort((a,b)=>b.tokens-a.tokens).map(row=>{
      const f=quota('five_hour',row.key),w=quota('weekly',row.key);
      return `<tr><td>${esc(name(row.model))} / ${esc(row.effort)}</td><td>${num(row.tokens)}</td><td>${num(f.tokens || 0)}</td><td>${observedRate(f)}</td><td>${num(f.groups || 0)}</td><td>${num(w.tokens || 0)}</td><td>${observedRate(w)}</td><td>${num(w.groups || 0)}</td></tr>`;
    }).join('');
    renderCharts();
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
      report=data;
      $('status').classList.remove('warning');
      render();
    } catch(error) {
      if(error.name==='AbortError') return;
      $('status').textContent=`통계를 불러오지 못했습니다: ${error.message}`;
      $('status').classList.add('warning');
    }
  }
  document.querySelectorAll('[data-zoom]').forEach(button=>button.addEventListener('click',()=>{
    const id=button.dataset.chart, state=chartStates.get(id);
    if(!report || !state) return;
    state.zoom=button.dataset.zoom==='reset' ? 1 : Math.max(1,Math.min(8,state.zoom*(button.dataset.zoom==='in' ? 2 : .5)));
    chart(id,state.series,state.max,state.format,state.settings);
    if(button.dataset.zoom==='reset') $(id).querySelector('.chart-scroll').scrollLeft=0;
  }));
  let resizeFrame;
  window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(report) renderCharts();});});
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
