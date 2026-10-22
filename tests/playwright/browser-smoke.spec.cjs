const { test, expect } = require('@playwright/test');

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

    if (process.env.CODEX_VERIFY_MARKDOWN === '1' || process.env.CODEX_VERIFY_FILE_PREVIEW === '1' || process.env.CODEX_VERIFY_PREVIEW_SETTINGS === '1') {
        // Preview rendering is independent of the local repository's Git status.
        await page.route('**/api/codex/git/status', route => route.fulfill({
            json: {branch: 'markdown-fixture', changed_files_count: 0, changed_files: []},
        }));
    }

    const response = await page.goto(targetUrl, {
        waitUntil: 'domcontentloaded',
        timeout: timeoutMs,
    });
    expect(response, 'navigation must return an HTTP response').not.toBeNull();
    expect(response.status(), 'HTTP status must be below 400').toBeLessThan(400);
    await expect(page.locator(targetSelector).first()).toBeVisible({ timeout: timeoutMs });
    await page.waitForTimeout(250);
    if (process.env.CODEX_VERIFY_FONT_SETTINGS === '1') {
        await require('./font-settings.cjs').verifyFontSettings(page, expect);
    }
    if (process.env.CODEX_VERIFY_TYPOGRAPHY === '1') {
        await require('./typography.cjs').verifyTypography(page, expect);
    }
    if (process.env.CODEX_VERIFY_COMPOSE_MODES === '1') {
        await require('./compose-modes.cjs').verifyComposeModes(page, expect);
    }
    if (process.env.CODEX_VERIFY_WORKBENCH_CONTROLS === '1') {
        await require('./workbench-controls.cjs').verifyWorkbenchControls(page, expect);
    }
    if (process.env.CODEX_VERIFY_DIALOG_LAYOUT === '1') {
        await require('./dialog-layout.cjs').verifyDialogLayout(page, expect);
    }
    if (process.env.CODEX_VERIFY_TEAM_PROGRESS === '1') {
        await require('./team-progress.cjs').verifyTeamProgress(page, expect);
    }
    if (process.env.CODEX_VERIFY_USAGE_PANEL === '1') {
        await require('./usage-panel.cjs').verifyUsagePanel(page, expect, {
            isolated: process.env.CODEX_VERIFY_USAGE_PANEL_ISOLATED === '1',
        });
    }
    if (process.env.CODEX_VERIFY_CONTROL_GEOMETRY === '1') {
        await require('./control-geometry.cjs').verifyControlGeometry(page, expect);
    }
    if (process.env.CODEX_VERIFY_MARKDOWN === '1') {
        await require('./markdown.cjs').verifyMarkdown(page, expect);
    }
    if (process.env.CODEX_VERIFY_FILE_PREVIEW === '1') {
        await require('./file-preview.cjs').verifyFilePreview(page, expect);
    }
    if (process.env.CODEX_VERIFY_PREVIEW_SETTINGS === '1') {
        await require('../test_file_preview_settings_browser.cjs').verifyPreviewSettings(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_COMPANY_TIMING === '1') {
        await require('./company-timing.cjs').verifyCompanyTiming(page, expect);
    }
    if (process.env.CODEX_VERIFY_COMPANY_KEY_POOL === '1') {
        await require('./company-key-pool.cjs').verifyCompanyKeyPool(page, expect);
    }
    expect(browserErrors, browserErrors.join('\n')).toEqual([]);
});
