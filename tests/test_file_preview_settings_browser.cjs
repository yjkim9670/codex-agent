// Run with a temporary Workbench server: PLAYWRIGHT_BROWSERS_PATH=./.playwright-browsers node tests/test_file_preview_settings_browser.cjs http://127.0.0.1:38941
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');
exports.verifyPreviewSettings = async (browser, url) => {
    const fixturePath = path.join(__dirname, '../.local/preview-settings-fixture.txt');
    fs.writeFileSync(fixturePath, '한글 preview line\n'.repeat(75000));
    const sourcePath = fixturePath.replace('.txt', '.sv');
    fs.writeFileSync(sourcePath, ('// ' + 's'.repeat(250) + '\n').repeat(6000));
    try {
        for (const width of [1280, 390]) {
            const context = await browser.newContext({ viewport: { width, height: 844 } });
            const page = await context.newPage();
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            await page.route('**/api/codex/git/status', route => route.fulfill({json: {branch: 'fixture', changed_files_count: 0, changed_files: []}}));
            await page.goto(url, { waitUntil: 'domcontentloaded' });
            await page.locator('#codex-ui-settings-open').click();
            for (const select of await page.locator('#codex-ui-settings-overlay select').all()) {
                if (!await select.isVisible()) continue;
                const metrics = await select.evaluate(el => ({
                    height: parseFloat(getComputedStyle(el).height),
                    fits: el.getBoundingClientRect().right <= innerWidth
                }));
                assert.ok(metrics.height >= 40, 'settings dropdown height');
                assert.ok(metrics.fits, 'settings dropdown fits viewport');
            }
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
                for (const readBytes of FILE_BROWSER_PREVIEW_BYTE_OPTIONS) {
                    for (const lines of FILE_BROWSER_PREVIEW_LINE_OPTIONS) {
                        fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings({ readBytes, lines });
                        const fits = 'x'.repeat(readBytes);
                        check(!shouldUseLargeFileBrowserTextPreview(fits, { lineCount: lines, size: readBytes }), 'exact limits use full source viewer');
                        check(shouldHighlightFileBrowserSource(fits, lines, true), 'exact limits allow highlighting');
                        check(shouldUseLargeFileBrowserTextPreview(fits + 'x'), 'character overflow uses lightweight viewer');
                        check(!shouldHighlightFileBrowserSource(fits + 'x', 1, true), 'character overflow skips highlighting');
                        check(shouldUseLargeFileBrowserTextPreview('x', { lineCount: lines + 1 }), 'line overflow uses lightweight viewer');
                        check(!shouldHighlightFileBrowserSource('x', lines + 1, true), 'line overflow skips highlighting');
                        check(shouldUseLargeFileBrowserTextPreview('x', { size: readBytes + 1 }), 'file byte overflow uses lightweight viewer');
                        check(shouldUseLargeFileBrowserTextPreview('x', { truncated: true }), 'truncated preview stays lightweight');
                        check(!shouldHighlightFileBrowserSource('x', 1, false), 'plain text skips highlighting');
                    }
                }
                // A file above the old fixed limits must gain full highlighted rows
                // when the user raises the existing preview settings.
                const medium = {
                    path: '.local/highlight-settings.js', language: 'javascript', is_script: true,
                    content: '// source comment with enough content to exceed old limits\n'.repeat(999),
                    editable: true, truncated: false
                };
                medium.size = new TextEncoder().encode(medium.content).length;
                for (const variant of [FILE_PANEL_VARIANT_OVERLAY, FILE_PANEL_VARIANT_WORK_MODE]) {
                    const elements = getFilePanelVariantConfig(variant).getElements();
                    fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings(null);
                    await renderFileBrowserViewerIntoElements(elements, medium, { root: 'server' });
                    check(!elements.viewerContent.querySelector('.file-browser-source'), 'default line ceiling uses lightweight viewer');
                    fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings({ readBytes: 262144, lines: 2000 });
                    await renderFileBrowserViewerIntoElements(elements, medium, { root: 'server' });
                    check(elements.viewerContent.querySelectorAll('.file-browser-source-line').length === 1000, 'raised settings render all source rows');
                    check(!!elements.viewerContent.querySelector('.file-browser-source-line-content span'), 'raised settings apply syntax tokens');
                    fileBrowserPreviewSettings = normalizeFileBrowserPreviewSettings(null);
                    await renderFileBrowserViewerIntoElements(elements, medium, { root: 'server' });
                    check(!elements.viewerContent.querySelector('.file-browser-source'), 'lowering settings restores lightweight viewer');
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
            // Change real settings while both panel types already have truncated files open.
            await page.evaluate(async () => {
                for (const [variant, path] of [
                    [FILE_PANEL_VARIANT_OVERLAY, '.local/preview-settings-fixture.txt'],
                    [FILE_PANEL_VARIANT_WORK_MODE, '.local/preview-settings-fixture.sv']
                ]) {
                    const first = await fetchFileBrowserFile('server', path);
                    await renderFileBrowserViewerIntoElements(getFilePanelVariantConfig(variant).getElements(), first, { root: 'server' });
                }
            });
            await page.locator('#codex-file-preview-lines').selectOption('5000');
            await page.locator('#codex-file-preview-bytes').selectOption('1048576');
            await page.waitForFunction(() => [FILE_PANEL_VARIANT_OVERLAY, FILE_PANEL_VARIANT_WORK_MODE].every(variant =>
                getFilePanelEditState(variant).previewResult.preview_max_bytes === 1048576));
            await page.evaluate(() => {
                for (const variant of [FILE_PANEL_VARIANT_OVERLAY, FILE_PANEL_VARIANT_WORK_MODE]) {
                    const elements = getFilePanelVariantConfig(variant).getElements();
                    const result = getFilePanelEditState(variant).previewResult;
                    const expected = buildFileBrowserLargeTextSlice(result.content);
                    assertPreview(elements.viewerContent.querySelector('code').textContent === expected.text, 'rendered text follows settings');
                    assertPreview(!result.editable, 'truncated preview cannot edit');
                    if (result.path.endsWith('.sv')) {
                        assertPreview(expected.text.length > 1000000, 'SV is no longer clipped by the old 218K character ceiling');
                    } else {
                        assertPreview(expected.endLine === 5000, 'text shows configured 5000 lines');
                    }
                }
                function assertPreview(condition, message) { if (!condition) throw new Error(message); }
            });
            // Settings changes must preserve an active edit buffer.
            await page.evaluate(() => {
                const state = getFilePanelEditState(FILE_PANEL_VARIANT_OVERLAY);
                state.editing = true; state.dirty = true; state.editBuffer = 'unsaved changes';
            });
            await page.locator('#codex-file-preview-lines').selectOption('2000');
            assert.equal(await page.evaluate(() => {
                const state = getFilePanelEditState(FILE_PANEL_VARIANT_OVERLAY);
                return state.editing && state.dirty && state.editBuffer === 'unsaved changes';
            }), true);
            assert.deepEqual(errors, []);
            await context.close();
            console.log(`PASS preview settings, persistence, read-more API, pagination, edit safety (${width}px)`);
        }
    } finally {
        fs.rmSync(fixturePath, {force: true});
        fs.rmSync(sourcePath, {force: true});
    }
};
if (require.main === module) {
    (async () => {
        const browser = await chromium.launch({ headless: true });
        try { await exports.verifyPreviewSettings(browser, process.argv[2]); }
        finally { await browser.close(); }
    })().catch(error => { console.error(error); process.exitCode = 1; });
}
