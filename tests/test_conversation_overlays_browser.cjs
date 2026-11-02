const {expect}=require('@playwright/test');

async function verifyConversationOverlays(browser,url){
 for(const width of [360,768,1440]){
  const context=await browser.newContext({viewport:{width,height:900},isMobile:width===360,hasTouch:width===360});
  try{
   const page=await context.newPage(),errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.goto(url);await page.evaluate(()=>chatReady);
   await page.locator('#message').fill('유지할 초안');
   if(width<1024){
    await page.locator('#show-history').click();
    await expect(page.locator('#sidebar-backdrop')).toBeVisible();
    expect(await page.locator('main').evaluate(el=>el.inert)).toBe(true);
    const style=await page.locator('#sidebar-backdrop').evaluate(el=>{
     const s=getComputedStyle(el);return {blur:s.backdropFilter,color:s.backgroundColor};
    });
    expect(style.blur).toBe('blur(4px)');expect(style.color).toBe('rgba(22, 22, 22, 0.4)');
    await page.locator('#account-settings summary').click();
    await expect(page.locator('#sidebar')).toHaveClass('open');
    await page.mouse.click(width-8,100);
    await expect(page.locator('#sidebar')).not.toBeVisible();
    await expect(page.locator('#sidebar-backdrop')).not.toBeVisible();
    await expect(page.locator('#show-history')).toBeFocused();
    await expect.poll(()=>page.locator('main').evaluate(el=>el.inert)).toBe(false);
    await expect(page.locator('#message')).toHaveValue('유지할 초안');
    await page.locator('#show-history').click();await page.keyboard.press('Escape');
    await expect(page.locator('#sidebar-backdrop')).not.toBeVisible();
    await page.locator('#show-history').click();await page.setViewportSize({width:1440,height:900});
    await expect(page.locator('#sidebar-backdrop')).not.toBeVisible();
    await expect.poll(()=>page.locator('main').evaluate(el=>el.inert)).toBe(false);
    await page.setViewportSize({width,height:900});
   }
   for(const id of width===360?['actions-dialog','request-dialog','settings-dialog','usage-dialog']:['settings-dialog','usage-dialog']){
    const trigger=id==='actions-dialog'?'#more-actions':id==='request-dialog'?'#request-summary':id==='settings-dialog'?'#preferences':'#usage';
    if(width===360&&['settings-dialog','usage-dialog'].includes(id))await page.locator('#more-actions').click();
    await page.locator(trigger).click();
    const dialog=page.locator('#'+id);await expect(dialog).toBeVisible();
    expect(await dialog.evaluate(el=>getComputedStyle(el,'::backdrop').backdropFilter)).toBe('blur(4px)');
    // Padding is inside the window. A drag that starts inside also stays open.
    const rect=await dialog.boundingBox();
    await page.mouse.click(rect.x+4,rect.y+4);await expect(dialog).toBeVisible();
    await page.mouse.move(rect.x+4,rect.y+4);await page.mouse.down();await page.mouse.move(2,2);await page.mouse.up();
    await expect(dialog).toBeVisible();
    await page.mouse.click(2,2);await expect(dialog).not.toBeVisible();
    await expect(page.locator('#message')).toHaveValue('유지할 초안');
   }
   expect(errors).toEqual([]);
   console.log(`PASS overlays ${width}px: outside dismissal, inside/drag protection, blur, inert background, Escape, resize, draft preservation`);
  }finally{await context.close();}
 }
}
module.exports={verifyConversationOverlays};
