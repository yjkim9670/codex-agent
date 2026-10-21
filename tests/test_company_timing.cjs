const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
class Element {
    constructor(tag) { this.tag = tag; this.children = []; }
    appendChild(child) { this.children.push(child); child.parent = this; }
    querySelector(selector) {
        return this.children.find(child => selector.startsWith('.')
            ? child.className === selector.slice(1) : child.tag === selector) || null;
    }
    remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
}
const document = { body: { dataset: { companyMode: 'true' } }, createElement: tag => new Element(tag) };
const context = vm.createContext({ document });
const start = source.indexOf('function buildCompanyTimingText(');
const end = source.indexOf('function setMessageTimingBreakdown(', start);
vm.runInContext(source.slice(start, end), context);
const footer = new Element('footer');
const message = { company_timing: {
    backend: 'claude', stream_id: 'test-stream', pid: 123, started_at: 1000, completed_at: 3000,
    timeline: [{ phase: 'waiting_cli_output', at: 2000, since_previous_ms: 1000 }],
    operations: { session_store_read: { count: 2, total_ms: 13, max_ms: 9, first_at: 1000, last_at: 2000 } }
} };
context.setMessageCompanyTiming(footer, message);
const panel = footer.querySelector('.message-company-timing');
assert.ok(panel.open);
assert.match(panel.querySelector('pre').textContent, /CLI 출력 대기/);
assert.match(panel.querySelector('pre').textContent, /2회 \| 13\.0ms \| 9\.0ms/);
assert.match(panel.querySelector('pre').textContent, /1970-01-01T00:00:02\.000Z/);
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 1);
message.company_timing.pending = true;
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 0);
message.company_timing.pending = false;
document.body.dataset.companyMode = 'false';
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 0);
console.log('Company timing rendering: passed');
