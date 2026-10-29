// Real layout and interactions for narrow cover displays and fold transitions.
const {expect}=require('@playwright/test');
const assert=require('node:assert/strict');
async function verifyMobileConversation(browser,url,{screenshot}={}){
 const context=await browser.newContext({viewport:{width:360,height:780},isMobile:true,hasTouch:true});
 try{
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);await page.evaluate(()=>chatReady);await page.evaluate(()=>document.fonts.ready);
  const geometry=()=>page.evaluate(()=>{
   const height=id=>document.querySelector(id).getBoundingClientRect().height;
   return {header:height('header'),thread:height('#thread'),composer:height('#composer'),overflow:document.documentElement.scrollWidth>innerWidth,composerBottom:document.querySelector('#composer').getBoundingClientRect().bottom,viewport:visualViewport.height};
  });
  await expect(page.locator('#request-options')).not.toBeVisible();
  let normal=await geometry();assert.ok(normal.header<=56);assert.ok(normal.composer<=110);assert.ok(normal.thread>=620);assert.equal(normal.overflow,false);
  await page.locator('[data-mode=translate]').click();
  await expect(page.locator('#request-summary')).toContainText('영어 번역');
  assert.equal((await geometry()).composer,normal.composer,'translation does not reserve settings space');
  await page.locator('#request-summary').click();await expect(page.locator('#request-dialog')).toBeVisible();
  await page.locator('#tone').selectOption('업무용');await page.locator('#language').fill('일본어');await page.locator('#language').dispatchEvent('change');
  await page.locator('#request-dialog [data-close-dialog]').click();await expect(page.locator('#request-summary')).toContainText('일본어 · 업무용');await expect(page.locator('#request-summary')).toBeFocused();
  await page.locator('#message').fill('긴 초안\n'.repeat(30));assert.ok((await page.locator('#message').boundingBox()).height<=120);
  await page.locator('#message').fill('모바일 대화를 검증해 주세요.');await page.locator('#send').click();
  await expect(page.locator('.answer-body strong').last()).toHaveText('Hello');
  await expect(page.locator('.answer-details').last()).not.toHaveAttribute('open','');
  await page.locator('.answer-details summary').last().click();await expect(page.locator('.answer-details[open]').last()).toContainText('123 tokens');
  await page.locator('.answer-details summary').last().click();
  await expect(page.locator('#status')).toBeEmpty({timeout:5000});
  if(screenshot)await page.screenshot({path:screenshot});
  await page.setViewportSize({width:360,height:460});
  await expect.poll(async()=>{const g=await geometry();return Math.abs(g.composerBottom-g.viewport);}).toBeLessThan(2);
  let keyboard=await geometry();assert.ok(keyboard.thread>=300);assert.ok(Math.abs(keyboard.composerBottom-keyboard.viewport)<2);assert.equal(keyboard.overflow,false);
  await page.locator('#request-summary').click();
  const sheet=await page.locator('#request-dialog').boundingBox();assert.ok(sheet.y>=0&&sheet.y+sheet.height<=461);
  await page.locator('#format').selectOption('번역+설명');await page.keyboard.press('Escape');await expect(page.locator('#request-dialog')).not.toBeVisible();
  await page.locator('#more-actions').click();await page.locator('#preferences').click();await expect(page.locator('#settings-dialog')).toBeVisible();await expect(page.locator('#actions-dialog')).not.toBeVisible();await page.locator('#settings-dialog button').click();
  await page.locator('#message').fill('접고 펼쳐도 유지되는 초안');
  await page.locator('#request-summary').click();await page.setViewportSize({width:768,height:900});
  await expect(page.locator('#request-dialog')).not.toBeVisible();await expect(page.locator('#mode')).toBeVisible();await expect(page.locator('#preferences')).toBeVisible();await expect(page.locator('#message')).toHaveValue('접고 펼쳐도 유지되는 초안');
  await page.setViewportSize({width:390,height:844});await expect(page.locator('#mode')).not.toBeVisible();await expect(page.locator('#request-summary')).toBeVisible();assert.equal((await geometry()).overflow,false);
  assert.deepEqual(errors,[]);console.log('PASS mobile cover layout',JSON.stringify({normal,keyboard}));
 }finally{await context.close();}
}
module.exports={verifyMobileConversation};
