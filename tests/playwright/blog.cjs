// Deterministic reader fixtures: no model runs or changes to the user's blog.
const posts = [
    {id:'draft',title:'다음 이야기',status:'집필 중',files:['draft.md']},
    {id:'published',title:'- 일상의-작은-기록 — 하루의‑습관',status:'완성본 있음',files:['final.md','draft.md']},
];
const markdown = '# 일상의 작은 기록 - 하루의 습관\n\n## 하루를 여는 방법\n\n**작은 습관**을 기록합니다.\n\n> 잠시 쉬어가세요.\n\n| 시간 | 행동 |\n| --- | --- |\n| 아침 | 기록 |\n\n### 기록 예시\n\n```js\nconst day = 1;\n```\n\n[참고](https://example.com)\n\n<script>window.blogUnsafe = true;</script>\n\n<a href="javascript:alert(1)">unsafe</a>';
exports.setupBlog = async page => {
    await page.route('**/api/codex/blog', route => route.fulfill({json:{
        configured:true,enabled:true,posts,dashboard:{current_stage:'draft',completed_stage_count:1,total_stage_count:3},
        project:{enabled:true},recent_runs:[],backlog:[],
    }}));
    await page.route('**/api/codex/blog/posts/*/*', route => route.fulfill({json:{
        content:route.request().url().endsWith('/published/final.md') ? markdown : '## 초고\n\n아직 작성하고 있는 이야기입니다.',
    }}));
};
exports.verifyBlog = async (page, expect) => {
    await expect(page.locator('#blog-home')).toBeVisible();
    await expect(page.locator('.featured-card h2')).toHaveText('일상의 작은 기록 하루의 습관');
    await expect(page.locator('#posts button span')).toHaveText('일상의 작은 기록 하루의 습관');
    await page.locator('#search').fill('일상의 작은 기록');
    await expect(page.locator('.featured-card')).toBeVisible();
    await page.locator('#search').fill('');
    await expect(page.locator('#reading-layout')).toBeHidden();
    expect(await page.locator('body').evaluate(node => getComputedStyle(node).fontSize)).toBe('16px');
    expect(await page.locator('.blog-sidebar').evaluate(node => getComputedStyle(node).backdropFilter)).toBe('none');
    await page.evaluate(() => document.fonts.ready);
    expect(await page.locator('body').evaluate(node => getComputedStyle(node).fontFamily)).toContain('LINE Seed Sans KR');
    expect(await page.evaluate(() => document.fonts.check('16px "LINE Seed Sans KR"', '오늘의 뜻밖'))).toBe(true);
    await expect(page.locator('#home-title')).toHaveText('오늘의 뜻밖.');
    expect(await page.evaluate(() => performance.getEntriesByType('resource').filter(r => /marked-|dompurify-|metadata_sync.css/.test(r.name)))).toEqual([]);
    await page.locator('.featured-card').evaluate(node => {node.dataset.preserved='true';});
    await page.locator('.featured-card').click();
    await expect(page.locator('#reader-title')).toHaveText('일상의 작은 기록 하루의 습관');
    await expect(page.locator('.featured-card')).toHaveAttribute('data-preserved','true');
    expect(await page.locator('#article').evaluate(node => getComputedStyle(node).fontSize)).toBe('19px');
    await expect(page.locator('#article h2')).toHaveText('하루를 여는 방법');
    await expect(page.locator('#article h1')).toHaveCount(0);
    await expect(page.locator('#article table')).toBeVisible();
    await expect(page.locator('#article blockquote')).toBeVisible();
    await expect(page.locator('#article pre code')).toHaveText('const day = 1;\n');
    await expect(page.locator('#toc a')).toHaveCount(2);
    await expect(page.locator('#blog-management')).not.toHaveAttribute('open','');
    await expect(page.locator('#posts button')).toHaveCount(1);
    await expect(page.locator('#article script, #article [href^="javascript:"]')).toHaveCount(0);
    expect(await page.evaluate(() => window.blogUnsafe)).toBeUndefined();
    await page.locator('#article-toc summary').click();
    await page.locator('#toc a').first().click();
    await expect(page).toHaveURL(/#article-heading-0$/);
    await page.locator('#blog-management > summary').click();
    await page.locator('#artifact').selectOption('draft.md');
    await expect(page.locator('#article h2')).toHaveText('초고');
    await page.locator('#filter-all').click();
    await expect(page.locator('#posts button')).toHaveCount(2);
    await page.locator('#posts button').filter({hasText:'다음 이야기'}).click();
    await expect(page.locator('#reader-title')).toHaveText('다음 이야기');
    await expect(page.locator('#posts [aria-current="page"]')).toContainText('다음 이야기');
    await page.locator('#search').fill('없는 제목');
    await expect(page.locator('#posts')).toContainText('검색 결과가 없습니다.');
    await page.locator('#search').fill('');
    await page.setViewportSize({width:390,height:844});
    await expect(page.locator('#reader-title')).toBeVisible();
    expect(await page.locator('#article').evaluate(node => getComputedStyle(node).fontSize)).toBe('18px');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator('#blog-sidebar')).toBeHidden();
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#blog-sidebar')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded','false');
    await page.locator('#menu-toggle').click();
    await page.locator('.manage-link').click();
    await expect(page.locator('#blog-sidebar')).toBeHidden();
    await expect(page.locator('#blog-management')).toHaveAttribute('open','');
    await expect(page.locator('#run')).toBeVisible();
    await page.locator('#back-home').click();
    await expect(page.locator('#blog-home')).toBeVisible();
    await expect(page.locator('.story-card')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    // Narrow phones, landscape and tablets: both home and reader must fit.
    for (const viewport of [{width:320,height:568},{width:390,height:844},{width:430,height:932},{width:844,height:390},{width:960,height:720}]) {
        await page.setViewportSize(viewport);
        await expect(page.locator('#blog-sidebar')).toBeHidden();
        await expect(page.locator('.featured-card h2')).toHaveText('일상의 작은 기록 하루의 습관');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.locator('#menu-toggle').click();
        await expect(page.locator('#blog-sidebar')).toBeVisible();
        await expect(page.locator('#posts button span').last()).toHaveText('일상의 작은 기록 하루의 습관');
        await page.locator('#posts button').filter({hasText:'일상의 작은 기록'}).click();
        await expect(page.locator('#blog-sidebar')).toBeHidden();
        await expect(page.locator('#reader-title')).toHaveText('일상의 작은 기록 하루의 습관');
        await expect(page.locator('#article table')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        expect(await page.locator('.article-table').evaluate(node => node.scrollWidth > node.clientWidth)).toBe(viewport.width < 520);
        const headerBoxes = await page.locator('.site-header > button, .site-header > a').evaluateAll(nodes => nodes.map(node => {
            const {left,right,height}=node.getBoundingClientRect();return {left,right,height};
        }));
        expect(headerBoxes.every(box => box.left >= 0 && box.right <= viewport.width)).toBe(true);
        await page.locator('#back-home').click();
    }
    // Empty projects remain usable and keep management available.
    await page.route('**/api/codex/blog', route => route.fulfill({json:{configured:false,enabled:false}}));
    await page.locator('#refresh').click();
    await expect(page.locator('#blog-home')).toContainText('첫 이야기를 기다리고 있어요');
    await expect(page.locator('#reading-layout')).toBeHidden();
};
