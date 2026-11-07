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

    if (process.env.CODEX_VERIFY_MARKDOWN === '1' || process.env.CODEX_VERIFY_FILE_PREVIEW === '1' || process.env.CODEX_VERIFY_IMAGE_PREVIEW === '1' || process.env.CODEX_VERIFY_PREVIEW_SETTINGS === '1') {
        // Preview rendering is independent of the local repository's Git status.
        await page.route('**/api/codex/git/status', route => route.fulfill({
            json: {branch: 'markdown-fixture', changed_files_count: 0, changed_files: []},
        }));
    }

    if (process.env.CODEX_VERIFY_BLOG === '1') {
        await require('./blog.cjs').setupBlog(page);
    }

    if (process.env.CODEX_VERIFY_CHAT_SCROLL === '1') {
        await require('./chat-scroll.cjs').setupChatScroll(page);
    }

    // Watch before navigation: a startup exception can leave the HTML shell
    // visible while preventing every data request from being sent.
    const startupResponses = process.env.CODEX_VERIFY_STARTUP === '1'
        ? Promise.all(['/api/codex/files/list', '/api/codex/settings', '/api/codex/sessions'].map(path =>
            page.waitForResponse(response => new URL(response.url()).pathname === path,
                { timeout: timeoutMs })))
        : null;

    const response = await page.goto(targetUrl, {
        waitUntil: 'domcontentloaded',
        timeout: timeoutMs,
    });
    expect(response, 'navigation must return an HTTP response').not.toBeNull();
    expect(response.status(), 'HTTP status must be below 400').toBeLessThan(400);
    await expect(page.locator(targetSelector).first()).toBeVisible({ timeout: timeoutMs });
    await page.waitForTimeout(250);
    if (process.env.CODEX_VERIFY_PROMPT_CONTROLS === '1') {
        await require('../test_prompt_controls_browser.cjs').verifyPromptControls(page, expect);
    }
    if (process.env.CODEX_VERIFY_USAGE_BLOG_STATUS === '1') {
        await expect(page.locator('#calibration-status')).toContainText('5시간:');
        await expect(page.locator('#calibration-status')).toContainText('24시간 이상 경과');
        await expect(page.locator('#calibration-status')).toContainText('기간 내 대기 7건');
        await expect(page.locator('#calibration-status')).toContainText('주간: 없음');
        await page.goto(new URL('/blog', targetUrl).href);
        await page.locator('.manage-link').click();
        await expect(page.locator('#automatic-status')).toBeVisible();
        await expect(page.locator('#automatic-status')).toContainText('당일 예산 소진');
        await expect(page.locator('#automatic-status')).toContainText('5시간 사용률 0%');
        await expect(page.locator('#budget-status')).toContainText('478,809 / 300,000토큰');
        await expect(page.locator('#budget-status')).toContainText('178,809토큰 초과');
        await expect(page.locator('#budget-status')).toContainText('즉시 실행은 간격·일일 예산 검사를 건너뜁니다');
    }
    if (startupResponses) {
        const responses = await startupResponses;
        for (const response of responses) expect(response.status()).toBe(200);
        // Chat responses may be encrypted on the wire. Check the application's
        // decoded state and rendered list after initialization completes.
        await expect(page.locator('#codex-session-storage')).not.toContainText('확인 중');
        await expect(page.locator('#codex-work-mode-file-meta')).not.toContainText('불러오는 중');
        await expect.poll(() => page.locator('#codex-model-select option[value]:not([value=""])').count())
            .toBeGreaterThan(0);
        await expect(page.locator('#codex-chat-status')).toHaveText('Idle');
        expect(await page.evaluate(() => state.settings.loaded)).toBe(true);
        const sessionCount = await page.evaluate(() => state.sessions.length);
        await expect(page.locator('#codex-session-list .session-item')).toHaveCount(sessionCount);
    }
    if (process.env.CODEX_VERIFY_RESOURCE_USAGE === '1') {
        await require('./resource-usage.cjs').verifyResourceUsage(page, expect);
    }
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
    if (process.env.CODEX_VERIFY_IMAGE_PREVIEW === '1') {
        await require('./image-preview.cjs').verifyImagePreview(page, expect);
    }
    if (process.env.CODEX_VERIFY_PREVIEW_SETTINGS === '1') {
        await require('../test_file_preview_settings_browser.cjs').verifyPreviewSettings(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_COMPANY_MODELS === '1') {
        await require('./company-models.cjs').verifyCompanyModels(page, expect);
    }
    if (process.env.CODEX_VERIFY_COMPANY_TIMING === '1') {
        await require('./company-timing.cjs').verifyCompanyTiming(page, expect);
    }
    if (process.env.CODEX_VERIFY_COMPANY_KEY_POOL === '1') {
        await require('./company-key-pool.cjs').verifyCompanyKeyPool(page, expect);
    }
    if (process.env.CODEX_VERIFY_METADATA_SYNC === '1') {
        await require('./metadata-sync.cjs').verifyMetadataSync(page, expect);
    }
    if (process.env.CODEX_VERIFY_CONVERSATION_SIDEBAR === '1') {
        test.setTimeout(60_000);
        await require('../test_conversation_sidebar_browser.cjs').verifyConversationSidebar(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_CHAT_LIMIT_RESET === '1') {
        await require('./chat-limit-reset.cjs').verifyChatLimitReset(page, expect);
    }
    if (process.env.CODEX_VERIFY_CONVERSATION_FILES === '1') {
        await require('../test_conversation_files_browser.cjs').verifyConversationFiles(page, expect);
    }
    if (process.env.CODEX_VERIFY_CONVERSATION_RESPONSIVE === '1') {
        test.setTimeout(300_000);
        await require('../test_conversation_responsive_browser.cjs').verifyResponsiveConversation(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_CONVERSATION_METADATA === '1') {
        test.setTimeout(60_000);
        await require('../test_conversation_metadata_browser.cjs').verifyConversationMetadata(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_CONVERSATION === '1') {
        test.setTimeout(120_000);
        await require('../test_conversation_browser.cjs').verifyConversation(page.context().browser(), targetUrl);
    }
    if (process.env.CODEX_VERIFY_BLOG === '1') {
        await require('./blog.cjs').verifyBlog(page, expect);
    }
    if (process.env.CODEX_VERIFY_CHAT_SCROLL === '1') {
        test.setTimeout(60_000);
        await require('./chat-scroll.cjs').verifyChatScroll(page, expect);
    }
    expect(browserErrors, browserErrors.join('\n')).toEqual([]);
    if (process.env.CODEX_VERIFY_CONVERSATION_VOICE === '1') {
        test.setTimeout(90_000);
        await require('../test_conversation_voice_browser.cjs').verifyConversationVoice(page, expect);
        expect(browserErrors, browserErrors.join('\n')).toEqual([]);
    }
    if (process.env.CODEX_VERIFY_VOICE === '1') {
        test.setTimeout(90_000);
        await require('../test_voice_browser.cjs').verifyVoice(page, expect);
        expect(browserErrors, browserErrors.join('\n')).toEqual([]);
    }
});
