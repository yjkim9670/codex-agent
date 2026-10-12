async function verifyUsagePanel(page, expect, { isolated = false } = {}) {
    if (!isolated) {
    // Exercise the real apply handler with an intercepted PATCH; no settings are persisted.
    await page.waitForFunction(() => state.settings.loaded);
    await page.locator('#codex-controls-toggle').click();
    const settingsResponse = await page.request.get(new URL('/api/codex/settings', page.url()).href);
    const settingsFixture = await settingsResponse.json();
    let savedPayload;
    await page.route('**/api/codex/settings', async route => {
        if (route.request().method() !== 'PATCH') return route.continue();
        savedPayload = route.request().postDataJSON();
        await route.fulfill({json: {...settingsFixture, settings:{...settingsFixture.settings, ...savedPayload}}});
    });
    const expectedPayload = await page.evaluate(() => {
        const value = prefix => {
            const select = document.getElementById(prefix + '-select');
            const input = document.getElementById(prefix + '-input');
            return (select && !select.classList.contains('is-hidden') ? select.value : input?.value || '').trim();
        };
        return {model:value('codex-model'), reasoning_effort:value('codex-reasoning'), plan_mode_model:value('codex-plan-mode-model'), secondary_model:value('codex-secondary-model')};
    });
    await page.locator('#codex-model-apply').click();
    await expect(page.locator('#codex-model-status')).toHaveText('Saved');
    expect(savedPayload).toMatchObject(expectedPayload);
    await page.unroute('**/api/codex/settings');
    }
    const fs = require('node:fs');
    const path = require('node:path');
    const root = path.resolve(__dirname, '../..');
    const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
    const functions = ['formatCompactTokenCount', 'normalizeTokenUsageEntry', 'buildTokenUsageEntry', 'formatLimitUsage', 'buildUsageEntry', 'buildUsageAccount', 'updateUsageSummary', 'updateControlsModelSummary', 'setPlanModeToggleState', 'syncModelCardForBackend'].map(name => {
        const start = source.indexOf(`function ${name}(`);
        return source.slice(start, source.indexOf('\nfunction ', start + 1));
    }).join('\n');
    await page.route('**/static/fonts/**', route => route.fulfill({
        path: path.join(root, 'codex-web-app', new URL(route.request().url()).pathname),
        contentType: 'font/woff2'
    }));
    const template = fs.readFileSync(path.join(root, 'codex-web-app/templates/index.html'), 'utf8');
    const start = template.indexOf('<div class="chat-controls is-collapsed"');
    const end = template.indexOf('<form id="codex-chat-form"', start);
    const panel = template.slice(start, end).replace('chat-controls is-collapsed', 'chat-controls').replace(/{%[\s\S]*?%}/g, '').replace(/{{[\s\S]*?}}/g, '[]');
    await page.setContent(`<main style="padding:12px">${panel}</main>`);
    await page.addStyleTag({content: fs.readFileSync(path.join(root, 'codex-web-app/static/css/app.css'), 'utf8')});
    await page.addScriptTag({content: `(() => {
        const state = {settings: {loaded:true, usageLimitsEnabled:false, model:'very-long-main-model-name-for-layout', reasoningEffort:'high', planModeModel:'plan-model', planModeReasoningEffort:'medium', secondaryModel:'secondary-model', secondaryReasoningEffort:'low'}, accounts:{label:'Test account'}};
        const getActiveCodexAccount = () => state.accounts;
        const getActiveAgentBackend = () => 'dtgpt';
        const hasReasoningControlsForBackend = () => !document.querySelector('.model-card').classList.contains('is-no-reasoning');
        const formatReasoningStatus = (model, effort) => effort || 'default';
        const getPlanModeState = () => state.settings.planModeState || 'off';
        const normalizePlanModeState = value => value;
        const shouldUsePlanModeForRequest = value => value === 'plan' || value === 'plan-and-execute';
        const getComposeModelRole = value => value === 'secondary' ? 'secondary' : 'main';
        const PLAN_MODE_STATE_OFF = 'off', PLAN_MODE_STATE_PLAN_ONLY = 'plan', PLAN_MODE_STATE_SECONDARY = 'secondary', PLAN_MODE_STATE_TEAM = 'team', PLAN_MODE_STATE_PLAN_AND_EXECUTE = 'plan-and-execute';
        const normalizeUsedPercent = value => Number(value);
        const formatRemainingPercent = value => 100 - value;
        const formatResetTimestamp = value => value || '';
        const formatWeeklyUsageProjection = () => 'Pace 40% by reset';
        const isUsageKeepaliveHistoryOverlayOpen = () => false;
        const formatNumber = value => Number(value).toLocaleString('en-US');
        ${functions}
        window.usageFixture = {account_name:'Test account',five_hour:{used_percent:20,resets_at:'2026-10-13 01:00'},weekly:{used_percent:35,resets_at:'2026-10-19 01:00'},token_usage:{today:{input_tokens:1000000,cached_input_tokens:800000,output_tokens:234567,total_tokens:1234567,requests:32,date:'2026-10-12'},all_time:{input_tokens:2400000000,cached_input_tokens:1800000000,output_tokens:100000000,total_tokens:2500000000,requests:15000}}};
        window.updateUsageSummary = updateUsageSummary;
        window.fixtureState = state;
        window.setPlanModeToggleState = setPlanModeToggleState;
        window.updateControlsModelSummary = updateControlsModelSummary;
        document.getElementById('codex-account-select').innerHTML = '<option value="a">Test account</option><option value="b">Other account</option>';
        document.getElementById('codex-account-select').disabled = false;
        document.getElementById('codex-model-input').value = state.settings.model;
        updateUsageSummary(window.usageFixture);
        updateControlsModelSummary();
    })();`});
    const today = page.locator('.usage-token-entry').first();
    const all = page.locator('.usage-token-entry').nth(1);
    await expect(today.locator('summary')).toHaveText('Today1.2M tok32 req');
    await expect(all.locator('summary')).toHaveText('All2.5B tok15K req');
    await expect(today.locator('dl')).toBeHidden();
    await today.locator('summary').click();
    await expect(today.locator('dl')).toBeVisible();
    await expect(today.locator('dd').first()).toHaveText('1,234,567');
    await expect(today.locator('dd').nth(1)).toHaveText('200,000');
    await page.evaluate(() => updateUsageSummary(window.usageFixture));
    await expect(today.locator('dl')).toBeVisible();
    await all.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(all.locator('dl')).toBeVisible();
    await page.keyboard.press('Space');
    await expect(all.locator('dl')).toBeHidden();
    await expect(page.locator('.usage-account')).toHaveCount(0);
    await page.locator('#codex-account-select').selectOption('b');
    await expect(page.locator('#codex-account-select')).toHaveValue('b');
    await page.evaluate(() => {
        fixtureState.settings.usageLimitsEnabled = true;
        updateUsageSummary(window.usageFixture);
    });
    const limit = page.locator('.usage-limit-entry').first();
    await expect(limit.locator('summary')).toHaveText('5h80% left');
    await expect(limit.locator('.usage-reset').first()).toBeHidden();
    await limit.locator('summary').click();
    await expect(limit.locator('.usage-reset').first()).toBeVisible();
    await page.evaluate(() => updateUsageSummary(window.usageFixture));
    await expect(limit.locator('.usage-reset').first()).toBeVisible();
    await page.evaluate(() => setPlanModeToggleState('plan'));
    await expect(page.locator('#codex-controls-summary')).toHaveText('Plan · plan-model · medium');
    await page.evaluate(() => setPlanModeToggleState('secondary'));
    await expect(page.locator('#codex-controls-summary > span')).toHaveText(['Sec · secondary-model · low', 'Plan · plan-model · medium']);
    await page.evaluate(() => setPlanModeToggleState('off'));
    await expect(page.locator('#codex-controls-summary > span')).toHaveText(['메인 · very-long-main-model-name-for-layout · high', 'Plan · plan-model · medium']);
    await page.evaluate(() => document.querySelectorAll('.usage-entry[open]').forEach(entry => entry.open = false));
    for (const width of [320, 375, 390, 430, 768, 900, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        const geometry = await page.evaluate(() => {
            const body = document.getElementById('codex-controls-body');
            body.scrollTop = 0;
            const usage = body.querySelector('.usage-card').getBoundingClientRect();
            const model = body.querySelector('.model-card').getBoundingClientRect();
            const header = document.querySelector('.chat-controls-header').getBoundingClientRect();
            const controls = document.getElementById('codex-controls').getBoundingClientRect();
            return {
                stacked: getComputedStyle(body).gridTemplateColumns.split(' ').length === 1,
                modelRight: model.right, usageRight: usage.right,
                headerRight: header.right, controlsRight: controls.right - parseFloat(getComputedStyle(document.getElementById('codex-controls')).borderRightWidth),
                contentWidths: [...body.querySelector('.model-card').children].map(el => el.getBoundingClientRect().width),
                usageTop: usage.top, modelTop: model.top, modelWidth: model.width, usageWidth: usage.width,
                usageBackground: getComputedStyle(body.querySelector('.usage-card')).backgroundColor,
                modelBackground: getComputedStyle(body.querySelector('.model-card')).backgroundColor,
                pairs: ['.usage-token-entry', '.usage-limit-entry'].map(selector => {
                    const [first, second] = [...body.querySelectorAll(selector)].map(el => el.getBoundingClientRect());
                    return {firstTop:first.top, secondTop:second.top, firstRight:first.right, secondLeft:second.left};
                }),
                overflows: [...document.querySelectorAll('#codex-controls, .usage-token-summary, .model-setting-row')].filter(el => el.scrollWidth > el.clientWidth + 1).map(el => el.className),
                rows: [...document.querySelectorAll('.model-setting-row')].map(row => {
                    const model = row.querySelector('.model-field').getBoundingClientRect();
                    const effort = row.querySelector('.model-field-reasoning').getBoundingClientRect();
                    return {modelWidth:model.width, effortWidth:effort.width, modelTop:model.top, effortTop:effort.top};
                })
            };
        });
        expect(geometry.overflows, `overflow at ${width}px`).toEqual([]);
        expect(Math.abs(geometry.headerRight - geometry.controlsRight), `header background at ${width}px`).toBeLessThanOrEqual(1);
        expect(Math.max(...geometry.contentWidths)).toBeLessThanOrEqual(306);
        if (geometry.stacked) {
            expect(Math.abs(geometry.modelRight - geometry.usageRight), `settings background at ${width}px`).toBeLessThanOrEqual(1);
        } else {
            expect(geometry.modelWidth).toBeLessThanOrEqual(320);
        }
        if (width >= 768) {
            expect(geometry.usageTop).toBe(geometry.modelTop);
            expect(geometry.usageWidth).toBeGreaterThan(geometry.modelWidth);
        }
        expect(geometry.usageBackground).not.toBe(geometry.modelBackground);
        for (const pair of geometry.pairs) {
            expect(pair.firstTop).toBe(pair.secondTop);
            expect(pair.firstRight).toBeLessThan(pair.secondLeft);
        }
        if (width <= 430) expect(geometry.usageTop).toBeLessThan(geometry.modelTop);
        for (const row of geometry.rows) {
            expect(row.modelWidth).toBeGreaterThan(row.effortWidth);
            expect(row.modelTop).toBe(row.effortTop);
        }
        await page.locator('#codex-model-apply').scrollIntoViewIfNeeded();
        await expect(page.locator('#codex-model-apply')).toBeInViewport();
        await page.evaluate(() => document.getElementById('codex-controls').classList.add('is-collapsed'));
        await expect(page.locator('#codex-controls-body')).toBeHidden();
        await expect(page.locator('#codex-controls-summary > span').last()).toBeVisible();
        await expect(page.locator('#codex-controls-summary > span').last()).toHaveText('Plan · plan-model · medium');
        const summaryFits = await page.locator('#codex-controls-summary').evaluate(el => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1);
        expect(summaryFits, `collapsed summary at ${width}px`).toBe(true);
        const collapsedGeometry = await page.locator('#codex-controls').evaluate(el => {
            const panel = el.getBoundingClientRect();
            const headerElement = el.querySelector('.chat-controls-header');
            const header = headerElement.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
                height: headerElement.offsetHeight,
                topGap: header.top - panel.top - parseFloat(style.borderTopWidth),
                bottomGap: panel.bottom - header.bottom - parseFloat(style.borderBottomWidth),
            };
        });
        expect(collapsedGeometry.height, `collapsed height at ${width}px`).toBeGreaterThanOrEqual(36);
        if (width >= 768) {
            expect(collapsedGeometry.height, `compact collapsed height at ${width}px`).toBeLessThanOrEqual(36);
        }
        expect(Math.abs(collapsedGeometry.topGap), `collapsed top at ${width}px`).toBeLessThanOrEqual(1);
        expect(Math.abs(collapsedGeometry.bottomGap), `collapsed bottom at ${width}px`).toBeLessThanOrEqual(1);
        await page.evaluate(() => document.getElementById('codex-controls').classList.remove('is-collapsed'));
    }
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
    const darkSurfaces = await page.evaluate(() => ['.usage-card', '.model-card'].map(selector => getComputedStyle(document.querySelector(selector)).backgroundColor));
    expect(darkSurfaces[0]).not.toBe(darkSurfaces[1]);
    await page.evaluate(() => {
        document.querySelector('.model-card').classList.add('is-no-reasoning');
        updateControlsModelSummary();
    });
    await expect(page.locator('.model-effort-heading')).toBeHidden();
    await expect(page.locator('#codex-controls-summary > span')).toHaveText(['메인 · very-long-main-model-name-for-layout', 'Plan · plan-model']);
    await page.evaluate(() => {
        fixtureState.settings.planModeModel = null;
        updateControlsModelSummary();
    });
    await expect(page.locator('#codex-controls-summary > span').last()).toHaveText('Plan · very-long-main-model-name-for-layout');
    await expect(page.locator('.model-field-reasoning').first()).toBeHidden();
}
module.exports = { verifyUsagePanel };
