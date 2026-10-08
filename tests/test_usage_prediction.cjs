const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
const relation = { is_applied: true, tokens_per_percent: 1000,
    weights: { uncached_input: 1, cached_input: .1, output: 4 }, observation_group_count: 20 };
const history = { calibration: {
    token_mix: { 'gpt-6.1-sol': { efforts: { medium: { five_hour: relation } } } },
    conditions: { 'gpt-6.1-sol': { low: { five_hour: { is_applied: true, is_reliable: true, tokens_per_percent: 2000 } } } },
    models: { 'gpt-6.1-sol': { weekly: { is_applied: true, is_reliable: true, tokens_per_percent: 10000 } } }
}, relation: { five_hour: { raw_tokens_per_percent: 5000 } } };
const context = vm.createContext({
    state: { settings: { usageHistory: history } },
    resolveUsageHistoryRelationScope: () => 'account',
    toNonNegativeInt: value => value == null ? null : Math.max(0, Math.round(Number(value))),
    resolveOpenAiApiPricing: () => null,
    countLiveSessionCount: () => 1,
    formatCompactTokenCount: value => String(value)
});
vm.runInContext(source.slice(source.indexOf('function resolveLimitTokenScale('),
    source.indexOf('function resolveMessageUsageLimitSnapshot(')), context);
const message = { response_model: 'gpt-6.1-sol', response_reasoning_effort: 'medium', service_tier: 'standard' };
const usage = { inputTokens: 203000, cachedInputTokens: 200000, outputTokens: 500, totalTokens: 203500, hasData: true };
const estimate = context.buildLimitUsageEstimate(usage, { message, limitName: 'five_hour' });
assert.equal(estimate.text, '5h 25.0%');
assert.equal(estimate.lowConfidence, false);
assert.equal(context.buildLimitUsageEstimate(usage, { message, limitName: 'weekly' }).text, 'Weekly 20.35%');
assert.equal(context.resolveLimitTokenScale('five_hour', history, message, { ...usage, estimated: true }).tokensPerPercent, 5000);
assert.equal(context.resolveLimitTokenScale('five_hour', history, message, { ...usage, inputTokens: 0 }).tokensPerPercent, 5000);
assert.equal(context.resolveLimitTokenScale('five_hour', history, { ...message, response_reasoning_effort: 'low' }, usage).tokensPerPercent, 2000);
assert.equal(context.resolveLimitTokenScale('five_hour', history, { ...message, service_tier: 'priority' }, usage).tokensPerPercent, 5000);
history.calibration.token_mix['gpt-6.1-sol'].model = { five_hour: { ...relation, tokens_per_percent: 2000 } };
assert.equal(context.resolveLimitTokenScale('five_hour', history, { ...message, response_reasoning_effort: 'low' }, usage).predictedPercent, 12.5);
// A session aggregate without a model must retain the account fallback.
assert.equal(context.resolveLimitTokenScale('five_hour', history, null, usage).tokensPerPercent, 5000);
relation.is_applied = false;
assert.equal(context.resolveLimitTokenScale('five_hour', history, message, usage).predictedPercent, 12.5);
console.log('PASS: quota display uses validated token mix, effort/model fallbacks and rejects incomplete usage');
