// Exercise production settings and rotation handlers without a running server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium, expect } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
const template = fs.readFileSync(path.join(root, 'codex-web-app/templates/index.html'), 'utf8');
const settings = source.slice(source.indexOf("    const UI_SCALE_STORAGE_KEY ="), source.indexOf('    if (form) {', source.indexOf("    const UI_SCALE_STORAGE_KEY =")));
const resize = source.slice(source.indexOf('    const handleWindowLayoutResize ='), source.indexOf("    window.addEventListener('pagehide', flushPersistWorkModeFileViewState)"));
const markup = template.slice(template.indexOf('                <label class="ui-scale-setting"'), template.indexOf('</label>', template.indexOf('                <label class="ui-scale-setting"')) + 8);
const setup = `
    const UI_VIEW_MODE_AUTO = 'auto';
    const UI_VIEW_MODES = ['auto', 'desktop', 'fold-cover', 'fold-inner', 'mobile'];
    let uiViewMode = 'auto', workModeArrangement, workModeMobileView = 'chat', workModeMobileBrowseView;
    const WORK_MODE_MOBILE_VIEW_CHAT = 'chat';
    const normalizeUiViewMode = value => UI_VIEW_MODES.includes(value) ? value : 'auto';
    const UI_VIEW_MODE_STORAGE_KEY = 'codex-ui-view-mode';
    const detectUiViewMode = () => 'fold-inner';
    const resolveUiViewMode = () => uiViewMode === 'auto' ? detectUiViewMode() : uiViewMode;
    const isAndroidPlatform = () => window.testAndroid || false;
    const uiSettingsScaleInput = document.getElementById('codex-ui-scale-input');
    const uiSettingsScaleValue = document.getElementById('codex-ui-scale-value');
    const uiSettingsFontInputs = [], uiSettingsViewInputs = [];
    const uiSettingsOverlay = null, uiSettingsOpen = null, uiSettingsClose = null, uiSettingsDone = null;
    const uiSettingsReset = document.getElementById('reset'), uiSettingsViewDetected = null;
    const normalizeWorkModeArrangement = value => value || 'auto';
    const createRafThrottledHandler = handler => handler;
    const isCompactLayout = () => false, isMobileLayout = () => false;
    const isWorkModeEnabled = () => false, isTerminalUiOpen = () => false;
    const isFileBrowserOverlayOpen = () => false, isUsageHistoryOverlayOpen = () => false;
    const syncSessionsLayout = () => {}, setFileBrowserMobileView = () => {};
    const setFileBrowserViewerFullscreen = () => {}, handleWorkModeMediaChange = () => {};
    const syncCoverStreamMonitor = () => {}, syncTerminalExtraKeysState = () => {};
    const syncWorkModeFileHorizontalScrollMetrics = () => {};
    const fileBrowserMobileView = 'list', fileBrowserViewerFullscreen = false;
    const applyPreviewSettings = () => {}, refreshFileBrowserTextPreviews = () => {};
    const FILE_BROWSER_PREVIEW_SETTINGS_KEY = 'preview';
`;
(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 768, height: 1000 } });
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.route('http://scale.test/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: `${markup}<button id="reset">reset</button><script>${setup}${settings}${resize}</script>` }));
        const scale = page.locator('#codex-ui-scale-input');
        const label = page.locator('#codex-ui-scale-label');
        const check = async value => {
            await expect(scale).toHaveValue(String(value));
            await expect.poll(() => page.evaluate(() => document.documentElement.style.getPropertyValue('--ui-scale'))).toBe(String(value / 100));
        };
        const setScale = value => scale.fill(String(value));
        const portrait = () => page.setViewportSize({ width: 768, height: 1000 });
        const landscape = () => page.setViewportSize({ width: 1000, height: 768 });
        await page.goto('http://scale.test');
        await check(95);
        await expect(label).toContainText('세로');
        await landscape();
        await check(90);
        await expect(label).toContainText('가로');
        await setScale(85);
        await portrait();
        await check(95);
        await setScale(100);
        await landscape();
        await check(85);
        await page.reload();
        await check(85);
        await portrait();
        await check(100);
        // Forced inner mode must also switch preferences on rotation.
        await page.evaluate(() => applyUiViewMode('fold-inner'));
        await landscape();
        await check(85);
        await portrait();
        await check(100);
        // Keyboard-driven viewport changes must retain physical portrait scale on Android.
        await page.evaluate(() => {
            window.testAndroid = true;
            Object.defineProperty(screen.orientation, 'type', { configurable: true, value: 'portrait-primary' });
        });
        await page.setViewportSize({ width: 768, height: 420 });
        await check(100);
        // An orientation event independently refreshes the setting.
        await page.evaluate(() => {
            Object.defineProperty(screen.orientation, 'type', { configurable: true, value: 'landscape-primary' });
            screen.orientation.dispatchEvent(new Event('change'));
        });
        await check(85);
        await page.click('#reset');
        await check(90);
        await page.evaluate(() => { window.testAndroid = false; });
        await portrait();
        await check(95);
        // The old shared inner value is ignored; other surface settings survive.
        await page.evaluate(() => localStorage.setItem('codex-ui-scale-by-view-mode', JSON.stringify({ 'fold-inner': 110, desktop: 105, 'fold-cover': 80 })));
        await page.reload();
        await check(95);
        await landscape();
        await check(90);
        await page.evaluate(() => applyUiViewMode('desktop', { refresh: false }));
        await check(105);
        await page.evaluate(() => applyUiViewMode('fold-cover', { refresh: false }));
        await check(80);
        assert.deepEqual(errors, []);
        console.log('PASS: Fold orientation defaults, independent storage, reload, forced mode rotation, keyboard stability, reset and migration');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
