// Real browser -> Web Crypto -> Python AESGCM -> SQLite/SSE -> browser rendering.
const {expect}=require('@playwright/test');
const assert=require('node:assert/strict');

async function verifyConversation(browser,targetUrl){
 for(const width of [360,768,1440,1920]){
  const prefix=width===360?'':width===768?'/apps/workbench-chat':'/chat';
  const context=await browser.newContext({viewport:{width,height:900},ignoreHTTPSErrors:process.env.CODEX_VERIFY_LOCAL_TLS==='1'});
  try{
  await context.addInitScript(()=>{Object.defineProperty(Crypto.prototype,'randomUUID',{value:undefined,configurable:true});});
  const page=await context.newPage(),errors=[],wire=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('request',request=>{if(new URL(request.url()).pathname.includes('/api/'))wire.push({url:request.url(),body:request.postData()||''});});
  await page.goto(targetUrl+prefix+'/');
  await page.evaluate(()=>chatReady);await expect(page.locator('#model')).toHaveValue('test-model');
  await expect(page.locator('#transport-status')).toContainText('AES-256-GCM');
  await page.evaluate(()=>{
   window.__paths=[];window.__markdownCalls=0;
   const open=transport.open.bind(transport);transport.open=(path,...args)=>{window.__paths.push(path);return open(path,...args);};
   marked.use({hooks:{preprocess(text){window.__markdownCalls++;return text;}}});
  });
  if(width===360)await page.evaluate(()=>{
   const stream=transport.stream.bind(transport);let broken=false;
   transport.stream=async function*(...args){for await(const chunk of stream(...args)){yield chunk;if(!broken){broken=true;throw Error('fixture: interrupted stream');}}};
  });
  assert.deepEqual(await page.evaluate(()=>['old.trycloudflare.com','new.trycloudflare.com','chat.example.ts.net','trycloudflare.com.evil.test'].map(prefersPolling)),[true,true,false,false]);
  if(width===768)await page.evaluate(()=>{prefersPolling=()=>true;});
  if(width>=1440)await page.evaluate(width=>{
   // Simulate a proxy that never sends headers, or stalls after its first body chunk.
   const fetchOriginal=window.fetch,stream=transport.stream.bind(transport);let stallNext=false;
   transport.stream=async function*(...args){stallNext=true;yield* stream(...args,200);};
   window.fetch=async(url,options)=>{
    if(!stallNext||!String(url).endsWith('/api/secure'))return fetchOriginal(url,options);
    stallNext=false;
    if(width===1440)return new Promise((resolve,reject)=>{options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});});
    const response=await fetchOriginal(url,options),reader=response.body.getReader();
    return new Response(new ReadableStream({async start(controller){
     options.signal.addEventListener('abort',()=>{controller.error(options.signal.reason);reader.cancel().catch(()=>{});},{once:true});
     const {value,done}=await reader.read();if(!done)controller.enqueue(value);
    },cancel(){return reader.cancel().catch(()=>{});}}),{headers:response.headers});
   };
  },width);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${width}`);
  await page.locator('[data-mode=translate]').click();await expect(page.locator('#search')).toHaveValue('off');await expect(page.locator('#translation-options')).toBeVisible();
  await page.locator('#message').fill('내일 회의할까요?');
  await page.locator('#message').dispatchEvent('keydown',{key:'Enter',keyCode:229,isComposing:true});
  assert.equal(await page.evaluate(()=>window.__paths.some(x=>x.endsWith('/messages'))),false);
  await page.locator('#send').click();await expect(page.locator('.answer-body.streaming')).toContainText('Hello');
  assert.equal(await page.evaluate(()=>window.__markdownCalls),0,'no Markdown parsing per delta');
  await expect(page.locator('.answer-body strong')).toHaveText('Hello');await expect(page.locator('#stop')).toBeHidden();
  assert.equal(await page.locator('.answer-body').evaluate(el=>(el.textContent.match(/Hello/g)||[]).length),1,'resume must not duplicate deltas');
  assert.equal(await page.evaluate(()=>window.__markdownCalls),1,'one Markdown parse on completion');
  assert.ok(await page.evaluate(()=>window.__paths.some(x=>x.includes('/poll?after='))),'JSON polling used after proxy failure or Quick Tunnel selection');
  assert.ok(await page.evaluate(()=>window.__paths.filter(x=>/\/messages$/.test(x)).length)<=3,'POST plus initial/final snapshots only');
  assert.equal(await page.evaluate(()=>window.xss),undefined);await expect(page.locator('.answer-body a[href^="javascript:"]')).toHaveCount(0);
  await expect(page.locator('.code-block')).toHaveCount(1);await expect(page.locator('.code-toolbar button')).toHaveText('코드 복사');
  await expect(page.locator('.answer-body blockquote')).toContainText('읽기 쉬운');await expect(page.locator('.answer-body th')).toHaveCount(2);
  assert.ok((await page.locator('.answer-body pre code').evaluate(el=>getComputedStyle(el).fontFamily)).includes('Chat Code'));
  assert.equal(await page.locator('.answer-body a[href="https://example.com/"]').getAttribute('rel'),'noopener noreferrer');
  if(width>=1440){const composer=await page.locator('.composer-inner').boundingBox();assert.ok(composer.width>1000,`desktop composer width ${composer.width}`);const answer=await page.locator('.answer').boundingBox();assert.ok(answer.width>1000,`desktop answer width ${answer.width}`);}
  await page.evaluate(()=>{window.__firstAnswer=document.querySelector('.answer-body');window.__mutations=0;window.__observer=new MutationObserver(rows=>window.__mutations+=rows.length);window.__observer.observe(window.__firstAnswer,{subtree:true,childList:true,characterData:true});});
  await page.locator('#message').fill('cancel me');await page.locator('#send').click();await expect(page.locator('.answer-body.streaming')).toBeVisible();
  await page.locator('#stop').click();await expect(page.locator('#stop')).toBeHidden();await expect(page.locator('.answer .meta').last()).toContainText('중단된 부분');
  assert.ok(await page.evaluate(()=>window.__firstAnswer===document.querySelector('.answer-body')),'preserve completed DOM');
  assert.equal(await page.evaluate(()=>window.__mutations),0,'do not mutate completed Markdown');
  await page.locator('#preferences').click();await page.locator('#theme').selectOption('dark');await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(22, 22, 22)');
  for(const font of ['ibm-plex','suit','nanum-square','wanted-sans','line-seed-kr','goorm-sans','paperlogy','nexon-lv2-gothic']){
   await page.locator('#font').selectOption(font);await expect(page.locator('html')).toHaveAttribute('data-ui-font',font);
   const family=await page.evaluate(()=>getComputedStyle(document.body).fontFamily.split(',')[0]);
   assert.ok(await page.evaluate(async family=>(await document.fonts.load('16px '+family,'안녕')).length>0,family),`font failed ${font}: ${family}`);
  }
  await page.locator('#settings-dialog button').click();await page.locator('#message').fill('보존할 초안');await page.reload();
  await expect(page.locator('#message')).toHaveValue('보존할 초안');await expect(page.locator('html')).toHaveAttribute('data-ui-font','nexon-lv2-gothic');await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  if(width<1024){await page.locator('#show-history').click();await expect(page.locator('#sidebar')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('#sidebar')).not.toBeVisible();await expect(page.locator('#show-history')).toBeFocused();}
  await page.locator('#usage').click();await expect(page.locator('#usage-summary')).toContainText('tokens');await expect(page.locator('#dialog-limits')).toContainText('76% 남음');await expect(page.locator('#dialog-limits')).toContainText('40% 남음');
  await expect(page.locator('#dialog-limits progress').first()).toHaveAttribute('value','24');
  await page.evaluate(async()=>{await fetch(appUrl('/__fixture/limits/fail'),{method:'POST',headers:{'X-Chat-CSRF':csrf}});});
  await page.locator('#refresh-limits').click();await expect(page.locator('#dialog-limits-status')).toContainText('조회 실패');await expect(page.locator('#dialog-limits')).toContainText('미제공');
  await page.evaluate(async()=>{await fetch(appUrl('/__fixture/limits/ok'),{method:'POST',headers:{'X-Chat-CSRF':csrf}});});
  await page.locator('#refresh-limits').click();await expect(page.locator('#dialog-limits')).toContainText('76% 남음');await page.locator('#usage-dialog .primary').click();
  // An expired session is renewed before retry; a plaintext response is never accepted.
  await page.evaluate(()=>{transport.channel.expires=0;});
  await page.locator('#usage').click();await expect(page.locator('#usage-summary')).toContainText('tokens');await page.locator('#usage-dialog .primary').click();
  if(width===1920){
   await context.grantPermissions(['clipboard-read','clipboard-write']);await page.locator('.code-toolbar button').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'print("hello")\n');
   // Deterministic load fixture: a 60k-character in-flight answer and 150 history rows.
   const metrics=await page.evaluate(()=>{
    const original=state.messages;const history=Array.from({length:150},(_,i)=>({id:'perf-'+i,content:'지난 질문 '+i,attempts:[{...original[0].attempts[0],id:'perf-a-'+i,text:'완료된 답변',citations:[]}]}));
    const live={...original[0].attempts[0],id:'perf-active',status:'streaming',text:'장문 응답 '.repeat(10000),citations:[]};history.push({id:'perf-last',content:'계속',attempts:[live]});
    render(history);window.__markdownCalls=0;const start=performance.now();for(let i=0;i<100;i++){live.text+='추가';render(history);}const elapsed=performance.now()-start;
    const result={elapsed,parses:window.__markdownCalls,rows:document.querySelectorAll('.message').length};render(original);return result;
   });
   assert.equal(metrics.parses,0);assert.equal(metrics.rows,151);console.log(`Streaming load fixture: 151 rows / 60k chars / 100 updates: ${metrics.elapsed.toFixed(1)} ms, 0 Markdown parses`);
  }
  assert.ok(wire.length>0);for(const request of wire){assert.ok(['/api/crypto-session','/api/secure'].some(s=>new URL(request.url).pathname===prefix+s),'only encrypted API endpoints');assert.ok(!request.url.includes('?'),'no plaintext query strings');assert.ok(!request.body.includes('내일 회의할까요?')&&!request.body.includes('cancel me'),'no plaintext prompts');if(request.url.endsWith('/api/secure'))assert.equal(JSON.parse(request.body).encrypted,true);}
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`final overflow ${width}`);assert.deepEqual(errors,[]);
  console.log(`PASS ${width}px · encrypted requests/SSE/poll · timeout/resume/cancel · stable DOM · Markdown/XSS · fonts · dark · limits`);
  }finally{await context.close();}
 }
 // Web Crypto unavailable: fail closed before any API request or plaintext fallback.
 const context=await browser.newContext({ignoreHTTPSErrors:process.env.CODEX_VERIFY_LOCAL_TLS==='1'});try{
  await context.addInitScript(()=>Object.defineProperty(Crypto.prototype,'subtle',{value:undefined,configurable:true}));const page=await context.newPage();let apiRequests=0;page.on('request',r=>{if(r.url().includes('/api/'))apiRequests++;});
  await page.goto(targetUrl+'/');await expect(page.locator('#status')).toContainText('HTTPS');await expect(page.locator('#send')).toBeDisabled();assert.equal(apiRequests,0);
 }finally{await context.close();}
}
module.exports={verifyConversation};
