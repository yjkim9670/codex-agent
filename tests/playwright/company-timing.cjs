async function verifyCompanyTiming(page, expect) {
    await page.evaluate(() => {
        document.body.dataset.companyMode = 'true';
        const fixture = document.createElement('div');
        fixture.id = 'company-timing-check';
        fixture.style.cssText = 'position:fixed;top:0;left:0;z-index:1000;background:var(--surface);padding:12px';
        const footer = createMessageFooter();
        fixture.appendChild(footer);
        document.body.appendChild(fixture);
        window.companyTimingFixture = {company_timing: {
            backend: 'claude', pid: 123, started_at: 1000, snapshot_at: 3000,
            timeline: [{phase: 'stdin_write_finished', at: 2000, elapsed_ms: 1000, since_previous_ms: 1000}],
            request: {prompt_chars: 3, prompt_utf8_bytes: 7},
            cli: {duration_api_ms: 900}, operations: {}
        }};
        setMessageTimingBreakdown(footer, window.companyTimingFixture);
    });
    const button = page.locator('#company-timing-check .message-timing-link');
    const overlay = page.locator('#codex-message-log-overlay');
    await expect(button).toBeVisible();
    await expect(page.locator('#company-timing-check details')).toHaveCount(0);
    await expect(overlay).not.toBeVisible();
    await button.click();
    await expect(overlay).toBeVisible();
    await expect(page.locator('#codex-message-log-overlay-title')).toHaveText('타임 로그');
    await expect(page.locator('#codex-message-log-overlay-content')).toContainText('입력 쓰기·닫기 완료');
    await expect(page.locator('#codex-message-log-overlay-content')).toContainText('duration_api_ms');
    await page.locator('#codex-message-log-overlay-close-footer').click();
    await expect(overlay).not.toBeVisible();
    await page.evaluate(() => {
        const footer = document.querySelector('#company-timing-check .message-footer');
        setMessageTimingBreakdown(footer, window.companyTimingFixture);
        setMessageTimingBreakdown(footer, window.companyTimingFixture);
    });
    await expect(button).toHaveCount(1);
    await page.evaluate(() => {
        document.body.dataset.companyMode = 'false';
        setMessageTimingBreakdown(document.querySelector('#company-timing-check .message-footer'), window.companyTimingFixture);
    });
    await expect(button).toHaveCount(0);
    await page.evaluate(() => document.querySelector('#company-timing-check').remove());
}
module.exports = {verifyCompanyTiming};
