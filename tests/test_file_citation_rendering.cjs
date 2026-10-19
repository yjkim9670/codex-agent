// Run: PLAYWRIGHT_BROWSERS_PATH=./.playwright-browsers node tests/test_file_citation_rendering.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
const markdown = source.slice(source.indexOf('function normalizeMarkdownRenderOptions('), source.indexOf('function normalizeError('));
const paths = source.slice(source.indexOf('function normalizeFilesystemPath('), source.indexOf('function shortenAbsolutePathsInText('));
const prefixes = source.match(/^const ABSOLUTE_PATH_HINT_PREFIXES = Object\.freeze\(\[[\s\S]*?\]\);/m)[0];

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage();
        await page.setContent('<body data-workspace-path="/Users/dinya/works/dev_workspace"><main></main></body>');
        for (const vendor of ['marked-18.0.6.umd.js', 'dompurify-3.4.12.min.js']) {
            await page.addScriptTag({ path: path.join(root, 'codex-web-app/static/vendor', vendor) });
        }
        await page.addScriptTag({ content: `${prefixes}\n${paths}\n${markdown}` });
        const results = await page.evaluate(() => {
            const filePath = '/Users/dinya/works/dev_workspace/codex_workbench/outputs/excel-preview-test-20261019/excel-preview-test.xlsx';
            const citation = `:codex-file-citation{path="${filePath}" purpose="output"}`;
            const host = document.querySelector('main');
            const verify = () => {
                host.innerHTML = renderMarkdown(`생성 완료: ${citation}\n\n**${citation}**\n\n\`${citation}\`\n\n\`\`\`text\n${citation}\n\`\`\``);
                const links = [...host.querySelectorAll('a.message-label-link')];
                const result = {
                    labels: links.map(link => link.textContent),
                    targets: links.map(link => link.dataset.filePath),
                    code: [...host.querySelectorAll('code')].map(code => code.textContent.trim()),
                };
                window.openFileBrowserFromAbsolutePath = (target, options) => {
                    result.opened = { target, options };
                    return true;
                };
                hydrateMessageLabelLinks(host);
                hydrateMessageLabelLinks(host);
                links[0].click();
                host.innerHTML = renderMarkdown([
                    ':codex-file-citation{path="javascript:alert(1)" purpose="output"}',
                    ':codex-file-citation{path="/tmp/incomplete.xlsx"',
                    ':codex-file-citation{path="/tmp/a.xlsx" path="/tmp/b.xlsx"}',
                    '[existing](</tmp/existing file.xlsx>)',
                    `:codex-file-citation{purpose="output" path=${JSON.stringify('/tmp/한글 "이름" <img src=x onerror=alert(1)>.xlsx')}}`,
                ].join('\n\n'));
                result.otherTargets = [...host.querySelectorAll('a.message-label-link')].map(link => link.dataset.filePath);
                result.unsafe = !!host.querySelector('img, script, [onerror], [href^="javascript:"]');
                result.malformedPreserved = host.textContent.includes(':codex-file-citation{path="/tmp/incomplete.xlsx"');
                return result;
            };
            const marked = verify();
            window.marked = undefined;
            return { marked, fallback: verify(), filePath, citation };
        });
        for (const result of [results.marked, results.fallback]) {
            assert.deepEqual(result.labels, ['excel-preview-test.xlsx', 'excel-preview-test.xlsx']);
            assert.deepEqual(result.targets, [results.filePath, results.filePath]);
            assert.deepEqual(result.code, [results.citation, results.citation]);
            assert.equal(result.opened.target, results.filePath);
            assert.deepEqual(result.otherTargets, ['/tmp/existing file.xlsx', '/tmp/한글 "이름" <img src=x onerror=alert(1)>.xlsx']);
            assert.equal(result.unsafe, false);
            assert.equal(result.malformedPreserved, true);
        }
        console.log('File citation rendering, preview clicks, code examples, fallback, and escaping passed.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
