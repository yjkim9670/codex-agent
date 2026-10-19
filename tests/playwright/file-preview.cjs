// Exercise both real panel templates and production handlers with deterministic file data.
exports.verifyFilePreview = async (page, expect) => {
    const response = await page.evaluate(async () => {
        const result = await fetchFilePanelDownload('server', ['README.md']);
        return { size: result.blob.size, text: (await result.blob.text()).slice(0, 200) };
    });
    expect(response.size).toBeGreaterThan(0);
    expect(response.text).toContain('Codex');
    const path = `${'long directory 한글/'.repeat(18)}preview.txt`;
    await page.evaluate(() => {
        document.body.dataset.workspacePath = '/fixture';
        window.previewCopied = [];
        window.previewDownloads = [];
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
            writeText: async value => window.previewCopied.push(value)
        }});
        fetchFilePanelDownload = async (root, paths) => {
            window.previewDownloads.push({ root, paths });
            return { blob: new Blob(['fixture contents']), contentDisposition: 'attachment; filename="preview.txt"' };
        };
    });
    for (const variant of ['overlay', 'work-mode']) {
        const prefix = variant === 'overlay' ? 'codex-file-browser' : 'codex-work-mode-file';
        await page.evaluate(async ({ variant, path }) => {
            const v = variant === 'overlay' ? FILE_PANEL_VARIANT_OVERLAY : FILE_PANEL_VARIANT_WORK_MODE;
            if (variant === 'work-mode') {
                workModeFileRoot = 'workspace';
                workModeFilePath = path.slice(0, path.lastIndexOf('/'));
            }
            const elements = getFilePanelVariantConfig(v).getElements();
            elements.loading?.classList.add('is-hidden');
            // Display the actual panel independently of unrelated list fetching and mobile navigation.
            const host = document.createElement('div');
            host.id = 'file-preview-verification';
            host.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--surface);display:flex;flex-direction:column;padding:8px;gap:8px;';
            const root = elements.root;
            window.previewOriginal = { root, parent: root.parentNode, next: root.nextSibling, style: root.getAttribute('style') };
            document.body.append(root);
            root.style.cssText = 'display:block!important;position:fixed;inset:0;z-index:99998;visibility:visible;opacity:1;';
            root.append(host);
            host.append(elements.path, elements.viewerPanel);
            elements.viewerPanel.style.cssText = 'display:flex;flex:1;min-width:0;';
            setFilePanelPathLabel(elements.path, 'workspace', path.slice(0, path.lastIndexOf('/')), '/fixture', { compact: true });
            await renderFileBrowserViewerIntoElements(elements, {
                root: 'workspace', path, content: 'fixture contents', size: 16, language: 'text', editable: true,
            }, { root: 'workspace' });
            syncFilePanelViewerActionState(v);
        }, { variant, path });
        const host = page.locator('#file-preview-verification');
        const dir = host.locator('.file-browser-path, .work-mode-preview-path');
        const file = host.locator('.file-browser-viewer-meta');
        await expect(host.locator('.file-browser-viewer-diff')).toHaveCount(0);
        await expect(host.locator('.file-browser-viewer-save')).not.toBeVisible();
        for (const theme of ['light', 'dark']) {
            await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
            for (const width of [1280, 390]) {
                await page.setViewportSize({ width, height: 800 });
                for (const locator of [dir, file]) {
                    const metrics = await locator.evaluate(el => {
                        el.scrollLeft = el.scrollWidth;
                        return { overflow: getComputedStyle(el).overflowX, scrolls: el.scrollLeft > 0, fits: el.getBoundingClientRect().right <= innerWidth };
                    });
                    expect(metrics).toEqual({ overflow: 'auto', scrolls: true, fits: true });
                }
                const actions = host.locator('.file-browser-viewer-actions');
                expect(await actions.evaluate(el => el.getBoundingClientRect().right <= innerWidth)).toBe(true);
                await expect(actions.locator('.file-browser-viewer-copy')).toBeVisible();
                const layout = await host.evaluate(el => {
                    const box = selector => el.querySelector(selector).getBoundingClientRect();
                    const file = box('.file-browser-viewer-meta');
                    const actions = box('.file-browser-viewer-actions');
                    const edit = box('.file-browser-viewer-edit');
                    const more = box('.file-browser-viewer-more');
                    const summary = box('.file-browser-viewer-more > summary');
                    const scale = summary.width / 28;
                    return {
                        sameRow: Math.abs((file.top + file.height / 2) - (actions.top + actions.height / 2)) < 1,
                        filenameVisible: file.width > 0 && file.right <= actions.left,
                        menuGap: (more.left - edit.right) / scale,
                        menuWidth: parseFloat(getComputedStyle(el.querySelector('.file-browser-viewer-more > summary')).width),
                        hiddenSaveWidth: box('.file-browser-viewer-save').width,
                    };
                });
                expect(layout.sameRow).toBe(true);
                expect(layout.filenameVisible).toBe(true);
                expect(layout.menuGap).toBeGreaterThanOrEqual(3);
                expect(layout.menuGap).toBeLessThanOrEqual(5);
                expect(layout.menuWidth).toBeCloseTo(28, 1);
                expect(layout.hiddenSaveWidth).toBe(0);
            }
        }
        await dir.click();
        expect(await page.evaluate(() => window.previewCopied.at(-1))).toBe(`/fixture/${path.slice(0, path.lastIndexOf('/'))}`);
        const expectedFilePath = await file.getAttribute('data-copy-path');
        expect(expectedFilePath.endsWith(path)).toBe(true);
        await file.focus();
        await page.keyboard.press('Enter');
        expect(await page.evaluate(() => window.previewCopied.at(-1))).toBe(expectedFilePath);
        await host.locator('.file-browser-viewer-copy').click();
        expect(await page.evaluate(() => window.previewCopied.at(-1))).toBe('fixture contents');
        const menu = host.locator('details.file-browser-viewer-more');
        await menu.locator('summary').click();
        await expect(menu.locator('button')).toHaveCount(3);
        await expect(menu.locator('button').first()).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(menu).not.toHaveAttribute('open', '');
        const downloadEvent = page.waitForEvent('download');
        await page.locator(`#${prefix}-download-current`).click();
        const download = await downloadEvent;
        expect(download.suggestedFilename()).toBe('preview.txt');
        expect(await page.evaluate(() => window.previewDownloads.at(-1))).toEqual({ root: 'workspace', paths: [path] });
        await page.evaluate(() => {
            // Return nodes to the original hierarchy so getElements() remains valid.
            const host = document.getElementById('file-preview-verification');
            const overlay = document.getElementById('codex-file-browser-overlay');
            const isOverlay = !!host.querySelector('#codex-file-browser-viewer-meta');
            const root = isOverlay ? overlay : document.getElementById('codex-work-mode-preview');
            while (host.firstChild) root.append(host.firstChild);
            host.remove();
            const original = window.previewOriginal;
            original.parent.insertBefore(original.root, original.next);
            if (original.style === null) original.root.removeAttribute('style');
            else original.root.setAttribute('style', original.style);
        });
    }
};
