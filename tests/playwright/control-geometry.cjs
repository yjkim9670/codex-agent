// Production DOM/CSS: label alignment and keyboard-resized touch targets.
async function verifyControlGeometry(page, expect) {
    await page.waitForTimeout(1500);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(150);
    await page.evaluate(() => document.fonts.ready);
    for (const mode of ['off', 'plan', 'plan_and_execute', 'secondary', 'team']) {
        await page.evaluate(mode => setPlanModeToggleState(mode), mode);
        const results = await page.evaluate(() => [...document.querySelectorAll(
            '#codex-plan-mode-toggle .control-label, .sessions .session-status-filter .control-label'
        )].map(label => {
            const r = label.getBoundingClientRect(), parent = label.parentElement.getBoundingClientRect();
            return { text: label.textContent, height: r.height, offset: Math.abs((r.top + r.bottom - parent.top - parent.bottom) / 2) };
        }));
        expect(results.length).toBeGreaterThanOrEqual(5);
        for (const result of results) {
            expect(result.height, result.text).toBeGreaterThan(0);
            expect(result.offset, JSON.stringify(result)).toBeLessThanOrEqual(1);
        }
    }
    let checks = 0;
    for (const [width, mode] of [[390, 'mobile'], [600, 'fold-inner'], [820, 'fold-inner'], [932, 'fold-inner']]) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForTimeout(150);
        for (const scale of [0.85, 1]) {
            await page.evaluate(({mode, scale}) => {
                document.documentElement.dataset.viewMode = mode;
                document.querySelector('.app').classList.add('is-work-mode');
                document.documentElement.style.setProperty('--ui-scale', scale);
                document.querySelector('#codex-chat-input').blur();
                Object.defineProperty(visualViewport, 'height', { configurable: true, get: () => 800 });
                Object.defineProperty(visualViewport, 'offsetTop', { configurable: true, get: () => 0 });
                applyMobileViewportHeight();
                rememberStableMobileViewportHeight();
                document.querySelector('#codex-chat-input').focus();
            }, { mode, scale });
            for (const height of [300, 175, 120]) {
                const result = await page.evaluate(height => {
                    Object.defineProperty(visualViewport, 'height', { configurable: true, get: () => height });
                    applyMobileViewportHeight(); syncMobileKeyboardState(true);
                    const button = document.querySelector('#codex-chat-send');
                    const r = button.getBoundingClientRect(), form = button.closest('form').getBoundingClientRect();
                    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                    return { zoom: getComputedStyle(document.body).zoom, view: document.documentElement.dataset.viewMode, cssHeight: getComputedStyle(button).height, height: r.height, bottom: r.bottom, formBottom: form.bottom,
                        hit: hit === button || button.contains(hit), keyboard: document.querySelector('.app').classList.contains('is-mobile-keyboard-open') };
                }, height);
                const context = JSON.stringify({width, mode, scale, viewport: height, result});
                expect(result.keyboard, context).toBe(true);
                expect(result.height, context).toBeGreaterThanOrEqual((width < 600 ? 52 : 44) * scale - 1);
                expect(result.bottom, context).toBeLessThanOrEqual(result.formBottom + 1);
                expect(result.hit, context).toBe(true);
                checks++;
            }
        }
    }
    console.log(`Verified five mode labels, session filter labels/counts, and ${checks} keyboard button layouts.`);
}
module.exports = {verifyControlGeometry};
