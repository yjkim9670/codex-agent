// Exercise production CSS at the responsive boundaries using representative content.
async function verifyTypography(page, expect) {
    expect(await page.evaluate(() => getComputedStyle(document.body).zoom)).toBe('1');
    await page.evaluate(() => {
        document.body.innerHTML = `<main class="app" style="padding:12px;overflow:auto;height:100%">
            <section class="message assistant"><div class="message-bubble">한글 본문 ABC 123
                <a href="#">파일 링크</a><blockquote>인용문 설명</blockquote>
                <pre class="markdown-code-block"><span class="markdown-code-gutter">1</span><code><span class="file-code-token-comment">// 코드 주석</span></code></pre>
            </div><div class="message-meta">시간 · 상태 · 메타정보</div></section>
            <section class="message user"><div class="message-bubble">사용자 메시지 <a href="#">링크</a></div></section>
            <div class="file-browser-entry-meta">경로 /workspace/very-long-file-name.txt</div>
            <div class="file-browser-markdown"><p>Markdown 파일 미리보기</p><code>inline code</code></div>
            <pre class="file-browser-source"><span class="file-code-token-comment">// 소스 주석</span></pre>
            <div class="file-browser-editor"><div class="file-browser-editor-body">
                <pre class="file-browser-editor-gutter">1\n2</pre>
                <textarea class="file-browser-editor-input">한글 ABC\n다음 줄</textarea>
                <pre class="file-browser-editor-syntax">한글 ABC\n다음 줄</pre>
            </div></div>
            <button class="btn primary">주요 버튼</button>
            <div class="toast">알림 메시지</div>
        </main>`;
    });
    for (const width of [1440, 840, 600, 390]) {
        await page.setViewportSize({width, height: 1000});
        for (const theme of ['light', 'dark']) {
            await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
            await page.evaluate(() => document.fonts.ready);
            const results = await page.evaluate(() => {
                const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
                const luminance = channels => channels.map(c => {
                    c /= 255;
                    return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
                }).reduce((n, c, i) => n + c * [.2126, .7152, .0722][i], 0);
                const contrast = (fg, bg) => {
                    const a = luminance(rgb(fg)), b = luminance(rgb(bg));
                    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
                };
                const background = el => {
                    while (el) {
                        const color = getComputedStyle(el).backgroundColor;
                        if (color !== 'rgba(0, 0, 0, 0)' && color !== 'transparent') return color;
                        el = el.parentElement;
                    }
                    return 'rgb(255, 255, 255)';
                };
                const checks = [
                    ['.message.assistant .message-bubble', 14],
                    ['.message.user .message-bubble', 14],
                    ['.message.assistant a', 14], ['.message.user a', 14],
                    ['.message-bubble blockquote', 14], ['.message-meta', 12],
                    ['.file-browser-entry-meta', 12], ['.file-browser-markdown', 14],
                    ['.file-browser-markdown code', 13], ['.message-bubble pre code', 13],
                    ['.message-bubble .file-code-token-comment', 13],
                    ['.message-bubble .markdown-code-gutter', 13],
                    ['.file-browser-source .file-code-token-comment', 13],
                    ['.btn.primary', 12], ['.toast', 12],
                ].map(([selector, minimum]) => {
                    const el = document.querySelector(selector), style = getComputedStyle(el);
                    return {selector, minimum, size: parseFloat(style.fontSize), contrast: contrast(style.color, background(el))};
                });
                // All secondary tokens must meet contrast on every common panel surface.
                for (const surface of ['--bg', '--surface', '--surface-muted', '--surface-raised']) {
                    for (const token of ['--text-primary', '--text-secondary', '--text-tertiary', '--text-muted']) {
                        const probe = document.createElement('span');
                        probe.style.cssText = `color:var(${token});background:var(${surface})`;
                        document.body.append(probe);
                        const style = getComputedStyle(probe);
                        checks.push({selector: `${token}/${surface}`, minimum: 0, size: 0, contrast: contrast(style.color, style.backgroundColor)});
                        probe.remove();
                    }
                }
                const editor = ['.file-browser-editor-input', '.file-browser-editor-syntax', '.file-browser-editor-gutter'].map(selector => {
                    const style = getComputedStyle(document.querySelector(selector));
                    return [style.fontFamily, style.fontSize, style.fontWeight, style.lineHeight];
                });
                return {checks, editor, fontLoaded: document.fonts.check('500 12px "IBM Plex Sans KR"', '한글'),
                    bubbleFits: [...document.querySelectorAll('.message-bubble')].every(el => el.getBoundingClientRect().right <= innerWidth),
                    pageFits: document.documentElement.scrollWidth <= innerWidth};
            });
            for (const check of results.checks) {
                const label = `${width}px ${theme} ${check.selector}`;
                expect(check.size, label).toBeGreaterThanOrEqual(check.minimum);
                expect(check.contrast, label).toBeGreaterThanOrEqual(4.5);
            }
            expect(results.editor[1]).toEqual(results.editor[0]);
            expect(results.editor[2]).toEqual(results.editor[0]);
            expect(results.fontLoaded).toBe(true);
            expect(results.bubbleFits, `${width}px ${theme} bubble width`).toBe(true);
            expect(results.pageFits, `${width}px ${theme} page width`).toBe(true);
        }
    }
}

module.exports = {verifyTypography};
