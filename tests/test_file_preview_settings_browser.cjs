// Run with a temporary Workbench server: PLAYWRIGHT_BROWSERS_PATH=./.playwright-browsers node tests/test_file_preview_settings_browser.cjs http://127.0.0.1:38941
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');
(async () => {
    const fixturePath = path.join(__dirname, '../.local/preview-settings-fixture.txt');
    fs.writeFileSync(fixturePath, '한글 preview line\n'.repeat(75000));
    const browser = await chromium.launch({ headless: true });
    try {
        for (const width of [1280, 390]) {
            const context = await browser.newContext({ viewport: { width, height: 844 } });
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.route('**/api/codex/git/status', route => route.fulfill({json: {branch: 'fixture', changed_files_count: 0, changed_files: []}}));
            await page.goto(process.argv[2], { waitUntil: 'domcontentloaded' });
            await page.locator('#codex-ui-settings-open').click();
            await page.locator('#codex-file-preview-bytes').selectOption('1048576');
            await page.locator('#codex-file-preview-lines').selectOption('5000');
            await page.reload({ waitUntil: 'domcontentloaded' });
            assert.equal(await page.locator('#codex-file-preview-bytes').inputValue(), '1048576');
            assert.equal(await page.locator('#codex-file-preview-lines').inputValue(), '5000');
            const result = await page.evaluate(async () => {
                const check = (condition, message) => { if (!condition) throw new Error(message); };
                // Real encrypted client -> API -> fixture file -> decoded response.
                const large = await fetchFileBrowserFile('server', '.local/preview-settings-fixture.txt');
                check(large.preview_max_bytes === 1048576 && large.truncated && !large.editable, 'configured read ceiling and edit safety');
                for (const lines of [750, 2000, 5000]) {
                    fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings({ lines, readBytes: 65536 });
                    const content = 'x\n'.repeat(7000);
                    const slice = buildFileBrowserLargeTextSlice(content);
                    check(slice.endLine === lines && slice.suffixOmitted, `line ceiling ${lines}`);
                    const long = buildFileBrowserLargeTextSlice('x'.repeat(400000));
                    check(long.text.length === getFileBrowserPreviewDisplayLimits().maxChars, `character ceiling ${lines}`);
                    let offset = 0, offsetLine = 1, joined = '';
                    while (offset < content.length) {
                        const part = buildFileBrowserLargeTextSlice(content, { offset, offsetLine });
                        check(part.endIndex > offset, 'pagination advances');
                        joined += part.text;
                        offset = part.endIndex; offsetLine = part.endLine;
                    }
                    check(joined === content, 'pagination preserves all content');
                }
                fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings(null);
                for (const variant of [FILE_PANEL_VARIANT_OVERLAY, FILE_PANEL_VARIANT_WORK_MODE]) {
                    const elements = getFilePanelVariantConfig(variant).getElements();
                    const first = await fetchFileBrowserFile('server', '.local/preview-settings-fixture.txt');
                    await renderFileBrowserViewerIntoElements(elements, first, { root: 'server' });
                    const find = text => [...elements.viewerContent.querySelectorAll('button')].find(button => button.textContent.includes(text));
                    check(!!find('다음 구간'), 'next page control');
                    find('다음 구간').click();
                    check(!!find('처음으로'), 'first page control');
                    const more = find('까지 읽기');
                    check(!!more, 'read more control');
                    more.click();
                    const deadline = performance.now() + 15000;
                    while (getFilePanelEditState(variant).previewResult.preview_max_bytes === 65536 && performance.now() < deadline) {
                        await new Promise(resolve => setTimeout(resolve, 20));
                    }
                    check(getFilePanelEditState(variant).previewResult.preview_max_bytes === 262144, 'read more increases API allowance');
                }
                const normalized = normalizeFileBrowserPreviewSettings({ readBytes: 999999999, lines: 999999999 });
                check(normalized.readBytes === 65536 && normalized.lines === 750, 'invalid storage values fall back');
                return true;
            });
            assert.equal(result, true);
            await page.locator('#codex-ui-settings-open').click();
            await page.locator('#codex-ui-settings-reset').click();
            assert.equal(await page.locator('#codex-file-preview-bytes').inputValue(), '65536');
            assert.equal(await page.locator('#codex-file-preview-lines').inputValue(), '750');
            assert.deepEqual(errors, []);
            await context.close();
            console.log(`PASS preview settings, persistence, read-more API, pagination, edit safety (${width}px)`);
        }
    } finally { await browser.close(); fs.rmSync(fixturePath, {force: true}); }
})().catch(error => { console.error(error); process.exitCode = 1; });
