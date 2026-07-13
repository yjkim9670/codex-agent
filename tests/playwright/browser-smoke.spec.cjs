const { test, expect } = require('playwright/test');

const targetUrl = process.env.CODEX_VERIFY_URL;
const targetSelector = process.env.CODEX_VERIFY_SELECTOR || 'body';
const timeoutMs = Number(process.env.CODEX_VERIFY_TIMEOUT_MS || 20_000);

test('browser UI smoke check', async ({ page }) => {
    test.setTimeout(timeoutMs + 5_000);
    const browserErrors = [];
    page.on('console', message => {
        if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`);
    });
    page.on('pageerror', error => {
        browserErrors.push(`page: ${error.message}`);
    });

    const response = await page.goto(targetUrl, {
        waitUntil: 'domcontentloaded',
        timeout: timeoutMs,
    });
    expect(response, 'navigation must return an HTTP response').not.toBeNull();
    expect(response.status(), 'HTTP status must be below 400').toBeLessThan(400);
    await expect(page.locator(targetSelector).first()).toBeVisible({ timeout: timeoutMs });
    await page.waitForTimeout(250);
    expect(browserErrors, browserErrors.join('\n')).toEqual([]);
});
