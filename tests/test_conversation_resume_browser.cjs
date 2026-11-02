const {expect}=require('@playwright/test');
const assert=require('node:assert/strict');
async function verifyConversationResume(browser,url){
 const context=await browser.newContext({viewport:{width:768,height:620}});
 try {
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.evaluate(()=>chatReady);
  await page.locator('#message').fill('읽기 위치를 보관하는 긴 질문입니다.\n'.repeat(30));
  await page.locator('#send').click();
  await expect(page.locator('.answer-body strong').last()).toHaveText('Hello');
  await page.locator('#message').fill('복귀 후에도 유지할 초안');
  await page.locator('#preferences').click();
  await page.locator('#line-height').fill('210');
  await page.locator('#line-height').dispatchEvent('input');
  await page.locator('#settings-dialog button').click();
  await page.evaluate(()=>{
   state.following=false;
   $('thread').scrollTo({top:90,behavior:'instant'});
  });
  await expect.poll(()=>page.locator('#thread').evaluate(e=>Math.abs(e.scrollTop-90))).toBeLessThan(2);
  const previousPosition=await page.evaluate(()=>({cid:state.cid,reading:readingPosition(state.cid),following:state.following}));
  // Existing installations may still have both legacy restore keys.
  await page.evaluate(()=>{
   flushDrafts();localStorage.setItem('chat-current',state.cid);
   localStorage.setItem('chat-drafts',JSON.stringify({...state.drafts,new:'이전에 제출한 프롬프트'}));
  });
  await page.reload();await page.evaluate(()=>chatReady);
  assert.equal(await page.evaluate(()=>state.cid),null);
  await expect(page.locator('#message')).toHaveValue('');
  await page.evaluate(id=>openConversation(id),previousPosition.cid);
  await expect(page.locator('#message')).toHaveValue('복귀 후에도 유지할 초안');
  try {await expect.poll(()=>page.locator('#thread').evaluate(e=>Math.abs(e.scrollTop-90))).toBeLessThan(2);} catch(error) {console.log('resume diagnostics',previousPosition,await page.evaluate(()=>({cid:state.cid,reading:readingPosition(state.cid),following:state.following,top:$('thread').scrollTop,height:$('thread').scrollHeight})));throw error;}
  await expect(page.locator('#line-height')).toHaveValue('210');
  const rhythm=await page.locator('.answer-body').first().evaluate(e=>{const s=getComputedStyle(e);return parseFloat(s.lineHeight)/parseFloat(s.fontSize);});
  assert.ok(Math.abs(rhythm-2.1)<.01);
  await page.setViewportSize({width:360,height:780});
  await expect(page.locator('#message')).toHaveValue('복귀 후에도 유지할 초안');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.setViewportSize({width:768,height:620});
  await expect(page.locator('#message')).toHaveValue('복귀 후에도 유지할 초안');
  // A fresh browser context carries disk storage, but no open page state.
  const reopened=await browser.newContext({storageState:await context.storageState()});
  try {
   const fresh=await reopened.newPage();await fresh.goto(url);await fresh.evaluate(()=>chatReady);
   assert.equal(await fresh.evaluate(()=>state.cid),null);
   await expect(fresh.locator('#message')).toHaveValue('');
   await expect(fresh.locator('#messages')).toBeEmpty();
   await expect(fresh.locator('#history [aria-current="page"]')).toHaveCount(0);
  } finally {await reopened.close();}
  await page.locator('#show-history').click();await page.locator('#new-chat').click();
  await expect(page.locator('#message')).toHaveValue('');
  await page.locator('#message').fill('제출 전 초안');
  await page.locator('#show-history').click();await page.locator('#new-chat').click();
  await expect(page.locator('#message')).toHaveValue('');
  await page.locator('#message').fill('새 세션으로 전송할 프롬프트');
  await page.locator('#send').click();
  await expect(page.locator('.answer-body strong')).toHaveText('Hello');
  await page.locator('#show-history').click();await page.locator('#new-chat').click();
  await expect(page.locator('#message')).toHaveValue('');
  // Selecting a saved conversation restores only that conversation's draft.
  await page.locator('#show-history').click();
  await page.locator(`#history button[data-cid="${previousPosition.cid}"]`).click();
  await expect(page.locator('#message')).toHaveValue('복귀 후에도 유지할 초안');
  assert.deepEqual(errors,[]);
  console.log('PASS explicit resume · real encrypted conversation · draft/scroll/line-height persistence · fold transition');
 } finally {await context.close();}
}
module.exports={verifyConversationResume};
