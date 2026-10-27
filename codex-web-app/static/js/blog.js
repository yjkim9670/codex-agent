(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const labels = {plan:'기획·근거',topic:'주제 선정',brief:'기획',research:'조사',outline:'구성',draft:'초고',review:'검수',select:'새 글 준비'};
    const fields = ['enabled','automatic_paused','topic_direction','audience','style_guide','exclude_ai_topics','allow_web_research','topic_rotation_enabled','cadence_minutes','daily_run_budget','daily_token_budget'];
    let status = {}, reading = 0, selected = null, selectedFile = '', publishedOnly = true, home = true;
    // Normalize titles for display and search; leave saved manuscripts unchanged.
    const displayTitle = title => String(title || '').replace(/^\s*(?:#{1,6}\s+|[-–—]\s+)+/, '').replace(/[-‐‑‒–—―]+/g, ' ').replace(/\s+/g, ' ').trim();
    let renderer;
    function loadRenderer() {
        if (!renderer) renderer = Promise.all(['marked-18.0.6.umd.js','dompurify-3.4.12.min.js'].map(name => new Promise((resolve, reject) => {
            const script = document.createElement('script');script.src = `/static/vendor/${name}`;
            script.onload = resolve;script.onerror = () => {script.remove();reject(new Error('본문 렌더러를 불러오지 못했습니다. 다시 시도하세요.'));};
            document.head.append(script);
        }))).catch(error => {renderer = null;throw error;});
        return renderer;
    }
    async function api(url, options) {
        const response = await fetch(url, {cache:'no-store', ...options, headers:{'Content-Type':'application/json', ...options?.headers}});
        if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error(`API 응답을 읽을 수 없습니다 (HTTP ${response.status}). 로그인 또는 서버 버전을 확인하세요.`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || data.reason || `HTTP ${response.status}`);
        return data;
    }
    function tokens(t = {}) {return ['input_tokens','cached_input_tokens','output_tokens','total_tokens'].map(k => Number(t[k] || 0).toLocaleString()).join(' / ');}
    function row(body, values) {const tr = document.createElement('tr'); for (const value of values) {const td = document.createElement('td');td.textContent = value;tr.append(td);}body.append(tr);return tr;}
    const fileLabels = {'final.md':'완성본','draft.md':'초고','brief.md':'기획','outline.md':'구성','research.md':'조사','review.md':'검수'};
    const readable = p => (p.files || []).filter(f => f.endsWith('.md') || f.endsWith('.json'));
    const published = p => p.status === '완성본 있음';
    function renderArticle(content, file) {
        const article = el('article');
        el('toc').replaceChildren();
        if (file.endsWith('.json')) {
            const pre = document.createElement('pre');pre.textContent = content;article.replaceChildren(pre);
        } else {
            article.innerHTML = DOMPurify.sanitize(marked.parse(content), {USE_PROFILES:{html:true}, FORBID_TAGS:['style','form','input','button']});
        }
        // Keep a single page title when the manuscript repeats it as its first heading.
        const first = article.firstElementChild;
        if (first?.tagName === 'H1' && displayTitle(first.textContent) === displayTitle(selected.title)) first.remove();
        article.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(heading => {
            // Update text nodes only so inline emphasis and links survive.
            const walker=document.createTreeWalker(heading,NodeFilter.SHOW_TEXT);
            while(walker.nextNode()) walker.currentNode.textContent=walker.currentNode.textContent.replace(/[-‐‑‒–—―]+/g, ' ');
        });
        article.querySelectorAll('img').forEach(img => {img.loading='lazy';img.decoding='async';});
        article.querySelectorAll('a').forEach(link => {
            const href = link.getAttribute('href') || '';
            if (/^https?:/i.test(href)) {link.target = '_blank';link.rel = 'noopener noreferrer';}
        });
        article.querySelectorAll('table').forEach(table => {const wrap=document.createElement('div');wrap.className='article-table';table.replaceWith(wrap);wrap.append(table);});
        article.querySelectorAll('h1,h2,h3').forEach((heading, index) => {
            heading.id = `article-heading-${index}`;
            const link=document.createElement('a');link.href=`#${heading.id}`;link.textContent=heading.textContent;
            if (heading.tagName === 'H3') link.className='toc-child';
            el('toc').append(link);
        });
        if (!el('toc').childElementCount) el('toc').textContent='본문을 천천히 읽어보세요.';
    }
    function closeMenu() {
        document.body.classList.remove('menu-open');
        el('menu-toggle').setAttribute('aria-expanded','false');
        el('sidebar-backdrop').hidden=true;
    }
    function showHome(focus = false) {
        home=true; ++reading;
        el('blog-home').hidden=false;el('reading-layout').hidden=true;
        el('home-button').setAttribute('aria-current','page');
        el('reader').setAttribute('aria-busy','false');closeMenu();posts(false);
        if(focus) {el('blog-content').focus();window.scrollTo({top:0});}
    }
    async function openPost(post, file = '', focus = true) {
        home=false;el('blog-home').hidden=true;el('reading-layout').hidden=false;
        el('home-button').removeAttribute('aria-current');closeMenu();
        if(focus) {el('blog-content').focus();window.scrollTo({top:0});}
        selected = post;
        selectedFile = file || ['final.md','draft.md','brief.md','outline.md'].find(f => post.files.includes(f)) || readable(post)[0];
        const request = ++reading;
        posts(false);
        el('reader-title').textContent=displayTitle(post.title);
        el('reader-category').textContent=published(post) ? '게시글' : '집필 작업물';
        el('reader-meta').textContent=`${post.status} · ${fileLabels[selectedFile] || selectedFile || '작업물 없음'}`;
        el('artifact').replaceChildren();
        for (const name of readable(post)) {const option=document.createElement('option');option.value=name;option.textContent=fileLabels[name] || name;el('artifact').append(option);}
        el('artifact').value=selectedFile || '';
        el('artifact-label').hidden=readable(post).length < 2;
        el('toc').replaceChildren();
        el('article').textContent=selectedFile ? '글을 불러오는 중…' : '아직 읽을 수 있는 작업물이 없습니다. 집필이 진행되면 이곳에 표시됩니다.';
        el('reader').setAttribute('aria-busy',String(Boolean(selectedFile)));
        if (!selectedFile) return;
        try {
            const [data]=await Promise.all([api(`/api/codex/blog/posts/${encodeURIComponent(post.id)}/${encodeURIComponent(selectedFile)}`), selectedFile.endsWith('.json') ? Promise.resolve() : loadRenderer()]);
            if (request !== reading) return;
            renderArticle(data.content,selectedFile);
            const minutes=Math.max(1,Math.ceil(data.content.length / 500));
            el('reader-meta').textContent+=` · 약 ${minutes}분 읽기`;
        } catch(error) {
            if (request !== reading) return;
            el('article').textContent='글을 불러오지 못했습니다. 새로고침으로 다시 시도하세요.';
            el('feedback').textContent=error.message;
        } finally {if(request === reading) el('reader').setAttribute('aria-busy','false');}
    }
    function posts(renderCards = true) {
        el('posts').replaceChildren();
        const query=el('search').value.trim().toLowerCase();
        const all=status.posts || [];
        const list=all.filter(p => (!publishedOnly || published(p)) && `${displayTitle(p.title)} ${p.status}`.toLowerCase().includes(displayTitle(query)));
        el('post-count').textContent=list.length;
        for (const p of list) {
            const button=document.createElement('button');button.type='button';button.className='post-link';
            if (!home && selected?.id === p.id) button.setAttribute('aria-current','page');
            const title=document.createElement('span');title.textContent=displayTitle(p.title);
            const meta=document.createElement('small');meta.textContent=p.status;
            button.append(title,meta);button.addEventListener('click',()=>void openPost(p));el('posts').append(button);
        }
        if (!renderCards) return;
        el('story-count').textContent=`${list.length}개의 글`;
        el('featured-post').replaceChildren();el('story-grid').replaceChildren();
        const featured=list.find(published);
        for (const p of list) {
            const card=document.createElement('button');card.type='button';
            card.className=p === featured ? 'featured-card' : 'story-card';
            const kicker=document.createElement('span');kicker.className='card-kicker';
            kicker.textContent=p === featured ? 'LATEST STORY · 최신 이야기' : published(p) ? 'JOURNAL · 완성된 글' : 'IN PROGRESS · 집필 중';
            const title=document.createElement(p === featured ? 'h2' : 'h3');title.textContent=displayTitle(p.title);
            const action=document.createElement('span');action.className='card-action';action.textContent=published(p) ? '이야기 읽기  ↗' : '작업물 살펴보기  ↗';
            card.append(kicker,title,action);card.addEventListener('click',()=>void openPost(p));
            el(p === featured ? 'featured-post' : 'story-grid').append(card);
        }
        if (!list.length) {
            const empty=document.createElement('p');empty.className='home-empty';
            empty.textContent=query ? '검색 결과가 없습니다. 다른 제목으로 찾아보세요.' : '첫 이야기를 기다리고 있어요. 전체 글에서 집필 중인 이야기를 살펴보세요.';
            el('story-grid').append(empty);
        }
        if (!list.length) {const empty=document.createElement('p');empty.className='list-empty';empty.textContent=query ? '검색 결과가 없습니다.' : publishedOnly ? '아직 완성된 글이 없습니다. 전체 글에서 집필 중인 글을 확인하세요.' : '아직 집필한 글이 없습니다.';el('posts').append(empty);}
    }
    function chooseInitialPost() {
        const all=status.posts || [];
        const previous=all.find(p => p.id === selected?.id);
        const post=previous || all.find(published) || all.find(p => readable(p).length) || all[0];
        if (post) {
            if (!published(post) && !all.some(published)) setFilter(false);
            void openPost(post,previous?.files.includes(selectedFile) ? selectedFile : '',false);
        } else {
            ++reading;selected=null;selectedFile='';
            el('reader-title').textContent='첫 이야기를 기다리고 있어요';
            el('reader-meta').textContent='Workbench Blog';el('artifact-label').hidden=true;
            el('article').textContent='아직 작성된 글이 없습니다. 아래 집필 관리에서 블로그를 설정하고 첫 글을 시작해보세요.';
            el('toc').replaceChildren();el('reader').setAttribute('aria-busy','false');
        }
    }
    function setFilter(value) {
        publishedOnly=value;
        el('filter-published').setAttribute('aria-pressed',String(value));
        el('filter-all').setAttribute('aria-pressed',String(!value));posts();
    }
    function render(fillSettings) {
        const d=status.dashboard || {}, p=status.project || {};
        el('progress').textContent = status.configured ? `${displayTitle(d.current_topic) || '새 글 준비'} · ${labels[d.current_stage] || d.current_stage} · ${d.completed_stage_count}/${d.total_stage_count} · ${d.is_running ? '실행 중' : p.automatic_paused ? '자동 실행 일시정지' : '대기'}${status.state?.last_error ? ` · ${status.state.last_error}` : ''}` : '아직 설정되지 않았습니다. 블로그 설정에서 방향과 활성화를 저장하세요.';
        el('run').disabled=!status.enabled || Boolean(d.is_running);
        if (fillSettings) for (const key of fields) {const input=el(key);if(input.type === 'checkbox') input.checked=Boolean(p[key] ?? (key === 'topic_rotation_enabled'));else input.value=p[key] ?? ({cadence_minutes:360,daily_run_budget:6,daily_token_budget:300000}[key] || '');}
        if (!home) chooseInitialPost();
        posts();el('backlog').replaceChildren();
        for(const item of status.backlog || []) {const li=document.createElement('li');li.textContent=`${displayTitle(item.title)} · ${item.status} · ${item.kind || ''}`;el('backlog').append(li);}
        el('runs').replaceChildren();
        for(const r of [...(status.recent_runs || [])].reverse()) row(el('runs'),[`${labels[r.stage] || r.stage} · ${r.status}`,`${r.at || ''} / ${Math.round(r.duration_seconds || 0)}초`,tokens(r.token_usage),`${r.prompt_chars || 0}자 / ${r.context_bytes || 0} B`,r.error || '']);
    }
    async function refresh(fillSettings = false) {try {status=await api('/api/codex/blog');render(fillSettings);el('feedback').textContent='현재 작업공간의 집필 상태를 불러왔습니다.';}catch(error){el('feedback').textContent=error.message;}}
    document.querySelector('.manage-link').addEventListener('click',()=>{closeMenu();el('blog-management').open=true;});
    el('menu-toggle').addEventListener('click',()=>{
        const open=!document.body.classList.contains('menu-open');
        document.body.classList.toggle('menu-open',open);el('menu-toggle').setAttribute('aria-expanded',String(open));el('sidebar-backdrop').hidden=!open;
        if(open) el('home-button').focus();
    });
    el('sidebar-backdrop').addEventListener('click',closeMenu);
    document.addEventListener('keydown',event=>{
        if(event.key==='Escape' && document.body.classList.contains('menu-open')) {closeMenu();el('menu-toggle').focus();}
        if(event.key==='Tab' && document.body.classList.contains('menu-open')) {
            const items=[el('menu-toggle'),...el('blog-sidebar').querySelectorAll('a,button,input')];
            const first=items[0],last=items[items.length-1];
            if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
            else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
        }
    });
    matchMedia('(min-width:961px)').addEventListener('change',event=>{if(event.matches) closeMenu();});
    el('article-toc').open=matchMedia('(min-width:1500px)').matches;
    el('home-button').addEventListener('click',()=>showHome(true));
    el('back-home').addEventListener('click',()=>showHome(true));
    document.querySelector('[data-blog-home]').addEventListener('click',event=>{event.preventDefault();showHome(true);});
    el('filter-published').addEventListener('click',()=>setFilter(true));
    el('filter-all').addEventListener('click',()=>setFilter(false));
    el('artifact').addEventListener('change',()=>{if(selected) void openPost(selected,el('artifact').value);});
    el('refresh').addEventListener('click', () => refresh());
    let searchTimer;
    el('search').addEventListener('input', () => {clearTimeout(searchTimer);searchTimer=setTimeout(posts,120);});
    el('settings').addEventListener('submit',async event => {event.preventDefault();const button=event.submitter;button.disabled=true;try {const payload={};for(const key of fields){const input=el(key);payload[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;}status=await api('/api/codex/blog',{method:'PUT',body:JSON.stringify(payload)});render(true);el('feedback').textContent='설정을 저장했습니다.';}catch(error){el('feedback').textContent=error.message;}finally{button.disabled=false;}});
    el('run').addEventListener('click',async()=>{el('run').disabled=true;try{await api('/api/codex/blog/run',{method:'POST',body:JSON.stringify({force:true})});await refresh();}catch(error){el('feedback').textContent=error.message;el('run').disabled=false;}});
    void refresh(true);
})();
