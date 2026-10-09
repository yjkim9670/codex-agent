const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
const elements = new Map();
for (const id of ['codex-plan-mode-toggle', 'codex-chat-compose-tools-toggle', 'mobile-mode']) {
    elements.set(id, { dataset: {}, attributes: {}, classes: new Set(),
        setAttribute(name, value) { this.attributes[name] = value; },
        classList: { toggle(name, enabled) { const classes = elements.get(id).classes; enabled ? classes.add(name) : classes.delete(name); } }
    });
}
const calls = [];
const context = vm.createContext({
    state: { settings: { planModeState: 'off' } },
    document: { getElementById: id => elements.get(id), querySelector: () => elements.get('mobile-mode') },
    getWorktreeModeState: () => false,
    queuePromptOnServer: async (sessionId, prompt, options) => {
        calls.push({ sessionId, prompt, ...options });
        // Simulate changing composer state while the first request is pending.
        context.setPlanModeToggleState('team');
        return { queueCount: calls.length };
    }
});
function load(start, end) {
    vm.runInContext(source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start))), context);
}
load("const PLAN_MODE_STATE_OFF =", 'let hasManualTheme');
load('function normalizePlanModeState(', 'function getChatToolsOverlayElements(');
load('async function queuePromptWithPlanMode(', 'function getExecutionPolicyPreset(');
load('function getComposeModelRole(', "document.getElementById('codex-execution-settings-save')");

(async () => {
    for (let pass = 0; pass < 2; pass++) {
        for (const [mode, label, role, plan, auto] of [
            ['off', 'Work', 'main', false, false],
            ['plan', 'Plan', 'main', true, false],
            ['team', 'Team', 'main', false, false],
            ['plan_and_execute', 'Plan+', 'main', true, true]
        ]) {
            assert.equal(context.getPlanModeState(), mode);
            context.setPlanModeToggleState(mode);
            assert.equal(elements.get('codex-plan-mode-toggle').textContent, label);
            assert.equal(elements.get('mobile-mode').textContent, label);
            assert.equal(context.getComposeModelRole(), role);
            assert.equal(context.shouldUsePlanModeForRequest(), plan);
            assert.equal(context.shouldAutoExecuteAfterPlan(), auto);
            let prevented = false;
            assert.equal(context.cyclePlanModeFromKeyboardEvent({ key: 'Tab', shiftKey: true,
                preventDefault: () => { prevented = true; }, stopPropagation() {} }), true);
            assert.equal(prevented, true);
        }
    }
    for (const event of [{ key: 'Tab' }, { key: 'Tab', shiftKey: true, ctrlKey: true }, { key: 'Enter', shiftKey: true }]) {
        assert.equal(context.cyclePlanModeFromKeyboardEvent(event), false);
    }
    assert.equal(context.normalizePlanModeState(true), 'plan');
    assert.equal(context.normalizePlanModeState('auto'), 'plan_and_execute');
    assert.equal(context.normalizePlanModeState('invalid'), 'off');
    assert.equal(context.normalizePlanModeState('secondary'), 'team');
    for (const [mode, expected] of [
        ['off', [[false, 'main']]], ['plan', [[true, 'main']]],
        ['team', [[false, 'main']]], ['plan_and_execute', [[true, 'main'], [false, 'main']]]
    ]) {
        calls.length = 0;
        context.setPlanModeToggleState('off');
        const result = await context.queuePromptWithPlanMode('session', 'task', mode);
        assert.equal(result.addedCount, expected.length);
        assert.deepEqual(calls.map(item => [item.planMode, item.modelRole]), expected);
        assert.ok(calls.every(item => item.executionMode === (mode === 'team' ? 'team' : '')));
    }
    console.log('PASS: mode cycle, keyboard modifiers, desktop/mobile state, legacy values, queued roles and Plan+ continuation');
})().catch(error => { console.error(error); process.exitCode = 1; });
