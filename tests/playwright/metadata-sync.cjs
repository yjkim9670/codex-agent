exports.verifyMetadataSync = async (page, expect) => {
    await expect(page.locator('#sync-runs')).not.toContainText('불러오는 중');
    await expect(page.locator('#project-path')).toContainText('프로젝트:');
    await expect(page).toHaveTitle('TG Platform 문서 동기화 | Codex Workbench');
    await expect(page.locator('h1')).toHaveText('TG Platform 문서 동기화');
    await expect(page.locator('#preview-status')).not.toContainText('분석하는 중');
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('400 14px Paperlogy'))).toBe(true);
    const main = await page.request.get(new URL('/', page.url()).toString());
    const mainHtml = await main.text();
    expect(mainHtml).not.toContain('id="codex-metadata-sync-open"');
    expect(mainHtml).toContain('사용량 5시간 구간이 0%일 때 블로그 한 단계를 진행합니다.');
    await page.route('**/api/codex/metadata-sync/preview', route => route.fulfill({json: {
        generated_at_kst: '2026-10-26 12:00 KST', since_ref: 'abc123', changed_paths_count: 2,
        features: [{name: 'vcd', documents: ['metadata/vcd.md', '<script>window.unsafe = true</script>'], reasons: ['affected_scope', 'stale_translation']}],
        projects: [{name: 'HPA', documents: ['projects/HPA.md'], reasons: ['affected_scope']}],
        other_documents: [{path: 'tools/sim.md', reasons: ['affected_scope']}], warnings: [], immediate_update_reasons: [],
    }}));
    await page.locator('#preview-refresh').click();
    await expect(page.locator('#preview-features')).toContainText('metadata/vcd.md');
    await expect(page.locator('#preview-features')).toContainText('번역 갱신 필요');
    await expect(page.locator('#feature-count')).toHaveText('(1)');
    await page.getByRole('button', {name: 'vcd 범위 선택', exact: true}).click();
    await expect(page.locator('#sync-scope')).toHaveValue('feature:vcd');
    await expect(page.locator('#preview-projects')).toContainText('projects/HPA.md');
    await expect(page.locator('#project-count')).toHaveText('(1)');
    await page.getByRole('button', {name: '과제 HPA 범위 선택', exact: true}).click();
    await expect(page.locator('#sync-scope')).toHaveValue('project:HPA');
    await page.locator('#preview-other summary').click();
    await expect(page.locator('#other-documents')).toContainText('tools/sim.md');
    const run = {id: 'browser_fixture', started_at_kst: '2026-10-26 10:00:00 KST', mode: 'manual', scope: ['feature:vcd'], result: 'success', published: true, changed_files: 1, has_change_record: true};
    await page.route('**/api/codex/metadata-sync', route => route.fulfill({json: {available: true, project: '/fixture/CommonTG', running: false, runs: [run]}}));
    await page.route('**/api/codex/metadata-sync/runs/browser_fixture', route => route.fulfill({json: {
        metadata: {...run, validation: {passed: true}, changes: [{path: 'metadata/spec.md', diff: '-old\n+<script>window.unsafe = true</script>', added_lines: 1, removed_lines: 1}]},
        summary: '검증 완료 · 미반영 항목 없음', validation_log: 'errors: 0; warnings: 0', error_log: '',
    }}));
    await page.locator('#sync-refresh').click();
    await expect(page.locator('#sync-runs')).toContainText('feature:vcd');
    await page.getByRole('button', {name: 'browser_fixture 상세 보기'}).click();
    await expect(page.locator('#detail-status')).toContainText('원본 반영 완료 · 검증 통과');
    await page.locator('#changed-files summary').click();
    await expect(page.locator('#changed-files pre')).toContainText('<script>window.unsafe');
    expect(await page.evaluate(() => window.unsafe)).toBeUndefined();
    await expect(page.locator('#detail-summary')).toContainText('미반영 항목 없음');
    for (const selector of ['h1', '#sync-scope', '#sync-start', '#sync-runs', '#changed-files pre', '#detail-summary']) {
        expect(await page.locator(selector).evaluate(node => getComputedStyle(node).fontFamily)).toContain('Paperlogy');
    }
    let requestBody;
    await page.route('**/api/codex/metadata-sync/run', async route => {
        requestBody = route.request().postDataJSON();
        expect(route.request().headers()['x-workbench-request']).toBe('metadata-sync');
        await route.fulfill({status: 202, json: {started: true}});
    });
    await page.getByRole('button', {name: '과제 HPA 범위 선택', exact: true}).click();
    await page.locator('#sync-start').click();
    await expect.poll(() => requestBody).toEqual({scope: 'project:HPA'});
    await page.route('**/api/codex/metadata-sync/preview', route => route.fulfill({json: {
        features: [], projects: [], other_documents: [], warnings: [], immediate_update_reasons: [], changed_paths_count: 0, since_ref: '',
    }}));
    await page.locator('#preview-refresh').click();
    await expect(page.locator('#preview-features')).toContainText('현재 수정 후보 feature가 없습니다.');
    await expect(page.locator('#preview-other')).toBeHidden();
    await expect(page.locator('#preview-projects')).toContainText('현재 수정 후보 과제가 없습니다.');
    // HTML returned by a proxy/login page must give an actionable message, then recover.
    await page.route('**/api/codex/metadata-sync/preview', route => route.fulfill({
        contentType: 'text/html', body: '<!DOCTYPE html><html><body>Login</body></html>',
    }));
    await page.locator('#preview-refresh').click();
    await expect(page.locator('#preview-status')).toContainText('JSON 대신 다른 형식');
    await expect(page.locator('#preview-status')).not.toContainText('Unexpected token');
    await expect(page.locator('#preview-projects')).toBeEmpty();
    await expect(page.locator('#preview-refresh')).toBeEnabled();
    await page.route('**/api/codex/metadata-sync/preview', route => route.fulfill({
        contentType: 'application/json', body: '<!DOCTYPE html>',
    }));
    await page.locator('#preview-refresh').click();
    await expect(page.locator('#preview-status')).toContainText('API 응답을 읽을 수 없습니다');
    await page.route('**/api/codex/metadata-sync/preview', route => route.fulfill({json: {
        features: [], projects: [], other_documents: [], warnings: [], immediate_update_reasons: [], changed_paths_count: 0,
    }}));
    await page.locator('#preview-refresh').click();
    await expect(page.locator('#preview-projects')).toContainText('현재 수정 후보 과제가 없습니다.');
    await page.setViewportSize({width: 390, height: 844});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
};
