async function verifyResourceUsage(page, expect) {
    await page.waitForFunction(() => state.settings.loaded && state.sessions.length > 0);
    const primary = page.locator('#codex-session-list');
    const mobile = page.locator('#codex-mobile-session-list');
    const count = await primary.locator(':scope > .session-item').count();
    expect(count).toBeGreaterThan(0);
    await expect(mobile.locator(':scope > .session-item')).toHaveCount(0);
    // Exercise the actual overlay lifecycle, including repeated summary renders.
    await page.evaluate(() => {
        document.querySelector('.app').classList.add(WORK_MODE_CLASS);
        openMobileSessionOverlay();
    });
    await expect(mobile.locator(':scope > .session-item')).toHaveCount(count);
    await page.evaluate(() => renderSessions());
    await expect(mobile.locator(':scope > .session-item')).toHaveCount(count);
    await page.evaluate(() => closeMobileSessionOverlay());
    await expect(mobile).toBeEmpty();
    await expect(primary.locator(':scope > .session-item')).toHaveCount(count);

    const compactResponse = page.waitForResponse(response =>
        response.url().includes('/api/codex/usage?compact=1'));
    await page.evaluate(() => refreshUsageSummary());
    const compact = await (await compactResponse).json();
    expect(compact.usage_history.is_summary).toBe(true);
    expect(compact.usage_history.items).toBeUndefined();
    expect(compact.usage.usage_reconciliation.trend).toBeUndefined();
    expect(compact.usage_history.relation).toBeTruthy();

    const historyResponse = page.waitForResponse(response =>
        response.url().includes('/api/codex/usage/history?'));
    await page.evaluate(() => openUsageHistoryOverlay());
    const detailed = await (await historyResponse).json();
    expect(Array.isArray(detailed.usage_history.items)).toBe(true);
    expect(detailed.usage_history.items.length).toBeGreaterThan(0);
    await expect(page.locator('#codex-usage-history-overlay')).toHaveClass(/is-visible/);
    await expect(page.locator('#codex-usage-history-chart')).toBeVisible();
    await page.evaluate(() => closeUsageHistoryOverlay());

    await page.evaluate(() => {
        const indicator = document.createElement('div');
        indicator.id = 'resource-test-indicator';
        indicator.className = 'message-stream-indicator-bar';
        indicator.innerHTML = '<span class="message-stream-indicator-dot"></span>';
        document.body.appendChild(indicator);
    });
    const dot = page.locator('#resource-test-indicator .message-stream-indicator-dot');
    const keyframes = await dot.evaluate(element => element.getAnimations()[0].effect.getKeyframes());
    expect(keyframes.every(frame => frame.transform && !('left' in frame))).toBe(true);
    const first = await dot.evaluate(element => getComputedStyle(element).transform);
    await page.waitForTimeout(150);
    expect(await dot.evaluate(element => getComputedStyle(element).transform)).not.toBe(first);
    await page.emulateMedia({reducedMotion: 'reduce'});
    expect(await dot.evaluate(element => element.getAnimations().length)).toBe(0);
    await page.locator('#resource-test-indicator').evaluate(element => element.remove());

    console.log(JSON.stringify({sessionRows: count, closedOverlayRows: 0,
        compactUsageBytes: JSON.stringify(compact).length,
        detailedUsageBytes: JSON.stringify(detailed).length,
        chartRows: detailed.usage_history.items.length}));
}

module.exports = {verifyResourceUsage};
