// Loaded by the deterministic runner; exercise real CSS with overflowing text.
exports.verifyPromptControls = async (page, expect) => {
    const input = page.locator('#codex-chat-input');
    const original = await input.inputValue();
    for (const viewport of [
        { width: 360, height: 780 },
        { width: 412, height: 420 },
        { width: 599, height: 780 },
        { width: 768, height: 900 },
    ]) {
        await page.setViewportSize(viewport);
        // Workbench defaults to its file pane on narrow screens. Select the
        // actual chat view before exercising the composer.
        await page.evaluate(() => setWorkModeMobileView('chat'));
        await expect(input).toBeVisible();
        await input.fill(Array.from({ length: 30 }, (_, i) => `${i} 한글 입력과 English text `.repeat(6)).join('\n'));
        for (const fraction of [0, 0.5, 1]) {
            const geometry = await input.evaluate((el, fraction) => {
                el.scrollTop = (el.scrollHeight - el.clientHeight) * fraction;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                // UI scale uses CSS zoom; compare all values in rendered pixels.
                const scale = rect.width / el.offsetWidth;
                return {
                    textRight: rect.right - (parseFloat(style.paddingRight) + parseFloat(style.borderRightWidth)) * scale,
                    overflow: el.scrollHeight > el.clientHeight,
                    scrollTop: el.scrollTop,
                    buttons: ['voice-start', 'codex-chat-compose-tools-toggle'].map(id => {
                        const button = document.getElementById(id);
                        const box = button.getBoundingClientRect();
                        return { id, visible: box.width > 0 && box.height > 0, left: box.left };
                    }),
                };
            }, fraction);
            expect(geometry.overflow).toBe(true);
            if (fraction > 0) expect(geometry.scrollTop).toBeGreaterThan(0);
            for (const button of geometry.buttons.filter(button => button.visible)) {
                expect(geometry.textRight, `text clears ${button.id} at ${viewport.width}px, scroll ${fraction}`).toBeLessThan(button.left - 2);
            }
            expect(geometry.buttons[0].visible).toBe(true);
            expect(geometry.buttons[1].visible).toBe(viewport.width <= 599);
        }
    }
    await input.fill(original);
};
