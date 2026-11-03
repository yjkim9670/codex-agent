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
  const bottomGap=()=>page.locator('#thread').evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop);
  await expect.poll(bottomGap).toBeLessThan(2);
  await expect(page.locator('#scroll-top')).toBeVisible();
  await page.locator('#scroll-top').click();
  await expect.poll(()=>page.locator('#thread').evaluate(e=>e.scrollTop)).toBeLessThan(2);
  // Incoming content cannot pull the reader away after choosing the top.
  await page.evaluate(()=>{$('messages').lastElementChild.querySelector('.user').append('추가 내용\n'.repeat(40));});
  await expect.poll(()=>page.locator('#thread').evaluate(e=>e.scrollTop)).toBeLessThan(2);
  const rail=page.locator('.thread-region>.overlay-scrollbar');
  await expect(rail).toBeVisible();
  const track=await rail.boundingBox(),thumb=await rail.locator('.overlay-scrollbar-thumb').boundingBox();
  await page.mouse.move(thumb.x+thumb.width/2,thumb.y+thumb.height/2);
  await page.mouse.down();await page.mouse.move(thumb.x+thumb.width/2,track.y+track.height, {steps:8});await page.mouse.up();
  await expect.poll(bottomGap).toBeLessThan(2);
  await page.locator('#scroll-top').click();await page.locator('#scroll-bottom').click();
  await expect.poll(bottomGap).toBeLessThan(2);
  const overlay=await page.evaluate(()=>{
   const thread=$('thread'),region=thread.parentElement.getBoundingClientRect(),buttons=document.querySelector('.thread-navigation').getBoundingClientRect();
   return {style:getComputedStyle(thread).scrollbarWidth,gutter:thread.offsetWidth-thread.clientWidth,inside:buttons.bottom<=region.bottom&&buttons.right<=region.right};
  });
  assert.deepEqual(overlay,{style:'none',gutter:0,inside:true});
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
  console.log('PASS explicit resume · real encrypted conversation · draft/line-height persistence · latest-first selection and overlay scroll controls · fold transition');
 } finally {await context.close();}
}
module.exports={verifyConversationResume};
