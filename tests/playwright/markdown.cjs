// Use production rendering and popup HTML to check document layout and sanitization.
async function verifyMarkdown(page, expect) {
    const source = [
        '# 문서 제목', '', '## 둘째 제목', '', '### 셋째 제목', '',
        '본문 문단과 **강조**, `inline code`.', '', '다음 문단.', '',
        '- 첫 항목', '  - 중첩 항목', '- 다음 항목', '',
        '> 인용문 안내', '',
        '| 열 | 값 |', '| --- | --- |', `| ${'long_column_'.repeat(35)} | 값 |`, '',
        '```javascript', `const text = "${'long code '.repeat(40)}";`, 'console.log(text);', '```', '',
        `[긴 링크](https://example.com/${'long-path'.repeat(45)})`, '',
        '[상대 링크](./notes.md)', '', '![local image](./image.png)', '',
        '<img onerror="window.markdownUnsafe=true">',
        '<script>window.markdownUnsafe=true</script>', '', '[unsafe](javascript:alert(1))', '',
        '```mermaid', 'graph TD', '  A[시작] --> B[완료]', '```'
    ].join('\n');
    await page.evaluate(source => {
        const host = document.createElement('main');
        host.id = 'markdown-verification';
        host.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--surface);overflow:auto;padding:12px;';
        host.innerHTML = '<section class="message assistant"><div class="message-bubble"></div></section><article class="file-browser-markdown"></article>';
        document.body.appendChild(host);
        for (const node of host.querySelectorAll('.message-bubble, .file-browser-markdown')) {
            node.innerHTML = renderMarkdown(source, {showCodeLineNumbers: true});
            hydrateRenderedMarkdown(node);
        }
        window.markdownPreviewUrl = URL.createObjectURL(new Blob([
            buildFilePanelMarkdownPreviewDocument({name: 'sample.md', path: 'docs/sample.md', content: source})
        ], {type: 'text/html'}));
        window.markdownCopied = [];
        Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
            writeText: async text => window.markdownCopied.push(text)
        }});
    }, source);
    const popup = await page.context().newPage();
    const popupErrors = [];
    popup.on('pageerror', error => popupErrors.push(error.message));
    popup.on('console', message => { if (message.type() === 'error') popupErrors.push(message.text()); });
    await popup.goto(await page.evaluate(() => window.markdownPreviewUrl));
    await expect(popup.locator('.markdown-code-language')).toHaveText('javascript');
    await expect(popup.locator('.file-browser-mermaid svg')).toBeVisible();
    await expect(page.locator('#markdown-verification > .file-browser-markdown .file-browser-mermaid svg')).toBeVisible();
    for (const width of [1280, 390]) {
        await page.setViewportSize({width, height: 900});
        await popup.setViewportSize({width, height: 900});
        for (const theme of ['light', 'dark']) {
            await page.evaluate(theme => {
                document.documentElement.dataset.theme = theme;
            }, theme);
            await popup.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
            const measure = () => {
                const nodes = [...document.querySelectorAll('.message-bubble, .file-browser-markdown')].filter(node => node.closest('#markdown-verification') || document.body.classList.contains('file-browser-markdown-preview-page'));
                return nodes.map(node => {
                    const style = el => el.ownerDocument.defaultView.getComputedStyle(el);
                    const table = node.querySelector('.markdown-table-scroll');
                    const code = node.querySelector('pre');
                    const shell = node.querySelector('.markdown-code-shell');
                    return {
                        headings: ['h1', 'h2', 'h3'].map(tag => parseFloat(style(node.querySelector(tag)).fontSize)),
                        lineHeightRatio: parseFloat(style(node).lineHeight) / parseFloat(style(node).fontSize),
                        paragraphGap: parseFloat(style(node.querySelector('p')).marginBottom),
                        tableScrolls: style(table).overflowX === 'auto' && table.scrollWidth > table.clientWidth,
                        codeScrolls: style(code).overflowX === 'auto' && code.scrollWidth > code.clientWidth,
                        fits: node.scrollWidth <= node.clientWidth + 1,
                        headerAboveCode: shell.querySelector('button').getBoundingClientRect().bottom <= code.getBoundingClientRect().top + 1,
                        unsafe: !!node.querySelector('script, [onerror], [href^="javascript:"]'),
                        copyCount: shell.querySelectorAll('button').length,
                    };
                });
            };
            const results = [...await page.evaluate(measure), ...await popup.evaluate(measure)];
            for (const result of results) {
                expect(result.headings[0]).toBeGreaterThan(result.headings[1]);
                expect(result.headings[1]).toBeGreaterThan(result.headings[2]);
                expect(result.paragraphGap).toBeGreaterThanOrEqual(8);
                expect(result.tableScrolls).toBe(true);
                expect(result.codeScrolls).toBe(true);
                expect(result.fits).toBe(true);
                expect(result.headerAboveCode).toBe(true);
                expect(result.unsafe).toBe(false);
                expect(result.copyCount).toBe(1);
                expect(result.lineHeightRatio).toBeCloseTo(1.7, 2);
            }
        }
    }
    await page.locator('#markdown-verification .message-bubble .markdown-code-copy').click();
    expect(await page.evaluate(() => window.markdownCopied[0])).toBe(`const text = "${'long code '.repeat(40)}";\nconsole.log(text);`);
    await expect(page.locator('#markdown-verification .message-bubble .markdown-code-copy')).toHaveText('복사됨');
    await popup.locator('.markdown-code-copy').click();
    await expect(popup.locator('.markdown-code-copy')).toHaveText('복사됨');
    expect(popupErrors).toEqual([]);
    await popup.close();
    await page.evaluate(() => URL.revokeObjectURL(window.markdownPreviewUrl));
}
module.exports = {verifyMarkdown};
