// Deterministic saved conversation; no model calls or writes to conversation storage.
exports.setupChatScroll = async page => {
    const session = {
        id: 'scroll-layout-fixture', title: 'Scroll layout fixture',
        created_at: '2026-11-04T00:00:00Z', updated_at: '2026-11-04T00:00:00Z',
        messages: Array.from({length: 24}, (_, i) => ({
            id: 'scroll-message-' + i, role: i % 2 ? 'assistant' : 'user',
            content: (`메시지 ${i}: 창 크기와 새로고침 후에도 최신 대화를 표시합니다. `).repeat(16),
            created_at: '2026-11-04T00:00:00Z'
        }))
    };
    await page.route('**/api/codex/sessions', route => route.fulfill({json: {
        sessions: [session], session_storage: {session_count: 1}
    }}));
    await page.route('**/api/codex/sessions/' + session.id, route => route.fulfill({json: {session}}));
    await page.route('**/api/codex/git/status', route => route.fulfill({json: {branch: 'fixture', changed_files_count: 0, changed_files: []}}));
};

exports.verifyChatScroll = async (page, expect) => {
    const list = page.locator('#codex-chat-messages');
    const gap = () => list.evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop);
    await expect(list.locator('.message')).toHaveCount(24);
    await expect.poll(gap, {message: 'latest conversation stays at bottom'}).toBeLessThan(2);
    for (const viewport of [{width: 1440, height: 1000}, {width: 1440, height: 650}, {width: 768, height: 900}, {width: 390, height: 780}, {width: 1280, height: 800}]) {
        await page.setViewportSize(viewport);
        await expect.poll(gap, {message: 'bottom after resize ' + JSON.stringify(viewport)}).toBeLessThan(2);
    }
    // Late font/preview reflow after the initial jump must remain at the bottom.
    await list.locator('.message').first().evaluate(el => el.style.minHeight = '1800px');
    await expect.poll(gap, {message: 'bottom after late content reflow'}).toBeLessThan(2);
    // Actual reading must disable following, including subsequent layout changes.
    await list.hover();
    await page.mouse.wheel(0, -650);
    await expect.poll(() => page.evaluate(() => state.autoScrollEnabled)).toBe(false);
    await page.setViewportSize({width: 1100, height: 700});
    await expect.poll(gap).toBeGreaterThan(200);
    expect(await page.evaluate(() => state.autoScrollEnabled)).toBe(false);
    await page.reload();
    await expect(list.locator('.message')).toHaveCount(24);
    await expect.poll(gap, {message: 'bottom after page reload'}).toBeLessThan(2);
    // Exercise the three real footer buttons with both theme palettes.
    for (const theme of ['light', 'dark']) {
        await page.evaluate(theme => {
            document.documentElement.dataset.theme = theme;
            const footer = document.querySelector('.message-footer');
            footer.querySelectorAll('.message-detail-link').forEach(button => button.classList.remove('is-hidden'));
            footer.querySelector('.message-footer-links').classList.remove('is-hidden');
        }, theme);
        const buttons = list.locator('.message-footer').first().locator('.message-detail-link');
        await expect(buttons).toHaveCount(3);
        for (const button of await buttons.all()) {
            await expect(button).toBeVisible();
            expect(await button.evaluate(el => parseFloat(getComputedStyle(el).borderRadius))).toBe(9);
        }
    }
};
