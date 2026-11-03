const {expect}=require('@playwright/test');
async function verifyConversationSidebar(browser,url){
 const context=await browser.newContext({viewport:{width:360,height:780},isMobile:true,hasTouch:true});
 try{
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  await page.goto(url);await page.evaluate(()=>chatReady);
  // Real encrypted API and rendered history, including enough rows to scroll.
  await page.evaluate(async()=>{
   for(let i=0;i<14;i++){const row=await api('/api/conversations','POST');await api('/api/conversations/'+row.id,'PATCH',{title:'사이드바 검증 '+i});}
   await list();
  });
  await page.locator('#show-history').click();
  await expect(page.locator('#account-settings')).not.toHaveAttribute('open','');
  await expect(page.locator('#usage-settings')).not.toHaveAttribute('open','');
  await expect(page.locator('#account')).not.toBeVisible();
  await expect(page.locator('#account-limits')).not.toBeVisible();
  await expect(page.locator('#history-query')).not.toBeVisible();
  await expect(page.locator('label[for=history-query]')).not.toBeVisible();
  expect((await page.locator('#history').boundingBox()).height).toBeGreaterThan(350);
  await expect(page.locator('#history button').first()).toBeInViewport();
  await page.locator('#history button').last().scrollIntoViewIfNeeded();
  await expect(page.locator('#history button').last()).toBeInViewport();
  await page.locator('#account-settings summary').click();await expect(page.locator('#account')).toBeVisible();
  await page.locator('#usage-settings summary').click();
  await page.locator('#account-limits').scrollIntoViewIfNeeded();await expect(page.locator('#limit-windows')).toContainText('76% 남음');
  expect((await page.locator('#history').boundingBox()).height).toBeGreaterThanOrEqual(96);
  await page.setViewportSize({width:360,height:460});
  expect((await page.locator('#history').boundingBox()).height).toBeGreaterThanOrEqual(96);
  const sidebar=await page.locator('#sidebar').boundingBox();expect(sidebar.y+sidebar.height).toBeLessThanOrEqual(461);
  await page.keyboard.press('Escape');await expect(page.locator('#show-history')).toBeFocused();
  await page.setViewportSize({width:1440,height:900});
  await expect(page.locator('#account')).toBeVisible();await expect(page.locator('#account-limits')).toBeVisible();
  await expect(page.locator('#account-settings summary')).not.toBeVisible();await expect(page.locator('#history-query')).toBeVisible();
  const sidebarWidth=(await page.locator('#sidebar').boundingBox()).width;
  expect(sidebarWidth).toBeGreaterThanOrEqual(288);
  expect(sidebarWidth).toBeLessThanOrEqual(420);
  expect((await page.locator('.account').boundingBox()).height).toBeLessThan(255);
  await page.locator('#scale').evaluate(input=>{input.value='80';input.dispatchEvent(new Event('input'));});
  expect(Math.abs((await page.locator('#sidebar').boundingBox()).width-sidebarWidth)).toBeLessThan(1);
  await page.locator('#scale').evaluate(input=>{input.value='90';input.dispatchEvent(new Event('input'));});
  const historyScroll=await page.locator('#history').evaluate(el=>({gutter:el.offsetWidth-el.clientWidth,style:getComputedStyle(el).scrollbarWidth}));
  expect(historyScroll).toEqual({gutter:0,style:'none'});
  await page.locator('#history button').first().evaluate(button=>{button.textContent='아주 긴 대화 제목이 충분히 보이도록 두 줄까지 표시하는 사이드바 검증 '.repeat(4);});
  const titleLayout=await page.locator('#history button').first().evaluate(button=>({
   lines:getComputedStyle(button).webkitLineClamp,whiteSpace:getComputedStyle(button).whiteSpace,
   fits:button.getBoundingClientRect().right<=document.querySelector('#sidebar').getBoundingClientRect().right
  }));
  expect(titleLayout).toEqual({lines:'2',whiteSpace:'normal',fits:true});
  // Polling must not resize the footer or the history above it on desktop.
  const stableLimits=await page.evaluate(()=>{
   const snapshot=()=>['#history','.account','#account-limits','#limit-windows','#limits-status'].map(selector=>{
    const {x,y,width,height}=document.querySelector(selector).getBoundingClientRect();return {x,y,width,height};
   });
   const populated={five_hour:{remaining_percent:100,used_percent:0,resets_at:2000000000},weekly:{remaining_percent:0.1,used_percent:99.9,resets_at:2000500000},observed_at:new Date().toISOString()};
   paintLimits(populated);const before=snapshot();
   const states=[[null,'사용 한도 확인 중'],[null,'조회 실패 · '+ '오류 상세 '.repeat(30)],[{five_hour:populated.five_hour},'미제공'],[null,'계정을 선택해 주세요.'],[populated]];
   return states.map(args=>{paintLimits(...args);return {before,after:snapshot()};});
  });
  for(const {before,after} of stableLimits)expect(after).toEqual(before);
  // Desktop collapse gives the conversation space back without opening a backdrop.
  const mainWidth=(await page.locator('main').boundingBox()).width;
  await page.locator('#close-history').click();await expect(page.locator('#sidebar')).not.toBeVisible();
  await expect(page.locator('#show-history')).toBeFocused();
  await expect(page.locator('#show-history')).toHaveAttribute('aria-expanded','false');
  await expect(page.locator('#sidebar-backdrop')).not.toBeVisible();
  expect((await page.locator('main').boundingBox()).width).toBeGreaterThan(mainWidth+280);
  await page.locator('#show-history').click();await expect(page.locator('#sidebar')).toBeVisible();
  await expect(page.locator('#close-history')).toBeFocused();
  await expect(page.locator('#show-history')).toHaveAttribute('aria-expanded','true');
  await page.locator('#history-query').fill('no-matching-conversation');await expect(page.locator('#history button')).toHaveCount(0);
  await page.setViewportSize({width:768,height:900});await page.locator('#show-history').click();
  await expect(page.locator('#history-query')).not.toBeVisible();await expect(page.locator('#account-settings')).not.toHaveAttribute('open','');
  await expect(page.locator('#history button').first()).toBeVisible();
  await page.locator('#history button').first().click();await expect(page.locator('#sidebar')).not.toBeVisible();
  await expect(page.locator('#title')).toContainText('사이드바 검증');
  expect(errors).toEqual([]);console.log('PASS sidebar: collapsed controls, scrollable history, short viewport, desktop restore, hidden search reset, conversation selection');
 }finally{await context.close();}
}
module.exports={verifyConversationSidebar};
