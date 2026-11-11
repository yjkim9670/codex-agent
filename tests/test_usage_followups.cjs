const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
const start = source.indexOf('function usageLimitSnapshotsDiffer(');
const end = source.indexOf('\nfunction scheduleUsageSummaryFollowup(', start);
const sample = (value, at) => ({observed_at: at, five_hour: {used_percent: value, resets_at: 'r'}, weekly: {used_percent: 2, resets_at: 'w'}});
async function check(responses, switchAccount = false) {
    const timers = [], summaries = [], footers = [];
    let calls = 0;
    const context = vm.createContext({
        state: {accounts: {activeAccountId: 'a'}, settings: {}, usageLimitFollowups: new Map(), activeSessionId: 's'},
        usageAccountGeneration: 0, usageResponseGeneration: 0, USAGE_HISTORY_REQUEST_TIMEOUT_MS: 100,
        window: {setTimeout: fn => timers.push(fn)},
        fetchChatResponseJson: async () => { const r = responses[calls++]; if (r instanceof Error) throw r; return r; },
        resolveMessageUsageLimitSnapshot: (message, key) => message?.[key] || null,
        findMessageEntryById: () => ({footer: {}}), setMessageTokenUsage: (_footer, msg) => footers.push(msg),
        updateUsageSummary: usage => summaries.push(usage),
    });
    vm.runInContext(source.slice(start, end), context);
    assert.equal(context.usageLimitSnapshotsDiffer(sample(1, 'a'), sample(1, 'b')), false);
    assert.equal(context.usageLimitSnapshotsDiffer(sample(1, 'a'), sample(2, 'b')), true);
    context.scheduleMessageUsageLimitFollowups('s', {id:'m', usage_limits_after: sample(1, 'a')});
    context.scheduleMessageUsageLimitFollowups('s', {id:'m', usage_limits_after: sample(1, 'a')});
    await new Promise(resolve => setImmediate(resolve));
    if (switchAccount) { context.usageAccountGeneration++; context.state.accounts.activeAccountId = 'b'; }
    while (timers.length) { timers.shift()(); await new Promise(resolve => setImmediate(resolve)); }
    return {calls, summaries, footers};
}
const result = (value, time, refreshed = true) => ({message: {id:'m', usage_limits_after: sample(value,time)}, usage: {value}, account_usage_refresh:{refreshed}});
(async () => {
    let r = await check([result(1, 'b'), result(2, 'c')]);
    assert.equal(r.calls, 2); assert.equal(r.summaries.at(-1).value, 2);
    r = await check([result(1,'b'), result(1,'c'), result(1,'d'), result(1,'e')]);
    assert.equal(r.calls, 4);
    r = await check([new Error('offline'), result(1,'c',false), result(2,'d')]);
    assert.equal(r.calls, 3);
    r = await check([result(1,'b')], true); assert.equal(r.calls, 1);
    console.log('PASS: quota followups retry unchanged samples and failures, stop on changes, and respect account changes');
})().catch(error => { console.error(error); process.exitCode = 1; });
