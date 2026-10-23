async function verifyCompanyModels(page, expect) {
    await page.evaluate(() => {
        const catalogs = {
            dtgpt: [{slug: 'main-model', reasoning_options: ['high']}],
            claude: [
                {slug: 'Qwen3.6-27B-H', selectable: false, reasoning_options: []},
                {slug: 'Qwen3.8-27B', reasoning_options: ['low', 'medium', 'xhigh']},
                {slug: 'openai/gpt-oss-120b', reasoning_options: ['low', 'medium', 'high']},
                {slug: 'standard', reasoning_options: ['low', 'medium', 'high', 'xhigh']},
                {slug: 'GaussO4.1-260330', reasoning_options: ['on', 'off']},
            ],
            opencode: [{slug: 'codemate/CodeLLMFast', reasoning_options: []}],
        };
        state.settings = {...state.settings, loaded: true, agentBackend: 'claude', model: 'Qwen3.8-27B', reasoningEffort: 'high',
            secondaryAgentBackend: null, secondaryModel: null, secondaryReasoningEffort: null,
            agentBackendOptions: [{id: 'dtgpt', name: 'Codex'}, {id: 'claude', name: 'Claude'}, {id: 'opencode', name: 'OpenCode'}],
            modelCatalogsByBackend: normalizeModelCatalogsByBackend(catalogs)};
        updateAgentBackendControls('claude', state.settings.agentBackendOptions);
        applyBackendScopedModelOptions();
        document.getElementById('codex-controls').classList.remove('is-collapsed');
    });
    const main = page.locator('#codex-model-select');
    const secBackend = page.locator('#codex-secondary-agent-backend-select');
    await expect(main).toBeVisible();
    await expect(main.locator('option[value="Qwen3.6-27B-H"]')).toBeDisabled();
    await expect(main.locator('option[value="Qwen3.6-27B-H"]')).toContainText('사용 불가');
    const efforts = id => page.locator(id).locator('option').evaluateAll(items => items.map(item => item.value).filter(Boolean));
    expect(await efforts('#codex-reasoning-select')).toEqual(['low', 'medium', 'xhigh']);
    await expect(page.locator('#codex-reasoning-select')).toHaveValue('');
    await main.selectOption('openai/gpt-oss-120b');
    expect(await efforts('#codex-reasoning-select')).toEqual(['low', 'medium', 'high']);
    await main.selectOption('standard');
    expect(await efforts('#codex-reasoning-select')).toEqual(['low', 'medium', 'high', 'xhigh']);
    await main.selectOption('GaussO4.1-260330');
    expect(await efforts('#codex-reasoning-select')).toEqual(['on', 'off']);
    await secBackend.selectOption('opencode');
    const secondary = page.locator('#codex-secondary-model-select');
    await expect(secondary.locator('option[value="codemate/CodeLLMFast"]')).toBeEnabled();
    expect(await efforts('#codex-secondary-model-select')).toEqual(['codemate/CodeLLMFast']);
    await expect(page.locator('#codex-secondary-reasoning-input')).toBeDisabled();
    await secBackend.selectOption('claude');
    await secondary.selectOption('Qwen3.8-27B');
    expect(await efforts('#codex-secondary-reasoning-select')).toEqual(['low', 'medium', 'xhigh']);
    await expect(secondary.locator('option[value="Qwen3.6-27B-H"]')).toBeDisabled();
    await secBackend.selectOption('opencode');
    await secondary.selectOption('codemate/CodeLLMFast');
    let submitted;
    await page.route('**/api/codex/settings', async route => {
        if (route.request().method() !== 'PATCH') return route.continue();
        submitted = route.request().postDataJSON();
        const catalogs = await page.evaluate(() => Object.fromEntries(Object.entries(state.settings.modelCatalogsByBackend).map(([backend, entries]) => [backend, entries.map(entry => ({slug: entry.slug, selectable: entry.selectable, reasoning_options: entry.reasoningOptions, default_reasoning_effort: entry.defaultReasoningEffort}))])));
        await route.fulfill({json: {settings: submitted, model_catalogs_by_agent_backend: catalogs,
            model_catalog: catalogs.claude, agent_backend_options: [{id: 'dtgpt'}, {id: 'claude'}, {id: 'opencode'}]}});
    });
    await page.evaluate(() => updateSettings());
    expect(submitted.secondary_agent_backend).toBe('opencode');
    expect(submitted.secondary_model).toBe('codemate/CodeLLMFast');
    expect(submitted.secondary_reasoning_effort).toBe('');
    await expect(secBackend).toHaveValue('opencode');
    await expect(secondary).toHaveValue('codemate/CodeLLMFast');
}
module.exports = {verifyCompanyModels};
