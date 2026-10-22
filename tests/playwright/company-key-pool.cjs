exports.verifyCompanyKeyPool = async (page, expect) => {
    await page.locator('#codex-ui-settings-open').click();
    await page.locator('#codex-company-admin-secret').fill('browser-test-admin');
    await page.locator('#codex-company-admin-login-button').click();
    await expect(page.locator('#codex-company-credential-editor')).toBeVisible();
    await page.locator('#codex-internal-api-key-pool-open').click();
    const overlay = page.locator('#codex-internal-api-key-pool-overlay');
    await expect(overlay).toBeVisible();
    // The temporary preview starts empty; allow a failed prior check to retry.
    page.on('dialog', dialog => dialog.accept());
    while (await page.locator('.internal-key-pool-remove').count()) {
        await page.locator('.internal-key-pool-remove').first().click();
    }
    for (const label of ['browser-first', 'browser-second']) {
        await page.locator('#codex-internal-api-key-label').fill(label);
        await page.locator('#codex-internal-api-key-value').fill(`private-test-${label}`);
        await page.locator('#codex-internal-api-key-add').click();
    }
    await page.locator('#codex-internal-api-key-allocation-save').click();
    await expect(page.locator('#codex-internal-api-key-allocation-status')).toContainText('저장했습니다');
    const pool = await page.evaluate(async () => (await fetch('/api/codex/company-credentials/key-pool')).json());
    expect(pool.keys.map(key => key.label)).toEqual(['browser-first', 'browser-second']);
    expect(JSON.stringify(pool)).not.toContain('private-test-browser');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#codex-ui-settings-open').click();
    await page.locator('#codex-internal-api-key-pool-open').click();
    await expect(page.locator('.internal-key-pool-row')).toHaveCount(2);
    await expect(page.locator('.internal-key-pool-name').first()).toHaveValue('browser-first');
};
