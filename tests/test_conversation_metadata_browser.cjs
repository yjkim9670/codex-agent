const {expect}=require('@playwright/test');

async function verifyConversationMetadata(browser,url){
 for(const width of [360,768,1440]){
  const context=await browser.newContext({viewport:{width,height:900}});
  try{
   const page=await context.newPage(),errors=[];
   page.setDefaultTimeout(10000);
   page.on('pageerror',error=>errors.push(error.message));
   await page.goto(url);await page.evaluate(()=>chatReady);
   await page.locator('#message').fill('답변 메타데이터 검증');await page.locator('#send').click();
   const answer=page.locator('.answer').last();
   await expect(answer.locator('.answer-execution')).toContainText('test-model · reasoning low · 시작');
   await expect(answer.locator('.answer-usage')).toHaveText('123 tokens · 관측 Δ 5h +2%p · Weekly +0.5%p');
   await expect(answer.locator('.answer-details')).not.toHaveAttribute('open');
   expect(await answer.evaluate(el=>{
    const header=el.querySelector('.answer-execution'),body=el.querySelector('.answer-body'),footer=el.querySelector('.answer-usage');
    return {top:header.getBoundingClientRect().bottom<=body.getBoundingClientRect().top,
      bottom:footer.getBoundingClientRect().top>=body.getBoundingClientRect().bottom,
      small:parseFloat(getComputedStyle(footer).fontSize)<=12,
      overflow:document.documentElement.scrollWidth>innerWidth+1};
   })).toEqual({top:true,bottom:true,small:true,overflow:false});
   const before=await answer.locator('.answer-execution').textContent();
   await page.reload();await page.evaluate(()=>chatReady);
   await page.evaluate(()=>openConversation(state.rows[0].id));
   await expect(page.locator('.answer-execution').last()).toHaveText(before);
   await expect(page.locator('.answer-usage').last()).toContainText('5h +2%p · Weekly +0.5%p');
   expect(await page.evaluate(()=>{
    const row=(used,resets)=>({five_hour:{used_percent:used,resets_at:resets}});
    return [attemptQuotaDelta({},'five_hour'),
      attemptQuotaDelta({before:row(20,'a'),after:row(0,'b')},'five_hour'),
      attemptQuotaDelta({before:row(20,'a'),after:row(20,'a')},'five_hour'),
      attemptQuotaDelta({before:row(null,'a'),after:row(20,'a')},'five_hour'),
      attemptQuotaDelta({before:row(20,'a'),after:row(21,'a'),delayed:{weekly:{used_percent:1}}},'five_hour'),
      attemptUsageText({usage:{total:{}}})];
   })).toEqual(['관측 대기','리셋/감소','+0%p','관측 대기','+1%p','토큰 집계 대기 · 관측 Δ 5h 관측 대기 · Weekly 관측 대기']);
   expect(errors).toEqual([]);
  }finally{await context.close();}
 }
 console.log('PASS answer metadata: live/delayed observations, persisted reload, compact layout at 360/768/1440px, resets and missing usage');
}
module.exports={verifyConversationMetadata};
