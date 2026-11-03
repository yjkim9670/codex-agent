// Deterministic rendered coverage of cover/inner displays, rotation and desktop.
const {expect}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const surfaces=[
 ['mobile-small',360,780],['mobile',390,844],['mobile-large',412,915],
 ['fold-cover-narrow',344,882],['fold-cover',374,904],
 ['fold-inner',768,900],['fold-inner-wide',853,1010],
 ['tablet-split',600,960],['tablet',820,1180],['tablet-large',1024,1366],
 ['desktop',1440,900],['desktop-wide',1920,1080],['reference',1487,1058],
];
async function verifyResponsiveConversation(browser,url){
 const output=path.resolve(__dirname,'../.agent_state/ui-verification');fs.mkdirSync(output,{recursive:true});
 const results=[];
 for(const [name,width,height] of surfaces.filter(row=>!process.env.CODEX_VERIFY_RESPONSIVE_ONLY||process.env.CODEX_VERIFY_RESPONSIVE_ONLY.split(',').includes(row[0]))){
  const touch=!name.startsWith('desktop')&&name!=='reference';
  const context=await browser.newContext({viewport:{width,height},isMobile:touch,hasTouch:touch,colorScheme:'light'});
  try{
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await page.goto(url);await page.evaluate(()=>chatReady);await page.evaluate(()=>document.fonts.ready);
   const checkGeometry=async(label)=>{
    await expect.poll(()=>page.evaluate(()=>Math.abs(document.querySelector('#composer').getBoundingClientRect().bottom-visualViewport.height))).toBeLessThan(2);
    const geometry=await page.evaluate(()=>{
     const rect=selector=>{const {x,y,width,height,right,bottom}=document.querySelector(selector).getBoundingClientRect();return {x,y,width,height,right,bottom};};
     return {width:innerWidth,height:visualViewport.height,overflow:document.documentElement.scrollWidth>innerWidth+1,header:rect('header'),thread:rect('#thread'),composer:rect('#composer'),message:rect('#message'),send:rect('#send')};
    });
    expect(geometry.overflow,label+' horizontal overflow').toBe(false);
    if(geometry.width<600)expect(geometry.header.height,label+' compact header').toBeLessThanOrEqual(56);
    expect(geometry.thread.height,label+' reading space').toBeGreaterThan(70);
    expect(geometry.message.x).toBeGreaterThanOrEqual(0);expect(geometry.send.right).toBeLessThanOrEqual(geometry.width+1);
    expect(geometry.send.x).toBeGreaterThanOrEqual(geometry.message.right-1);
    expect(geometry.send.y).toBeLessThan(geometry.message.bottom);
    expect(geometry.header.bottom).toBeLessThanOrEqual(geometry.thread.y+1);
    return geometry;
   };
   const openSettings=async()=>{if(await page.locator('#more-actions').isVisible())await page.locator('#more-actions').click();await page.locator('#preferences').click();};
   // Real hardware-key events with touch emulation, without sending paid requests.
   const keys=await page.evaluate(()=>{
    const original=send;let submissions=0;send=()=>submissions++;
    const input=$('message');input.value='키보드 검증';
    const event=options=>{const key=new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...options});input.dispatchEvent(key);return key.defaultPrevented;};
    try{return {enter:event({}),shift:event({shiftKey:true}),composing:event({isComposing:true}),legacyIme:event({keyCode:229}),submissions};}finally{send=original;}
   });
   expect(keys,name+' Enter / Shift+Enter / IME').toEqual({enter:true,shift:false,composing:false,legacyIme:false,submissions:1});
   await page.locator('#message').fill('화면 검증');await page.locator('#send').click();await expect(page.locator('.answer-body strong').last()).toHaveText('Hello');
   await page.locator('#message').fill('회전과 폴드 전환 중 보존할 초안');
   for(const [orientation,w,h] of [['portrait',width,height],...touch?[['landscape',height,width]]:[]]){
    await page.setViewportSize({width:w,height:h});
    const label=name+'-'+orientation;
    const geometry=await checkGeometry(label);
    await expect(page.locator('#message')).toHaveValue('회전과 폴드 전환 중 보존할 초안');
    if(w<1024){
     await page.locator('#show-history').click();await expect(page.locator('#sidebar')).toBeVisible();
     const drawer=await page.locator('#sidebar').boundingBox();expect(drawer.y).toBeGreaterThanOrEqual(-1);expect(drawer.y+drawer.height).toBeLessThanOrEqual(h+1);
     await page.keyboard.press('Escape');await expect(page.locator('#show-history')).toBeFocused();
    }else{
     await page.locator('#close-history').click();await expect(page.locator('#sidebar')).not.toBeVisible();await page.locator('#show-history').click();await expect(page.locator('#sidebar')).toBeVisible();
    }
    await openSettings();const dialog=await page.locator('#settings-dialog').boundingBox();expect(dialog.y).toBeGreaterThanOrEqual(-1);expect(dialog.y+dialog.height).toBeLessThanOrEqual(h+1);
    await page.locator('#theme').selectOption('dark');await page.locator('#settings-dialog button').click();await checkGeometry(label+' dark');
    await page.screenshot({path:path.join(output,label+'-dark.png')});
    await openSettings();await page.locator('#theme').selectOption('light');await page.locator('#scale').evaluate(el=>{el.value='110';el.dispatchEvent(new Event('input'));});await page.locator('#settings-dialog button').click();await checkGeometry(label+' 110%');
    await openSettings();await page.locator('#scale').evaluate(el=>{el.value='100';el.dispatchEvent(new Event('input'));});await page.locator('#settings-dialog button').click();
    await page.screenshot({path:path.join(output,label+'.png')});results.push({name:label,...geometry});
   }
   if(touch){
    await page.setViewportSize({width,height:360});await checkGeometry(name+' keyboard-height simulation');
    await page.setViewportSize({width:344,height:882});await checkGeometry(name+' folded');
    await page.setViewportSize({width:853,height:1010});await checkGeometry(name+' unfolded');
    await expect(page.locator('#message')).toHaveValue('회전과 폴드 전환 중 보존할 초안');
   }
   expect(errors).toEqual([]);console.log('PASS responsive '+name+' · rotation, input, dialogs, sidebar, light/dark, 110% scale, draft');
  }finally{await context.close();}
 }
 const report=path.join(output,'responsive-results.json');
 const previous=process.env.CODEX_VERIFY_RESPONSIVE_ONLY&&fs.existsSync(report)?JSON.parse(fs.readFileSync(report,'utf8')).filter(row=>!results.some(next=>next.name===row.name)):[];
 fs.writeFileSync(report,JSON.stringify([...previous,...results],null,2));
}
module.exports={verifyResponsiveConversation};
