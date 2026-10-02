// Exercise the actual branch/transition functions with a live stream in Chromium.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const source = fs.readFileSync(path.join(__dirname, '../codex-web-app/static/js/app.js'), 'utf8');
function slice(start, end) {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0 && source.indexOf(end, offset) > offset);
    return source.slice(offset, source.indexOf(end, offset));
}

(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--use-mock-keychain'] });
    try {
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.setContent('<div id="history" class="message" data-message-id="completed"><button>Branch copy</button></div><div id="live" class="message is-streaming" data-message-id="live" data-message-streaming="true"></div>');
        await page.addScriptTag({ content: `
            const state = { activeSessionId: 'source', sessionStorage: null };
            const events = [];
            const stream = { entry: { wrapper: document.getElementById('live') },
                polling: true, pendingQueue: ['queued'], output: 'partial' };
            const SESSION_MUTATION_REQUEST_TIMEOUT_MS = 1000;
            const SESSION_DETAIL_REQUEST_TIMEOUT_MS = 1000;
            const getSessionStream = id => id === 'source' ? stream : null;
            const isSessionBusy = () => true;
            const setStatus = text => events.push(text);
            const showToast = text => events.push(text);
            const normalizeError = error => error.message;
            const removeQueuedPromptWaitlist = () => {};
            const updateSessionStorageSummary = () => {};
            const upsertSessionSummary = () => {};
            const ensureSessionState = () => {};
            const syncSessionPendingQueue = () => {};
            const renderSessions = () => {};
            const attachSessionStreamEntry = () => {};
            const updateHeader = () => {};
            const syncActiveSessionControls = () => {};
            const syncActiveSessionStatus = () => {};
            const maybeAttachRemoteStreamToActiveSession = async () => {};
            const renderMessages = () => {
                if (stream.entry !== null) throw new Error('Original stream DOM was not detached');
                events.push('rendered branch');
            };
            const fetchChatResponseJson = async (url, options) => {
                if (state.activeSessionId !== 'source') throw new Error('Premature active session change');
                events.push(options.method === 'POST' ? 'branch POST' : 'branch GET');
                return { session: { id: 'branch', messages: [], pending_queue: [] } };
            };
            window.confirm = () => true;
            ${slice('function getMessageActionContext(', 'async function deleteMessageFromWrapper(')}
            ${slice('async function branchMessageFromWrapper(', 'async function writeTextToClipboard(')}
            ${slice('async function loadSession(', 'function renderMessages(')}
            ${slice('function detachSessionStreamEntry(', 'function attachSessionStreamEntry(')}
            ${slice('function setMessageStreaming(', 'function getStreamDuration(')}
            document.querySelector('#history button').onclick = () => {
                window.branchDone = branchMessageFromWrapper(document.getElementById('history'), document.querySelector('#history button'));
            };
        ` });
        // Both the rendered live class and persisted streaming metadata block a branch.
        for (const classOnly of [true, false]) {
            const result = await page.evaluate(async classOnly => {
                const live = document.getElementById('live');
                live.classList.toggle('is-streaming', classOnly);
                live.dataset.messageStreaming = classOnly ? 'false' : 'true';
                await branchMessageFromWrapper(live, document.querySelector('#history button'));
                return { posts: events.filter(value => value === 'branch POST').length, active: state.activeSessionId };
            }, classOnly);
            assert.deepEqual(result, { posts: 0, active: 'source' });
        }
        await page.locator('#history button').click();
        await page.evaluate(() => window.branchDone);
        const result = await page.evaluate(() => ({ active: state.activeSessionId,
            detached: stream.entry === null, polling: stream.polling, queue: stream.pendingQueue,
            posts: events.filter(value => value === 'branch POST').length,
            rendered: events.includes('rendered branch'), disabled: document.querySelector('#history button').disabled }));
        assert.deepEqual(result, { active: 'branch', detached: true, polling: true,
            queue: ['queued'], posts: 1, rendered: true, disabled: false });
        // Detached streams still receive output; a completed bubble becomes branchable.
        assert.equal(await page.evaluate(() => {
            stream.output += ' final';
            setMessageStreaming(document.getElementById('live'), false);
            return stream.output === 'partial final' && document.getElementById('live').dataset.messageStreaming === 'false';
        }), true);
        assert.deepEqual(errors, []);
        console.log('PASS: completed bubble branch during live response, unfinished bubble guards, normal transition, stream and queue preservation');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
