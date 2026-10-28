// Serve the actual app to an isolated browser via route interception. No server/job starts.
const {chromium,expect}=require('@playwright/test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--use-mock-keychain']});
 try{
 for(const width of [360,768,1440]){
  const context=await browser.newContext({viewport:{width,height:900}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let conversations=[],messages={},sent=[];
  await page.route('http://127.0.0.1:3101/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname,method=req.method();
   const json=data=>route.fulfill({json:data});
   if(p==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'conversation-app/templates/index.html'),'utf8').replace('{{ csrf }}','test-csrf')});
   if(p.startsWith('/static/')){
    const folder=p.startsWith('/static/vendor/')||p.startsWith('/static/fonts/')?'codex-web-app':'conversation-app';
    const file=path.join(root,folder,p);
    if(!fs.existsSync(file))return route.fulfill({status:404});
    return route.fulfill({path:file,contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':p.endsWith('.woff2')?'font/woff2':undefined});
   }
   if(p==='/api/accounts')return json({accounts:[{id:'personal',label:'Personal Codex',authenticated:true}]});
   if(p==='/api/models')return json({models:[{model:'test-model',displayName:'Test Model',defaultReasoningEffort:'low',supportedReasoningEfforts:[{reasoningEffort:'low'},{reasoningEffort:'high'}]}]});
   if(p==='/api/settings')return json({});
   if(p==='/api/usage/summary')return json({total_tokens:123,attempts:1,status:'잠정 관측치'});
   if(p==='/api/conversations'){
    if(method==='POST'){const c={id:'c'+(conversations.length+1),title:'새 대화'};conversations.push(c);messages[c.id]=[];return json(c);}
    return json(conversations);
   }
   const match=p.match(/^\/api\/conversations\/([^/]+)\/messages$/);
   if(match){const cid=match[1];if(method==='GET')return json({messages:messages[cid]});
    const value=req.postDataJSON();sent.push(value);assert.equal(req.headers()['x-chat-csrf'],'test-csrf');
    const attempt={id:'a'+sent.length,status:'completed',text:'**Hello**\n\n[Source](https://example.com)\n<script>window.xss=true</script>\n[Bad](javascript:alert(1))',settings:value.settings,provider:{model:'test-model'},citations:[{url:'https://example.com',title:'Example',searched_at:new Date().toISOString()}],search_count:0};
    messages[cid].push({id:'m'+sent.length,content:value.content,attempts:[attempt]});conversations.find(c=>c.id===cid).title='영어 번역';return json({attempt});
   }
   return route.fulfill({status:404,json:{error:'test route missing '+p}});
  });
  await page.goto('http://127.0.0.1:3101/');
  await expect(page.locator('#model')).toHaveValue('test-model');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${width}`);
  await page.locator('[data-mode=translate]').click();await expect(page.locator('#search')).toHaveValue('off');await expect(page.locator('#translation-options')).toBeVisible();
  await page.locator('#message').fill('내일 회의할까요?');
  await page.locator('#message').dispatchEvent('keydown',{key:'Enter',keyCode:229,isComposing:true});assert.equal(sent.length,0);
  await page.locator('#send').click();await expect(page.locator('.answer-body strong')).toHaveText('Hello');
  assert.equal(sent.length,1);assert.equal(sent[0].settings.search,'off');assert.ok(sent[0].content.includes('내일 회의할까요?'));
  assert.equal(await page.evaluate(()=>window.xss),undefined);await expect(page.locator('.answer-body a[href^="javascript:"]')).toHaveCount(0);
  await page.locator('#preferences').click();
  for(const font of ['ibm-plex','suit','nanum-square','wanted-sans','line-seed-kr','goorm-sans','paperlogy','nexon-lv2-gothic']){
   await page.locator('#font').selectOption(font);
   await expect(page.locator('html')).toHaveAttribute('data-ui-font',font);
   const family=await page.evaluate(()=>getComputedStyle(document.body).fontFamily.split(',')[0]);
   assert.ok(await page.evaluate(async family=>{const faces=await document.fonts.load('16px '+family,'안녕');return faces.length>0;},family),`font failed ${font}: ${family}`);
  }
  await page.locator('#settings-dialog button').click();
  await page.locator('#message').fill('보존할 초안');await page.reload();await expect(page.locator('#message')).toHaveValue('보존할 초안');await expect(page.locator('html')).toHaveAttribute('data-ui-font','nexon-lv2-gothic');
  if(width<1024){await page.locator('#show-history').click();await expect(page.locator('#sidebar')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('#sidebar')).not.toBeVisible();await expect(page.locator('#show-history')).toBeFocused();}
  await page.locator('#usage').click();await expect(page.locator('#usage-summary')).toContainText('123');await page.locator('#usage-dialog button').click();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`final overflow ${width}`);
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(root,`tmp/chat-${width}.png`),fullPage:true});
  await context.close();console.log(`PASS ${width}px · fonts 8 · IME · send · Markdown/XSS · draft · settings`);
 }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
