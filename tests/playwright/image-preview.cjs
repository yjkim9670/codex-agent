// Run with a >1 MiB image in the server root, exercising the real raw-file API.
exports.verifyImagePreview = async (page, expect) => {
    const path = process.env.CODEX_VERIFY_IMAGE_PATH;
    expect(path, 'CODEX_VERIFY_IMAGE_PATH must identify a test image').toBeTruthy();
    for (const variant of ['overlay', 'work-mode']) {
        await page.evaluate(async ({ variant, path }) => {
            const config = getFilePanelVariantConfig(variant === 'overlay'
                ? FILE_PANEL_VARIANT_OVERLAY : FILE_PANEL_VARIANT_WORK_MODE);
            const elements = config.getElements();
            const host = document.createElement('div');
            host.id = 'image-preview-verification';
            host.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--surface);display:flex;';
            window.imagePreviewOriginal = { element: elements.viewerContent,
                parent: elements.viewerContent.parentNode, next: elements.viewerContent.nextSibling };
            document.body.append(host);
            host.append(elements.viewerContent);
            elements.viewerContent.style.cssText = 'display:block;width:100%;height:100%;';
            const result = await fetchFileBrowserFile('server', path);
            if (result.size <= 1024 * 1024) throw new Error('Fixture must exceed the old image limit');
            await renderFileBrowserViewerIntoElements(elements, result, { root: 'server' });
        }, { variant, path });
        const host = page.locator('#image-preview-verification');
        const image = host.locator('img');
        await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
        for (const width of [1280, 768, 390]) {
            await page.setViewportSize({ width, height: 800 });
            await expect(image).toBeVisible();
            expect(await image.evaluate(el => {
                const box = el.getBoundingClientRect();
                return box.width > 0 && box.left >= 0 && box.right <= innerWidth;
            })).toBe(true);
        }
        // A decode failure must replace the broken image with useful guidance.
        await image.dispatchEvent('error');
        await expect(host.locator('[role="status"]')).toContainText('다운로드하여 확인');
        await expect(image).toHaveCount(0);
        await page.evaluate(() => {
            const { element, parent, next } = window.imagePreviewOriginal;
            element.removeAttribute('style');
            parent.insertBefore(element, next);
            document.getElementById('image-preview-verification').remove();
        });
    }
};
