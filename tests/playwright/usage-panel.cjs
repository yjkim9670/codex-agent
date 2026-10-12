async function verifyUsagePanel(page, expect) {
    const fs = require('node:fs');
    const path = require('node:path');
    const root = path.resolve(__dirname, '../..');
    const source = fs.readFileSync(path.join(root, 'codex-web-app/static/js/app.js'), 'utf8');
    const functions = ['formatCompactTokenCount', 'normalizeTokenUsageEntry', 'buildTokenUsageEntry', 'updateUsageSummary'].map(name => {
        const start = source.indexOf(`function ${name}(`);
        return source.slice(start, source.indexOf('\nfunction ', start + 1));
    }).join('\n');
    await page.route('**/static/fonts/**', route => route.fulfill({
        path: path.join(root, 'codex-web-app', new URL(route.request().url()).pathname),
        contentType: 'font/woff2'
    }));
    await page.setContent('<div class="usage-card" style="width:220px"><div class="usage-value" id="codex-usage-summary"></div></div>');
    await page.addStyleTag({content: fs.readFileSync(path.join(root, 'codex-web-app/static/css/app.css'), 'utf8')});
    await page.addScriptTag({content: `(() => {
        const state = {settings: {loaded:true, usageLimitsEnabled:false}};
        const isUsageKeepaliveHistoryOverlayOpen = () => false;
        const formatNumber = value => Number(value).toLocaleString('en-US');
        ${functions}
        window.usageFixture = {token_usage:{today:{input_tokens:1000000,cached_input_tokens:800000,output_tokens:234567,total_tokens:1234567,requests:32,date:'2026-10-12'},all_time:{input_tokens:2400000000,cached_input_tokens:1800000000,output_tokens:100000000,total_tokens:2500000000,requests:15000}}};
        window.updateUsageSummary = updateUsageSummary;
        updateUsageSummary(window.usageFixture);
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
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(today.locator('summary')).toBeVisible();
    const overflows = await page.locator('.usage-token-summary').evaluateAll(rows =>
        rows.filter(row => row.scrollWidth > row.clientWidth).map(row => ({text:row.textContent, scroll:row.scrollWidth, width:row.clientWidth, rect:row.getBoundingClientRect().width}))
    );
    expect(overflows, 'compact readings should fit a narrow usage panel').toEqual([]);
}
module.exports = { verifyUsagePanel };
