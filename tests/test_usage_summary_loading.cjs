const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
const start = source.indexOf('async function refreshUsageSummary(');
const end = source.indexOf('\nfunction usageLimitSnapshotsDiffer(', start);

async function check({failed = false, openDuringRequest = false} = {}) {
    let overlayOpen = false;
    const chart = {items: [{tokens: 100}]};
    const summary = {is_summary: true, count: 1, relation: {weekly: {tokens_per_percent: 100}}};
    const usage = {five_hour: {used_percent: 10}};
    let url;
    const context = vm.createContext({
        URLSearchParams,
        state: {settings: {usageHistory: chart}},
        usageHistoryLastRequestedHours: 24,
        usageHistoryLastRequestedScope: 'workspace',
        isUsageHistoryOverlayOpen: () => overlayOpen,
        fetchJson: async requestUrl => {
            url = requestUrl;
            overlayOpen = openDuringRequest;
            const payload = {usage, usage_history: summary};
            if (failed) throw {payload};
            return payload;
        },
        normalizeBooleanPolicyFlag: (value, fallback) => value ?? fallback,
        updateUsageSummary() {}, updateRenderedLimitUsageEstimates() {},
        normalizeError: () => 'offline',
    });
    vm.runInContext(source.slice(start, end), context);
    await context.refreshUsageSummary();
    assert.match(url, /compact=1&hours=24&scope=workspace/);
    assert.equal(context.state.settings.usage, usage);
    assert.equal(context.state.settings.usageHistory, openDuringRequest ? chart : summary);
}

(async () => {
    for (const failed of [false, true]) {
        for (const openDuringRequest of [false, true]) {
            await check({failed, openDuringRequest});
        }
    }
    console.log('PASS: usage summaries load lazily and in-flight polls preserve an opened chart, including error fallbacks');
})().catch(error => { console.error(error); process.exitCode = 1; });
