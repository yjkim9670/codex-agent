// Run against an unused local Workbench port: CODEX_VERIFY_URL=http://127.0.0.1:3197
const assert = require('node:assert/strict');
const { chromium, expect } = require('@playwright/test');
(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 768, height: 1000 }, hasTouch: true });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(process.env.CODEX_VERIFY_URL || 'http://127.0.0.1:3197');
        await expect(page.locator('html')).toHaveAttribute('data-view-mode', 'fold-inner');
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'single');
        await expect(page.locator('.work-surface-tabs')).toBeVisible();
        await expect(page.locator('.chat')).toBeVisible();
        await expect(page.locator('#codex-work-mode-preview')).toBeHidden();
        const draft = 'Fold draft retained';
        await page.locator('#codex-chat-input').fill(draft);
        await page.locator('[data-work-view="list"]').click();
        await expect(page.locator('.chat')).toBeHidden();
        await expect(page.locator('#codex-work-mode-preview .work-mode-file-list-panel')).toBeVisible();
        await page.locator('[data-work-view="viewer"]').click();
        await expect(page.locator('#codex-work-mode-preview .file-browser-viewer-panel')).toBeVisible();
        await page.locator('[data-work-view="chat"]').click();
        await expect(page.locator('#codex-chat-input')).toHaveValue(draft);
        await page.setViewportSize({ width: 932, height: 568 });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'horizontal');
        await expect(page.locator('.work-surface-tabs')).toBeHidden();
        await expect(page.locator('.chat')).toBeVisible();
        await expect(page.locator('#codex-work-mode-preview')).toBeVisible();
        const panes = await page.evaluate(() => ['.chat', '#codex-work-mode-preview'].map(s => document.querySelector(s).getBoundingClientRect().width));
        assert(panes.every(w => w >= 399), JSON.stringify(panes));
        await page.setViewportSize({ width: 650, height: 900 });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'single');
        // Select through the real settings handler without needing to open the overlay.
        await page.locator('#codex-work-arrangement').selectOption('vertical', { force: true });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'vertical');
        await expect(page.locator('.work-surface-tabs')).toBeHidden();
        const geometry = await page.evaluate(() => {
            const chat = document.querySelector('.chat').getBoundingClientRect();
            const files = document.querySelector('#codex-work-mode-preview').getBoundingClientRect();
            return { cw: chat.width, fw: files.width, ct: chat.top, fb: files.bottom };
        });
        assert(Math.abs(geometry.cw - geometry.fw) < 2 && geometry.ct >= geometry.fb, JSON.stringify(geometry));
        const divider = page.locator('#codex-work-mode-divider');
        const box = await divider.boundingBox();
        const before = await page.locator('.chat').boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2, box.y - 60);
        await page.mouse.up();
        const after = await page.locator('.chat').boundingBox();
        assert(after.height > before.height + 20, JSON.stringify({ before, after, box, state: await page.evaluate(() => ({ ratio: workModeSplitRatio, arrangement: resolveWorkModeArrangement(), pointer: workModeResizePointerId })) }));
        await page.reload();
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'vertical');
        await page.locator('#codex-work-arrangement').selectOption('auto', { force: true });
        await page.setViewportSize({ width: 932, height: 568 });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'horizontal');
        await page.evaluate(() => { setMobileKeyboardOpen(true); syncWorkModeArrangement(); });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'single');
        await expect(page.locator('.chat')).toBeVisible();
        await page.evaluate(() => { setMobileKeyboardOpen(false); syncWorkModeArrangement(); });
        await expect(page.locator('html')).toHaveAttribute('data-work-arrangement', 'horizontal');
        assert.deepEqual(errors, []);
        console.log('PASS: Fold portrait detection, tabs, draft retention, rotation, narrow window, vertical resize, persistence and keyboard fallback');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
