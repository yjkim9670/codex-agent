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
