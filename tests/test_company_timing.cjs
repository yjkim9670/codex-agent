const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.events = {}; }
    addEventListener(name, handler) { this.events[name] = handler; }
    appendChild(child) { this.children.push(child); child.parent = this; }
    querySelector(selector) {
        return this.children.find(child => selector.startsWith('.')
            ? (child.className || '').split(' ').includes(selector.slice(1)) : child.tag === selector) || null;
    }
    remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
}
const document = { body: { dataset: { companyMode: 'true' } }, createElement: tag => new Element(tag) };
let overlay;
const context = vm.createContext({ document, MESSAGE_LOG_OVERLAY_MODE_DETAIL: 'detail',
    openMessageLogOverlay: (...args) => { overlay = args; } });
const start = source.indexOf('function buildCompanyTimingText(');
const end = source.indexOf('function setMessageTimingBreakdown(', start);
vm.runInContext(source.slice(start, end), context);
const footer = new Element('footer');
const message = { company_timing: {
    backend: 'claude', stream_id: 'test-stream', pid: 123, started_at: 1000, completed_at: 3000,
    environment: { os: 'Darwin' },
    spans: [{ name: 'process_spawn', duration_ms: 123, start_phase: 'starting_process', end_phase: 'process_spawned' }],
    timeline: [{ phase: 'waiting_cli_output', at: 2000, since_previous_ms: 1000 }],
    operations: { session_store_read: { count: 2, total_ms: 13, max_ms: 9, first_at: 1000, last_at: 2000 } }
} };
context.setMessageCompanyTiming(footer, message);
const button = footer.querySelector('.message-timing-link');
assert.ok(button);
assert.equal(button.type, 'button');
assert.equal(button.textContent, '타임 로그 보기');
assert.equal(footer.querySelector('details'), null);
button.events.click({ preventDefault() {}, stopPropagation() {} });
assert.equal(overlay[0], '타임 로그');
assert.equal(overlay[2], '사내 디버깅 · 프로세스 진행 시각');
assert.match(overlay[1], /CLI 출력 대기/);
assert.match(overlay[1], /프로세스 생성: 123\.0ms/);
assert.match(overlay[1], /Darwin/);
assert.match(overlay[1], /합산 금지/);
assert.match(overlay[1], /2회 \| 13\.0ms \| 9\.0ms/);
assert.match(overlay[1], /1970-01-01T00:00:02\.000Z/);
message.company_timing.pid = 456;
context.setMessageCompanyTiming(footer, message);
button.events.click({ preventDefault() {}, stopPropagation() {} });
assert.match(overlay[1], /PID: 456/);
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 1);
message.company_timing.pending = true;
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 0);
message.company_timing.pending = false;
document.body.dataset.companyMode = 'false';
context.setMessageCompanyTiming(footer, message);
assert.equal(footer.children.length, 1);
console.log('Company timing rendering: passed');
