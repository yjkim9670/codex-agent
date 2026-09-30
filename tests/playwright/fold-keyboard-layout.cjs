// Geometry regression check; viewport metrics simulate Android keyboard resize
// and panning. A real Samsung keyboard still needs a device check.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        for (const scale of [0.85, 1]) {
            for (const width of [932, 820]) {
                const page = await browser.newPage({ viewport: { width, height: 568 }, isMobile: true, hasTouch: true });
                await page.addInitScript(() => localStorage.setItem('codex-ui-view-mode', 'fold-inner'));
                await page.goto(process.env.CODEX_VERIFY_URL || 'http://127.0.0.1:3004');
                await page.waitForSelector('#codex-chat-input');
                await page.waitForTimeout(1500);
                await page.evaluate(scale => {
                    document.documentElement.dataset.viewMode = 'fold-inner';
                    document.documentElement.style.setProperty('--ui-scale', scale);
                    document.querySelector('.app').classList.add('is-work-mode');
                    rememberStableMobileViewportHeight();
                    document.querySelector('#codex-chat-input').focus();
                }, scale);
                for (const height of [260, 175, 120]) {
                    for (const offsetTop of [0, 60, 130]) {
                        const result = await page.evaluate(({ height, offsetTop }) => {
                            Object.defineProperty(visualViewport, 'height', { configurable: true, get: () => height });
                            Object.defineProperty(visualViewport, 'offsetTop', { configurable: true, get: () => offsetTop });
                            applyMobileViewportHeight();
                            syncMobileKeyboardState(true);
                            const rect = selector => {
                                const r = document.querySelector(selector).getBoundingClientRect();
                                return { top: r.top, bottom: r.bottom, height: r.height };
                            };
                            const input = document.querySelector('#codex-chat-input');
                            const r = input.getBoundingClientRect();
                            // elementFromPoint uses layout viewport coordinates.
                            const hit = document.elementFromPoint(r.left + 20, r.bottom - 3);
                            return { app: rect('.app'), chat: rect('.chat'), prompt: rect('.chat-input'), input: rect('#codex-chat-input'), hit: hit === input, keyboard: document.querySelector('.app').classList.contains('is-mobile-keyboard-open'), split: getComputedStyle(document.querySelector('.layout')).flexDirection };
                        }, { height, offsetTop });
                        const context = JSON.stringify({ scale, width, height, offsetTop, result });
                        assert(result.keyboard, context);
                        assert(Math.abs(result.app.top - offsetTop) < 2, context);
                        assert(Math.abs(result.app.bottom - (height + offsetTop)) < 2, context);
                        assert(result.prompt.bottom <= result.chat.bottom + 1, context);
                        assert(result.input.bottom <= result.app.bottom + 1, context);
                        assert(result.hit, context);
                        assert.equal(result.split, 'row', context);
                    }
                }
                const closed = await page.evaluate(() => {
                    document.querySelector('#codex-chat-input').blur();
                    Object.defineProperty(visualViewport, 'height', { configurable: true, get: () => 568 });
                    Object.defineProperty(visualViewport, 'offsetTop', { configurable: true, get: () => 0 });
                    applyMobileViewportHeight(); syncMobileKeyboardState(true);
                    const app = document.querySelector('.app');
                    return { keyboard: app.classList.contains('is-mobile-keyboard-open'), position: getComputedStyle(app).position, bottom: app.getBoundingClientRect().bottom };
                });
                assert(!closed.keyboard && closed.position === 'relative' && Math.abs(closed.bottom - 568) < 2, JSON.stringify(closed));
                await page.close();
            }
        }
        console.log('PASS: 36 Fold keyboard cases (85%/100%, 932/820px, resize/pan), composer hit testing and keyboard close');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
