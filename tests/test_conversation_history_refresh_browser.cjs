const {expect}=require('@playwright/test');

async function verifyConversationHistoryRefresh(browser,url){
 const context=await browser.newContext({viewport:{width:1440,height:900}});
 try{
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.clock.install();
  await page.goto(url);await page.evaluate(()=>chatReady);
  await page.evaluate(async()=>{
   for(let i=0;i<16;i++)await api('/api/conversations','POST',{});
   await list();
   await openConversation(state.rows[0].id);
   $('message').value='작성 중인 초안';
   $('history').scrollTop=180;
   window.beforeRefresh={cid:state.cid,top:$('thread').scrollTop,button:$('history').children[4],offset:$('history').children[4].offsetTop-$('history').scrollTop};
   const other=await api('/api/conversations','POST',{});
   await api('/api/conversations/'+other.id,'PATCH',{title:'다른 탭에서 만든 세션'});
   window.otherId=other.id;
   const original=transport.request.bind(transport);
   window.historyRequests=0;
   transport.request=(path,...args)=>{if(path.startsWith('/api/conversations?'))window.historyRequests++;return original(path,...args);};
  });
  await page.clock.runFor(30000);
  await expect(page.locator('#history button').first()).toHaveText('다른 탭에서 만든 세션');
  expect(await page.evaluate(()=>({cid:state.cid===beforeRefresh.cid,thread:$('thread').scrollTop===beforeRefresh.top,draft:$('message').value,anchor:Math.abs(beforeRefresh.button.offsetTop-$('history').scrollTop-beforeRefresh.offset)<2,calls:historyRequests}))).toEqual({cid:true,thread:true,draft:'작성 중인 초안',anchor:true,calls:1});
  // Hidden tabs do no work; returning refreshes once and coalesces duplicate triggers.
  await page.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,value:true}));
  await page.clock.runFor(60000);
  expect(await page.evaluate(()=>historyRequests)).toBe(1);
  await page.evaluate(async()=>{
   Object.defineProperty(document,'hidden',{configurable:true,value:false});
   await Promise.all([refreshHistory(),refreshHistory()]);
  });
  expect(await page.evaluate(()=>historyRequests)).toBe(2);
  // Keep the current search, and pick up a rename without reloading the page.
  const searchQuery=await page.evaluate(()=>'자동 갱신 검색 '+requestId());
  await page.locator('#history-query').fill(searchQuery);
  await page.clock.runFor(200);
  await expect(page.locator('#history button')).toHaveCount(0);
  await page.evaluate(async query=>{await api('/api/conversations/'+otherId,'PATCH',{title:query+' 결과'});},searchQuery);
  await page.clock.runFor(30000);
  await expect(page.locator('#history button')).toHaveCount(1);
  await expect(page.locator('#history button')).toHaveText(searchQuery+' 결과');
  // Fail quietly and back off instead of retrying every tick.
  await page.evaluate(()=>{
   const original=transport.request.bind(transport);
   transport.request=(path,...args)=>{if(path.startsWith('/api/conversations?')){window.historyRequests++;return Promise.reject(Error('offline fixture'));}return original(path,...args);};
   status('기존 대화 상태');window.callsBeforeFailure=historyRequests;
  });
  await page.clock.runFor(30000);
  await expect.poll(()=>page.evaluate(()=>historyRefreshFailures)).toBe(1);
  await page.clock.runFor(30000);
  expect(await page.evaluate(()=>historyRequests-callsBeforeFailure)).toBe(1);
  await page.clock.runFor(30000);
  await expect.poll(()=>page.evaluate(()=>historyRefreshFailures)).toBe(2);
  await expect(page.locator('#status')).toHaveText('기존 대화 상태');
  // Text navigation remains distinct and fits both mobile and desktop overlays.
  for(const width of [360,768,1440]){
   await page.setViewportSize({width,height:900});
   await expect(page.locator('#scroll-previous')).toHaveText('이전 요청');
   await expect(page.locator('#scroll-next')).toHaveText('다음 요청');
   const layout=await page.evaluate(()=>{
    const nav=document.querySelector('.thread-navigation').getBoundingClientRect(),region=$('thread').getBoundingClientRect();
    return {fits:nav.left>=region.left&&nav.right<=region.right&&nav.top>=region.top,round:getComputedStyle($('scroll-top')).borderRadius,text:getComputedStyle($('scroll-previous')).borderRadius};
   });
   expect(layout.fits).toBe(true);expect(layout.round).not.toBe(layout.text);
  }
  await page.reload();await page.evaluate(()=>chatReady);
  for(let i=0;i<3;i++){
   await page.locator('#message').fill(('요청 이동 검증 '+i+'\n').repeat(24));
   await page.locator('#send').click();
   await expect(page.locator('.answer-body strong')).toHaveCount(i+1);
   await expect(page.locator('#send')).toBeEnabled();
  }
  await page.locator('#scroll-top').click();
  await page.locator('#scroll-next').click();
  await expect.poll(()=>page.locator('#thread').evaluate(el=>el.scrollTop)).toBeGreaterThan(100);
  await page.locator('#scroll-previous').click();
  await expect.poll(()=>page.locator('#thread').evaluate(el=>el.scrollTop)).toBeLessThan(2);
  await page.locator('#scroll-bottom').click();
  await expect.poll(()=>page.locator('#thread').evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2);
  expect(errors).toEqual([]);
  console.log('PASS history auto-refresh: encrypted API, 30s polling, hidden tab, coalescing, search, backoff, preserved draft/selection/scroll; text navigation at 360/768/1440px');
 }finally{await context.close();}
}
module.exports={verifyConversationHistoryRefresh};
if(require.main===module){
 const {chromium}=require('playwright');
 (async()=>{const browser=await chromium.launch({headless:true});try{await verifyConversationHistoryRefresh(browser,process.argv[2]);}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
}
