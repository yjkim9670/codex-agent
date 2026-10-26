const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
function load(context, start, end) {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0 && source.indexOf(end, offset) > offset);
    vm.runInContext(source.slice(offset, source.indexOf(end, offset)), context);
}
function setup(parentMissing = true, bothMissing = false, serverAuto = false) {
    const requests = [], notices = [], confirmations = [];
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    const context = vm.createContext({
        console, Date, Set, Array, Number,
        GIT_SYNC_TARGET_WORKSPACE: 'workspace', GIT_SYNC_TARGET_CODEX_AGENT: 'codex_agent',
        GIT_BRANCH_STATUS_CACHE_MS: 1000, GIT_STATUS_REQUEST_TIMEOUT_MS: 1000,
        GIT_STAGE_REQUEST_TIMEOUT_MS: 1000, GIT_COMMIT_REQUEST_TIMEOUT_MS: 1000,
        GIT_PUSH_REQUEST_TIMEOUT_MS: 1000,
        gitMutationInFlight: false, gitBranchRepoTarget: 'workspace',
        gitBranchStatusInFlight: null, gitBranchStatusCache: { fetchedAt: 0 },
        normalizeGitSyncRepoTarget: target => target || 'workspace',
        normalizeGitChangedFilesCount: count => count,
        normalizeGitWindowsInvalidFiles: files => files || [],
        normalizeGitWindowsInvalidCount: (count = 0) => count,
        normalizeGitWindowsPathIssueState: value => Boolean(value),
        normalizeGitDivergenceCount: value => value,
        normalizeGitChangedFiles: files => files,
        getGitSyncRepoLabel: target => target,
        getGitSyncOverlayElements: () => null,
        isGitSyncOverlayOpen: () => false, isGitBranchOverlayOpen: () => false,
        setGitSyncHistoryCache: () => {}, setGitButtonBusy: () => {},
        refreshGitBranchStatus: async () => {},
        recoverGitPushButtonsIfIdle: () => {}, getGitPushButtons: button => [button],
        summarizeGitOutput: () => '', showToast: text => notices.push(text),
        normalizeGitActionError: error => error.message,
        requestGitCancelAfterTimeout: async () => '',
        window: { confirm: text => { confirmations.push(text); return true; } },
        fetchJson: async (url, options) => {
            const target = options.body ? JSON.parse(options.body).repo_target : 'workspace';
            requests.push({ url, target });
            if (url.endsWith('/status')) {
                await pending;
                if (serverAuto && target === 'auto') {
                    return { repo_target: parentMissing ? 'codex_agent' : 'workspace',
                        branch: 'main', changed_files: ['tracked.txt'], changed_files_count: 1 };
                }
                if (parentMissing) throw new Error('not a git repository');
                return { branch: 'main', changed_files: [{path: 'workspace.txt'}], changed_files_count: 1 };
            }
            return { commit_hash: 'abc', post_fetch_ok: true };
        },
        fetchGitStatusForRepoTarget: async target => {
            requests.push({ url: 'target-status', target });
            if (bothMissing) throw new Error('not a git repository');
            return { branch: 'main', changedFiles: [{path: `${target}.txt`}], count: 1 };
        }
    });
    load(context, 'async function fetchGitStatus(', 'async function fetchGitChangedFilesCount(');
    load(context, 'async function resolveGitActionRepoTarget(', 'async function handleGitSync(');
    return { context, requests, notices, confirmations, release };
}
(async () => {
    for (const missing of [false, true]) {
        const test = setup(missing, false, true);
        test.release();
        for (let poll = 0; poll < 3; poll++) {
            const status = await test.context.fetchGitStatus(true);
            assert.equal(status.repoTarget, missing ? 'codex_agent' : 'workspace');
            assert.equal(status.isStale, false);
        }
        assert.equal(test.requests.length, 3);
        assert.ok(test.requests.every(({url, target}) => url.endsWith('/status') && target === 'auto'));
        await test.context.handleGitPush({});
        assert.equal(test.requests.find(({url}) => url.endsWith('/push')).target,
            missing ? 'codex_agent' : 'workspace');
    }
    for (const action of ['handleGitQuickCommit', 'handleGitPush']) {
        for (const missing of [false, true]) {
            const test = setup(missing);
            // Clicking while the first header status is still pending must wait.
            const firstStatus = test.context.fetchGitStatus(true);
            const operation = test.context[action]({});
            await Promise.resolve();
            assert.equal(test.requests.length, 1);
            assert.equal(test.confirmations.length, 0);
            test.release();
            await Promise.all([firstStatus, operation]);
            const mutations = test.requests.filter(({url}) => /\/(stage|commit|push)$/.test(url));
            assert.equal(mutations.length, action === 'handleGitPush' ? 1 : 2);
            assert.ok(mutations.every(({target}) => target === (missing ? 'codex_agent' : 'workspace')));
            assert.ok(test.confirmations.every(text => text.startsWith(missing ? 'codex_agent' : 'workspace')));
        }
        const failed = setup(true, true);
        failed.release();
        await failed.context[action]({});
        assert.ok(!failed.requests.some(({url}) => /\/(stage|commit|push)$/.test(url)));
        assert.equal(failed.confirmations.length, 0);
        assert.ok(failed.notices.some(text => text.includes('Git 저장소를 확인')));
        // An explicit Sync overlay selection must override the header default.
        const explicit = setup(true);
        explicit.release();
        await explicit.context[action]({}, {repoTarget: 'workspace'});
        assert.ok(explicit.requests.filter(({url}) => /\/(stage|commit|push)$/.test(url)).every(({target}) => target === 'workspace'));
        assert.ok(!explicit.requests.some(({url}) => url.endsWith('/status')));
    }
    console.log('PASS: header Commit/Push fallback, parent preference, pending status, missing repositories and explicit overlay targets');
})().catch(error => { console.error(error); process.exitCode = 1; });
