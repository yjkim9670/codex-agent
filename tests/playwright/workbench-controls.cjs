// Run in the deterministic browser runner with CODEX_VERIFY_WORKBENCH_CONTROLS=1.
exports.verifyWorkbenchControls = async (page, expect) => {
    await expect(page.locator('#codex-service-tier-select')).toHaveCount(0);
    await expect(page.locator('#codex-secondary-model-select')).toHaveCount(1);
    await expect(page.locator('#codex-secondary-run')).toHaveCount(0);
    await page.setViewportSize({ width: 1280, height: 800 });
    const mode = page.locator('#codex-plan-mode-toggle');
    await expect(mode).toHaveText('Work');
    for (const label of ['Plan', 'Secondary', 'Plan+', 'Work']) {
        await mode.click();
        await expect(mode).toHaveText(label === 'Secondary' ? 'Sec' : label);
    }
    const input = page.locator('#codex-chat-input');
    await input.fill('모드 전환 테스트');
    for (const label of ['Plan', 'Secondary', 'Plan+', 'Work']) {
        await input.press('Shift+Tab');
        await expect(mode).toHaveText(label === 'Secondary' ? 'Sec' : label);
        await expect(input).toBeFocused();
        await expect(input).toHaveValue('모드 전환 테스트');
    }
    await input.fill('');
    await page.setViewportSize({ width: 360, height: 360 });
    await page.locator('#codex-chat-compose-tools-toggle').click();
    const mobileMode = page.locator('[data-chat-compose-action="plan"]');
    for (const label of ['Plan', 'Secondary', 'Plan+', 'Work']) {
        await mobileMode.click();
        await expect(mobileMode).toHaveText(label);
        await expect(mode).toHaveText(label === 'Secondary' ? 'Sec' : label);
    }
    await page.locator('#codex-chat-input').click();
    for (const id of ['codex-account-manage-open', 'codex-blog-dashboard-open', 'codex-usage-history-open', 'codex-usage-keepalive-history-open', 'codex-cli-version-card', 'codex-verification-mode-select']) {
        await expect(page.locator(`#codex-ui-settings-overlay #${id}`)).toHaveCount(1);
        await expect(page.locator(`#codex-controls #${id}`)).toHaveCount(0);
    }
    await page.evaluate(async () => {
        for (let i = 0; i < 55; i++) showToast(`archive-test-${i}`, { type: i === 54 ? 'success' : 'error', durationMs: 1 });
        showPersistentToast('archive-test-persistent', { tone: 'default' });
        await window.workbenchToastHistory.ready();
    });
    await page.setViewportSize({ width: 360, height: 360 });
    await page.locator('#codex-ui-settings-open').click();
    await expect(page.locator('#codex-ui-settings-title')).toHaveText('워크벤치 설정');
    await expect(page.locator('#toast-history-search, #toast-history-clear')).toHaveCount(0);
    await page.locator('#toast-history-open').click();
    await expect(page.locator('#toast-history-overlay')).toBeVisible();
    await expect(page.locator('#toast-history-list li')).toHaveCount(50);
    await page.locator('#toast-history-more').click();
    await expect(page.locator('#toast-history-list li')).toHaveCount(56);
    await page.locator('#toast-history-tone').selectOption('success');
    await expect(page.locator('#toast-history-list li')).toHaveCount(1);
    await expect(page.locator('#toast-history-list')).toContainText('archive-test-54');
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#toast-history-export').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^workbench-toast-history-.*\.json$/);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#codex-ui-settings-open').click();
    await page.locator('#toast-history-open').click();
    await page.locator('#toast-history-tone').selectOption('success');
    await expect(page.locator('#toast-history-list li')).toHaveCount(1);
    await expect(page.locator('#toast-history-list')).toContainText('완료');
    const geometry = await page.locator('#toast-history-overlay .ui-settings-card').evaluate(card => {
        const bounds = card.getBoundingClientRect();
        const body = card.querySelector('.ui-settings-body');
        return { top: bounds.top, bottom: bounds.bottom, height: innerHeight, scrollable: body.scrollHeight > body.clientHeight, width: card.scrollWidth, clientWidth: card.clientWidth };
    });
    expect(geometry.top).toBeGreaterThanOrEqual(0);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.height + 1);
    await page.locator('#toast-history-tone').selectOption('');
    await page.locator('#toast-history-more').click();
    await page.locator('#toast-history-list li').last().scrollIntoViewIfNeeded();
    await expect(page.locator('#toast-history-list li').last()).toBeInViewport();
    expect(geometry.width).toBeLessThanOrEqual(geometry.clientWidth + 1);
    await page.keyboard.press('Escape');
    await expect(page.locator('#toast-history-overlay')).not.toBeVisible();
    await expect(page.locator('#codex-ui-settings-overlay')).toBeVisible();
    await expect(page.locator('#toast-history-open')).toBeFocused();
    for (const id of ['codex-blog-dashboard-open', 'codex-usage-history-open', 'codex-usage-keepalive-history-open']) {
        const button = page.locator(`#${id}`);
        expect(await button.evaluate(el => getComputedStyle(el).backgroundImage)).toBe('none');
        expect(await button.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    }
};
