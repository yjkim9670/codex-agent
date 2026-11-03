async function verifyChatLimitReset(page, expect) {
    await page.evaluate(() => chatReady);
    // The fixture returns the provider's ISO timestamp for 5h and epoch seconds
    // for weekly. Both must render in the sidebar and the usage dialog.
    await expect(page.locator('#limit-windows')).toContainText('76% 남음');
    await expect(page.locator('#limit-windows')).not.toContainText('시간 미제공');
    await page.locator('#usage').click();
    const expected = await page.evaluate(() => [
        new Date('2033-05-18T03:33:20Z').toLocaleString(),
        new Date('2033-05-23T22:26:40Z').toLocaleString(),
    ]);
    for (const selector of ['#limit-windows', '#dialog-limits']) {
        for (const reset of expected) await expect(page.locator(selector)).toContainText(reset);
        await expect(page.locator(selector)).not.toContainText('시간 미제공');
    }
    await page.evaluate(() => paintLimits({five_hour: {
        used_percent: 24, remaining_percent: 76, resets_at: 'invalid',
    }}));
    await expect(page.locator('#dialog-limits')).toContainText('시간 미제공');
    await expect(page.locator('#dialog-limits')).not.toContainText('Invalid Date');
}
module.exports = {verifyChatLimitReset};
