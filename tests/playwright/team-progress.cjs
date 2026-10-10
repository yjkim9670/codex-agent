// Deterministic Team rendering checks; no model execution or saved chat changes.
exports.verifyTeamProgress = async (page, expect) => {
    for (const width of [1280, 360]) {
        await page.setViewportSize({ width, height: 800 });
        await page.evaluate(() => {
            document.getElementById('team-browser-check')?.remove();
            const wrapper = document.createElement('div');
            wrapper.id = 'team-browser-check';
            wrapper.className = 'message assistant';
            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            wrapper.appendChild(bubble);
            document.getElementById('codex-chat-messages').replaceChildren(wrapper);
            const now = Date.now() / 1000;
            window.teamBrowserFixture = { status: 'running', started_at: now - 40, steps: [
                { phase: 'analysis', title: '메인 분석 중', status: 'completed', model: 'main', started_at: now - 40, completed_at: now - 30 },
                { phase: 'worker', title: '워커 1/1 실행 중', status: 'failed', model: 'secondary', error: '비 Git 작업 루트 · 메인 후속 처리로 전환합니다.' },
                { phase: 'review', title: '메인 검토 중', status: 'running', model: 'main', started_at: now - 20, last_activity_at: now - 16,
                  process_running: true, process_pid: 4321, progress: '파일을 확인하고 테스트를 실행합니다. <script>alert(1)</script>',
                  events: [{ index: 1, type: 'item.completed', item_type: 'command_execution', detail: 'command=pytest -q exit_code=0' }] }
            ] };
            setMessageTeamProgress(bubble, window.teamBrowserFixture);
        });
        const panel = page.locator('#team-browser-check .message-team-progress');
        await expect(panel).toBeVisible();
        await expect(panel).toContainText('메인 분석 · 완료');
        await expect(panel).toContainText('비 Git 작업 루트');
        await expect(panel).toContainText('메인 검토 · 진행 중');
        await expect(panel).toContainText('프로세스 실행 중 · 새 응답 대기');
        await expect(panel).toContainText('PID 4321');
        await expect(panel.locator('script')).toHaveCount(0);
        await panel.locator('summary').click();
        await expect(panel.locator('pre')).toBeVisible();
        await expect(panel.locator('pre')).toContainText('exit_code=0');
        await page.evaluate(() => {
            window.teamBrowserFixture.steps[2].events.push({ index: 2, type: 'item.started', detail: '다음 파일 확인' });
            setMessageTeamProgress(document.querySelector('#team-browser-check .message-bubble'), window.teamBrowserFixture);
        });
        await expect(panel.locator('details')).toHaveAttribute('open', '');
        await expect(panel.locator('pre')).toContainText('다음 파일 확인');
        const bounds = await panel.evaluate(el => ({ width: el.getBoundingClientRect().width, client: el.clientWidth, scroll: el.scrollWidth }));
        expect(bounds.scroll).toBeLessThanOrEqual(bounds.client + 1);
        expect(bounds.width).toBeLessThanOrEqual(width);
        // Rebuild from persisted metadata, as renderMessages does after refresh.
        await page.evaluate(() => {
            const bubble = document.querySelector('#team-browser-check .message-bubble');
            bubble.replaceChildren();
            window.teamBrowserFixture.status = 'interrupted';
            setMessageTeamProgress(bubble, JSON.parse(JSON.stringify(window.teamBrowserFixture)));
        });
        await expect(panel).toContainText('Team · 중단');
        await expect(panel).toContainText('메인 검토 · 중단');
        await expect(panel).not.toContainText('프로세스 실행 중');
        await page.evaluate(() => {
            window.teamBrowserFixture.status = 'completed';
            window.teamBrowserFixture.steps[2].status = 'completed';
            window.teamBrowserFixture.steps[2].completed_at = Date.now() / 1000;
            setMessageTeamProgress(document.querySelector('#team-browser-check .message-bubble'), window.teamBrowserFixture);
        });
        await expect(panel).toContainText('Team · 완료');
        await expect(panel).toContainText('메인 검토 · 완료');
    }
};
