const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const source = fs.readFileSync(path.join(__dirname, '../codex-web-app/static/js/app.js'), 'utf8');
function slice(start, end) {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0, start);
    const finish = source.indexOf(end, offset);
    assert.ok(finish > offset, end);
    return source.slice(offset, finish);
}

(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        const cases = [
            { name: 'iPadOS desktop identity, landscape, trackpad', width: 1366, platform: 'MacIntel', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15', touch: 5, fine: true, mobile: true },
            { name: 'iPad portrait', width: 820, platform: 'iPad', userAgent: 'Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)', touch: 5, fine: false, mobile: true },
            { name: 'Android tablet, desktop layout', width: 1280, platform: 'Linux armv8l', userAgent: 'Mozilla/5.0 (Linux; Android 15)', touch: 5, fine: true, mobile: true },
            { name: 'Android phone', width: 412, platform: 'Linux armv8l', userAgent: 'Mozilla/5.0 (Linux; Android 15) Mobile', touch: 5, fine: false, mobile: true },
            { name: 'fold inner screen', width: 1000, platform: 'Linux armv8l', userAgent: '', touch: 5, fine: true, fold: true, mobile: true },
            { name: 'Mac desktop', width: 1440, platform: 'MacIntel', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X)', touch: 0, fine: true, mobile: false },
            { name: 'Windows touch laptop with mouse', width: 1440, platform: 'Win32', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', touch: 10, fine: true, mobile: false },
        ];
        for (const device of cases) {
            const page = await browser.newPage({ viewport: { width: device.width, height: 900 } });
            try {
                await page.setContent('<form id="codex-chat-form"><textarea id="codex-chat-input"></textarea><button type="submit">Submit</button></form>');
                await page.evaluate(device => {
                    for (const [key, value] of Object.entries({ platform: device.platform, userAgent: device.userAgent, maxTouchPoints: device.touch, userAgentData: undefined })) {
                        Object.defineProperty(navigator, key, { configurable: true, value });
                    }
                    window.testDevice = device;
                    window.submissions = 0;
                }, device);
                await page.addScriptTag({ content: `
                    const form = document.getElementById('codex-chat-form');
                    const input = document.getElementById('codex-chat-input');
                    const isCompactLayout = () => window.innerWidth < 600;
                    const isFoldInnerLayout = () => Boolean(testDevice.fold);
                    const mediaQueryMatches = query => query === '(any-pointer: fine)' ? testDevice.fine : !testDevice.fine;
                    const cyclePlanModeFromKeyboardEvent = () => false;
                    const syncActiveSessionControls = () => {};
                    const handleSubmit = event => { event?.preventDefault(); window.submissions++; };
                    ${slice('function isLikelyVirtualKeyboardEnvironment()', 'function isEditableElement(')}
                    ${slice('    if (form) {\n        form.addEventListener(\'submit\', handleSubmit);', '    sessionStatusFilterButtons.forEach')}
                    ${slice("    if (input) {\n        input.addEventListener('keydown'", '    if (imageAttachBtn && imageInput)')}
                ` });
                const input = page.locator('textarea');
                await input.fill('first');
                await input.press('Enter');
                assert.equal(await page.evaluate(() => submissions), device.mobile ? 0 : 1, device.name);
                assert.equal(await input.inputValue(), device.mobile ? 'first\n' : 'first', device.name);
                await input.fill('first');
                await input.press('Shift+Enter');
                assert.equal(await input.inputValue(), 'first\n', device.name);
                const baseline = await page.evaluate(() => submissions);
                for (const ime of [{ isComposing: true }, { keyCode: 229 }]) {
                    await input.dispatchEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...ime });
                    assert.equal(await page.evaluate(() => submissions), baseline, `${device.name}: IME`);
                }
                if (device.mobile) {
                    for (const key of ['Control+Enter', 'Meta+Enter']) await input.press(key);
                    assert.equal(await page.evaluate(() => submissions), 0, `${device.name}: hardware modifiers`);
                }
                await page.getByRole('button', { name: 'Submit' }).click();
                assert.equal(await page.evaluate(() => submissions), baseline + 1, `${device.name}: Submit`);
                console.log(`PASS: ${device.name}`);
            } finally {
                await page.close();
            }
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
