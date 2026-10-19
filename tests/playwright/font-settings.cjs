// Verify real settings events, font downloads, and persisted selection together.
async function verifyFontSettings(page, expect) {
    const fontRequests = [];
    page.on('response', response => {
        if (/\/fonts\/(paperlogy|nexon-lv2-gothic)\//.test(response.url())) {
            fontRequests.push({url: response.url(), status: response.status()});
        }
    });
    expect(await page.evaluate(() => performance.getEntriesByType('resource')
        .filter(entry => /\/fonts\/(paperlogy|nexon-lv2-gothic)\//.test(entry.name)))).toEqual([]);

    for (const [value, family, weights] of [
        ['paperlogy', 'Paperlogy', [100, 200, 300, 400, 500, 600, 700, 800, 900]],
        ['nexon-lv2-gothic', 'NEXON Lv2 Gothic', [300, 400, 500, 600, 700, 900]],
    ]) {
        await page.locator('#codex-ui-settings-open').click();
        const input = page.locator(`input[name="codex-ui-font"][value="${value}"]`);
        await input.check();
        await expect(input).toBeChecked();
        await expect(page.locator('html')).toHaveAttribute('data-ui-font', value);
        expect(await page.evaluate(() => localStorage.getItem('codex-ui-font'))).toBe(value);
        const loaded = await page.evaluate(async ({family, weights}) => {
            for (const weight of weights) {
                const faces = await document.fonts.load(`${weight} 16px "${family}"`, '가나다 ABC 123');
                if (!faces.length || faces.some(face => face.status !== 'loaded')) return false;
            }
            return getComputedStyle(document.body).fontFamily.includes(family);
        }, {family, weights});
        expect(loaded, `${family}: actual font faces and body style`).toBe(true);
        for (const width of [390, 1440]) {
            await page.setViewportSize({width, height: 1000});
            expect(await input.locator('..').evaluate(el => {
                const rect = el.getBoundingClientRect();
                return rect.left >= 0 && rect.right <= innerWidth;
            }), `${value}: option fits ${width}px viewport`).toBe(true);
        }
        await page.reload({waitUntil: 'domcontentloaded'});
        await expect(page.locator('html')).toHaveAttribute('data-ui-font', value);
        await expect(input).toBeChecked();
    }
    expect(fontRequests.length).toBeGreaterThanOrEqual(13);
    expect(fontRequests.filter(item => item.status >= 400)).toEqual([]);
}

module.exports = {verifyFontSettings};
