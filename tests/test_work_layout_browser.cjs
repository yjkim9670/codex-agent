// Render the real template without starting the Workbench server or collectors.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium, expect } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'codex-web-app/static/css/app.css'), 'utf8');
const python = process.env.CODEX_PYTHON_BIN || 'python3.14';
const render = internal => execFileSync(python, ['-c', `
import jinja2
env = jinja2.Environment(loader=jinja2.FileSystemLoader('codex-web-app/templates'), autoescape=True)
print(env.get_template('index.html').render(internal_multiuser_mode=${internal ? 'True' : 'False'}))
`], { cwd: root, encoding: 'utf8' });
function fn(name, next) {
    const start = source.indexOf(`function ${name}(`);
    assert.ok(start >= 0, name);
    const end = source.indexOf(`function ${next}(`, start);
    assert.ok(end > start, next);
    return source.slice(start, end);
}

(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        let cases = 0;
        for (const internal of [false, true]) {
            const html = render(internal).replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '')
                .replace(/<link\b[^>]*>/g, '');
            for (const width of [390, 820, 1440]) {
                await page.goto('about:blank');
                await page.setViewportSize({ width, height: 900 });
                await page.setContent(`<style>${css}</style>${html}`);
                // Work layout is already active before JS or preferences load.
                await expect(page.locator('.app')).toHaveClass(/is-work-mode/);
                await expect(page.locator('#codex-work-mode-toggle')).toHaveCount(0);
                await expect(page.locator('#codex-file-browser-open')).toHaveCount(0);
                if (width === 1440) {
                    await expect(page.locator('#codex-work-mode-preview')).toBeVisible();
                    await expect(page.locator('#codex-work-mode-divider')).toBeVisible();
                }
                // Exercise the real startup and media-change functions; file I/O,
                // terminal connections and unrelated panel internals are stubbed.
                await page.addScriptTag({ content: `
                    const WORK_MODE_CLASS = 'is-work-mode';
                    const CHAT_FULLSCREEN_CLASS = 'is-chat-fullscreen';
                    const WORK_MODE_MOBILE_VIEW_CHAT = 'chat';
                    const WORK_MODE_MOBILE_VIEW_LIST = 'list';
                    const WORK_MODE_PANEL_MODE_TERMINAL = 'terminal';
                    let workModeSplitRatio, workModeFileSplitRatio, workModeFileColumnWidths;
                    let workModePanelMode, workModeMobileView = 'chat', workModeMobileBrowseView = 'list';
                    let workModeFileRoot = 'workspace', workModeFilePath = '';
                    let workModeFileViewerFullscreen = false, workModePreviewFullscreen = false;
                    window.panelLoads = 0;
                    window.terminalLoads = 0;
                    window.savedPanelMode = 'file';
                    const isMobileLayout = () => innerWidth < 700;
                    const isFoldLayout = () => innerWidth >= 700 && innerWidth < 1000;
                    const isFoldInnerLayout = () => false;
                    const usesWorkModeSingleFilePane = isFoldLayout;
                    const isMobileSessionOverlayOpen = () => false;
                    const isFileBrowserOverlayOpen = () => false;
                    const isTerminalUiOpen = () => false;
                    const readWorkModeSplitPreference = () => 0.58;
                    const readWorkModeFileSplitPreference = () => 0.4;
                    const readWorkModeFileColumnsPreference = () => ({});
                    const readWorkModePanelModePreference = () => window.savedPanelMode;
                    const normalizeWorkModeMobileBrowseView = value => value;
                    const normalizeWorkModeMobileView = value => value;
                    const getTerminalLaunchContext = () => ({});
                    const openWorkModeTerminalPanelFromContext = async () => { window.terminalLoads++; };
                    const ensureWorkModeFilePanelContent = async () => { window.panelLoads++; };
                    const noop = () => {};
                    const initializeWorkModeFileViewState = noop, setWorkModeFilePathLabel = noop;
                    const applyWorkModeSplitRatio = noop, applyWorkModeFileSplitRatio = noop;
                    const applyWorkModeFileColumnWidths = noop, setWorkModeFileViewerFullscreen = noop;
                    const setWorkModePreviewFullscreen = noop, syncWorkModePanelModeState = noop;
                    const syncWorkModeFileHorizontalScrollMetrics = noop;
                    const setWorkModeMobileView = value => { workModeMobileView = value; };
                    ${fn('getWorkModeElements', 'getFilePanelElementsByPrefix')}
                    ${fn('isWorkModeEnabled', 'normalizeWorkModeSplitRatio')}
                    ${fn('activateWorkModeLayout', 'initializeWorkMode')}
                    ${fn('initializeWorkMode', 'handleWorkModeMediaChange')}
                    ${fn('handleWorkModeMediaChange', 'updateWorkModeSplitFromPointer')}
                    // Legacy browser storage is unavailable: startup must ignore it.
                    Object.defineProperty(window, 'localStorage', { configurable: true, get() {
                        throw new Error('layout must not read legacy preference');
                    }});
                    initializeWorkMode(isMobileLayout());
                ` });
                assert.equal(await page.evaluate(() => isWorkModeEnabled()), true);
                assert.equal(await page.evaluate(() => window.panelLoads), 1);
                await page.evaluate(() => {
                    window.savedPanelMode = 'terminal';
                    initializeWorkMode(isMobileLayout());
                    handleWorkModeMediaChange(true);
                    handleWorkModeMediaChange(false);
                });
                assert.equal(await page.evaluate(() => window.terminalLoads), 1);
                await expect(page.locator('.app')).toHaveClass(/is-work-mode/);
                await expect(page.locator('#codex-work-mode-preview')).toHaveAttribute('aria-hidden', 'false');
                cases++;
            }
        }
        assert.deepEqual(errors, []);
        console.log(`PASS: ${cases} personal/internal layout cases, first paint, startup without legacy storage, terminal restoration and media changes`);
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
