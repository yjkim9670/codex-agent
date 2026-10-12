// Exercises the real composer without sending prompts or starting agents.
exports.verifyComposeModes = async (page, expect) => {
    const desktop = page.locator('#codex-plan-mode-toggle');
    const mobile = page.locator('[data-chat-compose-action="plan"]');
    const menu = page.locator('#codex-compose-mode-menu');
    const input = page.locator('#codex-chat-input');
    const modes = [
        ['off', 'Work', 'main', false], ['plan', 'Plan', 'main', true],
        ['plan_and_execute', 'Plan+', 'main', true], ['secondary', 'Sec', 'secondary', false],
        ['team', 'Team', 'main', false]
    ];
    for (const [width, height] of [[1280, 800], [600, 360], [360, 360]]) {
        await page.setViewportSize({ width, height });
        await page.evaluate(() => { closeComposeModeMenu(); setPlanModeToggleState('off'); });
        await input.fill('유지할 입력');
        const trigger = width < 600 ? mobile : desktop;
        const openMenu = async () => {
            if (width < 600) await page.locator('#codex-chat-compose-tools-toggle').click();
            await trigger.click();
            await expect(menu).toBeVisible();
        };
        for (const [mode, label, role, plan] of modes) {
            await openMenu();
            await expect(menu.locator('[role="menuitemradio"]')).toHaveCount(5);
            await expect(menu.locator('[aria-checked="true"]')).toHaveCount(1);
            const bounds = await menu.evaluate(el => {
                const r = el.getBoundingClientRect();
                return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, scroll: el.scrollWidth, client: el.clientWidth };
            });
            expect(bounds.left).toBeGreaterThanOrEqual(-1);
            expect(bounds.right).toBeLessThanOrEqual(width + 1);
            expect(bounds.top).toBeGreaterThanOrEqual(-1);
            expect(bounds.bottom).toBeLessThanOrEqual(height + 1);
            expect(bounds.scroll).toBeLessThanOrEqual(bounds.client + 1);
            await menu.locator(`[data-compose-mode="${mode}"]`).click();
            await expect(menu).toBeHidden();
            await expect(desktop).toHaveText(label);
            await expect(mobile).toHaveText(label);
            await expect(menu.locator(`[data-compose-mode="${mode}"]`)).toHaveAttribute('aria-checked', 'true');
            expect(await page.evaluate(() => getComposeModelRole())).toBe(role);
            expect(await page.evaluate(() => shouldUsePlanModeForRequest())).toBe(plan);
            await expect(input).toBeFocused();
            for (const nextLabel of [mode === 'off' ? 'Plan' : 'Work', mode === 'off' ? 'Work' : 'Plan']) {
                await input.press('Shift+Tab');
                await expect(desktop).toHaveText(nextLabel);
                await expect(mobile).toHaveText(nextLabel);
                await expect(input).toBeFocused();
                await expect(input).toHaveValue('유지할 입력');
            }
        }
        await openMenu();
        await page.setViewportSize({ width, height: height + 40 });
        await expect(menu).toBeVisible();
        await page.setViewportSize({ width, height });
        await expect(menu).toBeVisible();
        await page.keyboard.press('End');
        await expect(menu.locator('[data-compose-mode="team"]')).toBeFocused();
        await page.keyboard.press('Home');
        await expect(menu.locator('[data-compose-mode="off"]')).toBeFocused();
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Enter');
        await expect(desktop).toHaveText('Plan');
        await expect(menu).toBeHidden();
        await openMenu();
        await page.keyboard.press('Escape');
        await expect(menu).toBeHidden();
        await expect(trigger).toBeFocused();
        await openMenu();
        await input.click();
        await expect(menu).toBeHidden();
    }
    await page.evaluate(() => setPlanModeToggleState('off'));
    await input.fill('');
};
