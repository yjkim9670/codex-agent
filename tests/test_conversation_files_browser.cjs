async function verifyConversationFiles(page,expect){
 await page.context().grantPermissions(['clipboard-read','clipboard-write']);
 await page.evaluate(()=>chatReady);
 await page.locator('#message').fill('file preview fixture');await page.locator('#send').click();
 const link=page.locator('#messages a[data-artifact-path]').first();await expect(link).toBeVisible();
 await link.click();const panel=page.locator('#file-preview');await expect(panel).toBeVisible();
 await expect(page.locator('#file-copy')).toBeEnabled();
 await expect(page.locator('#file-preview-title')).toHaveText('sample.py');
 await expect(page.locator('#file-page')).toHaveText('1 / 3');
 expect(await page.locator('#file-preview-code code').evaluate(el=>el.textContent.length)).toBe(24000);
 const bounds=await panel.boundingBox(),viewport=page.viewportSize();expect(bounds.x+bounds.width).toBeCloseTo(viewport.width,0);expect(bounds.height).toBeLessThanOrEqual(viewport.height);
 await page.locator('#file-copy').click();await expect(page.locator('#file-preview-status')).toContainText('복사했습니다');
 const full=await page.evaluate(()=>navigator.clipboard.readText());expect(full).toContain('미리보기');expect(full.length).toBeGreaterThan(70000);
 await page.locator('#file-next').click();await page.locator('#file-next').click();await expect(page.locator('#file-page')).toHaveText('3 / 3');await expect(page.locator('#file-preview-code')).toContainText('<script>');expect(await page.evaluate(()=>window.fileXss)).toBeUndefined();
 const downloaded=page.waitForEvent('download');await page.locator('#file-download').click();const download=await downloaded;expect(download.suggestedFilename()).toBe('sample.py');
 const stream=await download.createReadStream();const parts=[];for await(const part of stream)parts.push(part);expect(Buffer.concat(parts).toString('utf8')).toBe(full);
 await page.keyboard.press('Escape');await expect(panel).not.toBeVisible();await expect(link).toBeFocused();
 // Sanitized file/sandbox links stay interactive; executable URLs never do.
 expect(await page.evaluate(()=>{const box=safeMarkdown('[a](file:///tmp/workbench-chat-test/a.py) [b](sandbox:/tmp/workbench-chat-test/b.py) [bad](javascript:alert%281%29)');return [box.querySelectorAll('[data-artifact-path]').length,box.querySelectorAll('a[href^="javascript:"]').length];})).toEqual([2,0]);
 for(const width of [768,390]){
  await page.setViewportSize({width,height:700});await link.click();await expect(page.locator('#file-copy')).toBeEnabled();const box=await panel.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width+1);await page.keyboard.press('Escape');
 }
 await page.setViewportSize({width:1280,height:900});
 // HTML larger than both the old 1 MiB cap and 4 MiB text preview renders whole.
 const htmlLink=page.locator('#messages a[data-artifact-path]').filter({hasText:'sample.html'});
 await htmlLink.click();await expect(page.locator('#file-open')).toBeEnabled();
 const frame=page.frameLocator('#file-preview-html');
 await expect(frame.locator('h1')).toHaveText('렌더링 확인');
 await expect(page.locator('#file-preview-code')).toBeHidden();
 await expect(page.locator('.file-preview-paging')).toBeHidden();
 await frame.locator('#counter').click();await expect(frame.locator('#counter')).toHaveText('1');
 expect(await page.evaluate(()=>document.body.dataset.escaped)).toBeUndefined();
 expect(await frame.locator('body').evaluate(()=>localStorage.getItem('fixture'))).toBe('ready');
 expect(await page.locator('#file-preview-html').getAttribute('sandbox')).toBe('allow-scripts allow-forms');
 const popupEvent=page.waitForEvent('popup');await page.locator('#file-open').click();const popup=await popupEvent;
 await expect(popup.locator('h1')).toHaveText('렌더링 확인');
 expect(await popup.evaluate(()=>window.opener)).toBeNull();
 expect(await popup.evaluate(()=>localStorage.getItem('fixture'))).toBe('ready');
 expect(await popup.evaluate(()=>{try{void parent.document.cookie;return false;}catch{return true;}})).toBe(true);
 await popup.close();
 const htmlDownloadEvent=page.waitForEvent('download');await page.locator('#file-download').click();const htmlDownload=await htmlDownloadEvent;
 expect(htmlDownload.suggestedFilename()).toBe('sample.html');
 const htmlStream=await htmlDownload.createReadStream(),htmlParts=[];for await(const part of htmlStream)htmlParts.push(part);
 const html=Buffer.concat(htmlParts).toString('utf8');expect(html.length).toBeGreaterThan(5*1024*1024);expect(html).not.toContain('data-codex-workbench-preview-compat');
 await page.locator('#file-copy').click();await expect(page.locator('#file-preview-status')).toContainText('복사했습니다');
 expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(html);
 for(const width of [390,768,1280]){
  await page.setViewportSize({width,height:800});
  const tools=await page.locator('.file-preview-actions').boundingBox();
  expect(tools.x).toBeGreaterThanOrEqual(0);expect(tools.x+tools.width).toBeLessThanOrEqual(width+1);
  expect(tools.height).toBeLessThanOrEqual(40);
  await expect(frame.locator('h1')).toBeVisible();
 }
 await page.locator('#file-preview [data-close-dialog]').click();
 await expect(page.locator('#file-preview-html')).not.toHaveAttribute('src',/.+/);
 await page.evaluate(()=>openFilePreview('/etc/passwd',document.activeElement));await expect(page.locator('#file-preview-status')).toContainText('이 대화에서 생성한 파일');await expect(page.locator('#file-copy')).toBeDisabled();await page.keyboard.press('Escape');
}
module.exports={verifyConversationFiles};
