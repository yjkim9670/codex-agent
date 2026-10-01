// Run through verify_browser_ui.py with CODEX_VERIFY_DIALOG_LAYOUT=1.
// Synthetic file/history rows exercise layout without running Git actions.
exports.verifyDialogLayout = async (page, expect) => {
    let checks = 0;
    for (const viewport of [
        { width: 360, height: 480 },
        { width: 740, height: 360 },
        { width: 1280, height: 900 },
    ]) {
        await page.setViewportSize(viewport);
        for (const scale of [0.8, 1.1]) {
            for (const keyboard of [false, true]) {
                const height = keyboard ? 220 : viewport.height;
                const top = keyboard ? 40 : 0;
                for (const kind of ['ui-settings', 'branch', 'sync']) {
                    for (const fullscreen of (kind === 'ui-settings' ? [false] : [false, true])) {
                        const result = await page.evaluate(({ kind, scale, height, top, fullscreen }) => {
                            Object.defineProperty(visualViewport, 'height', { configurable: true, get: () => height });
                            Object.defineProperty(visualViewport, 'offsetTop', { configurable: true, get: () => top });
                            document.documentElement.style.setProperty('--ui-scale', scale);
                            applyMobileViewportHeight();
                            document.querySelectorAll('.ui-settings-overlay, .branch-overlay, .sync-overlay').forEach(el => {
                                el.classList.remove('is-visible', 'is-fullscreen');
                            });
                            const overlay = document.querySelector(`.${kind}-overlay`);
                            overlay.classList.add('is-visible');
                            overlay.classList.toggle('is-fullscreen', fullscreen);
                            const prefix = kind === 'ui-settings' ? 'ui-settings' : `${kind}-overlay`;
                            const body = overlay.querySelector(`.${prefix}-body`);
                            overlay.querySelectorAll('ul').forEach(list => {
                                list.classList.remove('is-hidden');
                                list.replaceChildren(...Array.from({ length: 25 }, (_, i) => {
                                    const row = document.createElement('li');
                                    row.textContent = `${i}: long/path/`.repeat(8);
                                    return row;
                                }));
                            });
                            overlay.querySelectorAll('textarea').forEach(input => {
                                input.value = 'Long commit message\n'.repeat(20);
                            });
                            overlay.querySelectorAll(`[class$="-subtitle"]`).forEach(el => {
                                el.textContent = 'long-branch-name/'.repeat(10);
                            });
                            const card = overlay.querySelector('[role="dialog"]');
                            const rect = el => {
                                const r = el.getBoundingClientRect();
                                return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height };
                            };
                            body.scrollTop = body.scrollHeight;
                            const last = body.lastElementChild;
                            return {
                                card: rect(card), header: rect(overlay.querySelector(`.${prefix}-header`)),
                                footer: rect(overlay.querySelector(`.${prefix}-footer`)),
                                body: rect(body), last: rect(last),
                                horizontalOverflow: body.scrollWidth - body.clientWidth,
                            };
                        }, { kind, scale, height, top, fullscreen });
                        const label = JSON.stringify({ viewport, kind, scale, height, top, fullscreen, result });
                        expect(result.card.top, label).toBeGreaterThanOrEqual(top - 1);
                        expect(result.card.bottom, label).toBeLessThanOrEqual(top + height + 1);
                        expect(result.card.left, label).toBeGreaterThanOrEqual(-1);
                        expect(result.card.right, label).toBeLessThanOrEqual(viewport.width + 1);
                        expect(result.body.height, label).toBeGreaterThan(0);
                        expect(result.header.bottom, label).toBeLessThanOrEqual(result.body.top + 1);
                        expect(result.footer.top, label).toBeGreaterThanOrEqual(result.body.bottom - 1);
                        expect(result.last.bottom, label).toBeLessThanOrEqual(result.body.bottom + 1);
                        expect(result.horizontalOverflow, label).toBeLessThanOrEqual(1);
                        checks++;
                    }
                }
            }
        }
    }
    console.log(`Verified ${checks} dialog layout cases: narrow/landscape/desktop, zoom, keyboard pan, fullscreen and scroll reachability.`);
};
