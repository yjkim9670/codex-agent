// Verify the real input listener avoids job-list work while preserving control state.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');
const source = fs.readFileSync(path.join(__dirname, '../codex-web-app/static/js/app.js'), 'utf8');
function slice(start, end) {
    const first = source.indexOf(start);
    const last = source.indexOf(end, first);
    assert.ok(first >= 0 && last > first, start);
    return source.slice(first, last);
}
(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        const page = await browser.newPage();
        await page.setContent(`<textarea id="codex-chat-input"></textarea>
            <button id="codex-chat-send"><span class="sr-only"></span></button>
            <button id="codex-chat-image-attach"></button><button id="codex-worktree-mode-toggle"></button>
            <section class="chat-runtime-strip"><div id="codex-chat-job-monitor">
            <span id="codex-chat-job-monitor-summary"></span><ul id="codex-chat-job-monitor-list"></ul>
            </div></section>`);
        await page.addScriptTag({ content: `
            const input = document.getElementById('codex-chat-input');
            const state = { activeSessionId: 'active', remoteStreamSessions: new Set() };
            let busy = false;
            let collections = 0;
            let viewportChanges = 0;
            let keyboardMarks = 0;
            let mobile = false;
            const getSessionState = () => ({ sending: busy });
            const getSessionStream = () => busy;
            const getQueuedPromptCount = () => 0;
            const isMobileViewportBehaviorActive = () => mobile;
            const CHAT_INPUT_MOBILE_PLACEHOLDER = 'mobile';
            const CHAT_INPUT_DEFAULT_PLACEHOLDER = 'desktop';
            const collectRunningJobs = () => { collections++; return [{ title: 'Job', phase: 'Running' }]; };
            const isCompactLayout = () => false;
            const cyclePlanModeFromKeyboardEvent = () => false;
            const handleSubmit = () => {};
            const formatElapsedTime = () => '';
            ${slice('function renderRunningJobsMonitor()', 'function startRunningJobsMonitorTicker()')}
            ${slice('function syncActiveSessionControls(', 'function appendTextToChatInput(')}
            ${slice("    if (input) {\n        input.addEventListener('keydown'", '    if (imageAttachBtn && imageInput)')}
            // Install the actual viewport input listener with observable dependencies.
            const mobileMedia = { matches: false };
            const markMobilePromptKeyboardExpected = () => keyboardMarks++;
            const handleViewportChange = () => viewportChanges++;
            ${slice("    input.addEventListener('input', () => {\n        if (!isMobileViewportBehaviorActive", '\n}\n\nfunction setupMobileSettingsInputBehavior(')}
            window.runChecks = () => {
                const send = document.getElementById('codex-chat-send');
                syncActiveSessionControls();
                const initialCollections = collections;
                const originalItem = document.querySelector('#codex-chat-job-monitor-list li');
                let labelMutations = 0;
                const observer = new MutationObserver(records => labelMutations += records.length);
                observer.observe(send.querySelector('.sr-only'), { childList: true });
                for (let i = 0; i < 1000; i++) {
                    input.value = '한글 prompt ' + i;
                    input.dispatchEvent(new Event('input'));
                }
                labelMutations += observer.takeRecords().length;
                observer.disconnect();
                const result = { extraCollections: collections - initialCollections,
                    preservedJobNode: originalItem === document.querySelector('#codex-chat-job-monitor-list li'),
                    labelMutations, desktopViewportChanges: viewportChanges, sendMode: send.dataset.mode };
                busy = true;
                input.dispatchEvent(new Event('input'));
                result.queueMode = send.dataset.mode;
                input.value = '';
                input.dispatchEvent(new Event('input'));
                result.stopMode = send.dataset.mode;
                busy = false;
                state.remoteStreamSessions.add('active');
                syncActiveSessionControls();
                result.remoteLocked = input.disabled && input.readOnly && send.disabled;
                state.remoteStreamSessions.clear();
                syncActiveSessionControls();
                result.unlocked = !input.disabled && !send.disabled;
                result.stateChangeCollections = collections - initialCollections;
                mobile = true;
                input.dispatchEvent(new Event('input'));
                result.mobileViewportChanges = viewportChanges;
                result.keyboardMarks = keyboardMarks;
                return result;
            };
        ` });
        assert.deepEqual(await page.evaluate(() => runChecks()), {
            extraCollections: 0, preservedJobNode: true, labelMutations: 0,
            desktopViewportChanges: 0, sendMode: 'send', queueMode: 'queue', stopMode: 'stop',
            remoteLocked: true, unlocked: true, stateChangeCollections: 2,
            mobileViewportChanges: 1, keyboardMarks: 1,
        });
        console.log('PASS: 1000 prompt inputs skip job collection/DOM replacement and desktop viewport work; Send/Queue/Stop, remote locks and mobile keyboard updates preserved');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
