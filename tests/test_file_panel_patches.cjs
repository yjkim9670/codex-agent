const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../codex-web-app/static/js/app.js`, 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function buildFilePanelEditPatch('), source.indexOf('async function fetchFileBrowserDirectory(')), context);
const build = context.buildFilePanelEditPatches;
const compact = context.compactFilePanelEditPatches;
function apply(original, patches) {
    const chars = Array.from(original);
    let cursor = 0;
    let result = '';
    for (const p of patches) {
        assert.ok(p.start >= cursor);
        result += chars.slice(cursor, p.start).join('') + p.insert;
        cursor = p.start + p.delete_count;
    }
    return result + chars.slice(cursor).join('');
}
const cases = [
    ['', ''], ['', '새 파일😀\n'], ['delete all', ''], ['unchanged', 'unchanged'],
    ['abc', 'xabc!'], ['abc def ghi', 'aBc def gHi'],
    ['😀한글👩‍💻 end', '😀수정👩‍💻 END'], ['a\nb\nc\n', 'a\nx\nb\n'],
    ['x'.repeat(10000), 'y'.repeat(10000)], ['aaaaabaaaaa', 'aaaacbaaaa'],
];
for (const [a, b] of cases) assert.equal(apply(a, build(a, b)), b);
let seed = 42;
const rand = n => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n; };
const alphabet = ['a', 'b', 'c', '\n', '\r', '한', '😀'];
for (let i = 0; i < 1000; i++) {
    const a = Array.from({length: rand(100)}, () => alphabet[rand(alphabet.length)]).join('');
    const b = Array.from(a);
    for (let j = 0; j < 5; j++) b.splice(rand(b.length + 1), rand(4), alphabet[rand(alphabet.length)]);
    assert.equal(apply(a, build(a, b.join(''))), b.join(''));
}
const restore = context.restoreFilePanelEditorNewlines;
for (const [original, edited, expected] of [
    ['a\r\nb\r\n', 'a\nB\n', 'a\r\nB\r\n'],
    ['a\r\nb\r\n', 'a\nx\nb\n', 'a\r\nx\r\nb\r\n'],
    ['a\rb\r', 'a\nB\n', 'a\rB\r'],
    ['a\r\nb\nc\r', 'a\nB\nc\n', 'a\r\nB\nc\r'],
    ['😀\r\na\r\n', '😀\nA\n', '😀\r\nA\r\n'],
    ['a\r\n', 'a', 'a'], ['a\n', 'a\nb\n', 'a\nb\n'],
    ['a\r\nb\n', 'a\nb\n', 'a\r\nb\n'],
]) assert.equal(restore(original, edited), expected);
const original = Array.from({length: 3000}, (_, i) => `line ${i}: const value = 123456789;\n`).join('');
const edited = original.replace('line 0:', 'Line 0:').replace('line 2999:', 'Line 2999:');
const patches = build(original, edited);
assert.equal(patches.length, 2);
assert.equal(apply(original, patches), edited);
assert.ok(Buffer.byteLength(JSON.stringify(patches)) < 150);
const compactPatches = compact(patches);
assert.equal(JSON.stringify(compactPatches), JSON.stringify(patches.map(({start, delete_count, insert}) => [start, delete_count, insert])));
assert.ok(Buffer.byteLength(JSON.stringify(compactPatches)) < Buffer.byteLength(JSON.stringify(patches)));
console.log(`PASS: ${cases.length} cases, 1000 randomized cases, 8 newline cases; distant edits ${Buffer.byteLength(original)}B -> ${Buffer.byteLength(JSON.stringify(compactPatches))}B compact patch JSON`);
context.stringifyJsonRequestPayload = JSON.stringify;
context.getUtf8ByteLength = value => Buffer.byteLength(value);
context.normalizeFileBrowserRoot = value => String(value || 'server');
context.normalizeFileBrowserRelativePath = value => String(value || '');
vm.runInContext(source.slice(source.indexOf('function buildFilePanelWritePayload('), source.indexOf('async function writeFilePanelFile(')), context);
vm.runInContext(source.slice(source.indexOf('function getFileBrowserEncryptedBodyByteLength('), source.indexOf('function showCopyableFilePanelSaveConfirmation(')), context);
const summary = context.getFilePanelSaveChangeSummary(original, edited);
assert.equal(summary.removedBytes, 2);
assert.equal(summary.insertedBytes, 2);
assert.equal(summary.removedLines, 2);
assert.equal(summary.insertedLines, 2);
assert.ok(summary.patchPayloadBytes < Buffer.byteLength(JSON.stringify({
    mode: 'patch', root: 'server', path: 'file', expected_modified_ns: '0', patch: patches
})));
const actualRequest = {
    root: 'workspace',
    path: 'a/long/path/'.repeat(10) + 'sample.f',
    expectedModifiedNs: '1799999999999999999',
    cryptoSessionId: 's'.repeat(32)
};
const deletionSummary = context.getFilePanelSaveChangeSummary('0123456789', '012349', actualRequest);
const deletionPayload = context.buildFilePanelWritePayload(
    actualRequest.root,
    actualRequest.path,
    '012349',
    actualRequest.expectedModifiedNs,
    '0123456789'
);
const compactWritePayload = JSON.stringify([
    deletionPayload.root,
    deletionPayload.path,
    deletionPayload.expected_modified_ns,
    deletionPayload.patch
]);
assert.equal(deletionSummary.patchPayloadBytes, Buffer.byteLength(compactWritePayload));
// CFW3 frame: magic (4), id length (1), session ID, IV (12), and GCM tag (16).
assert.equal(
    deletionSummary.encryptedPayloadBytes,
    5 + Buffer.byteLength(actualRequest.cryptoSessionId) + 12 + deletionSummary.patchPayloadBytes + 16
);
assert.match(source, /function showCopyableFilePanelSaveConfirmation\(message\)/);
assert.match(source, /data-action="copy">내용 복사<\/button>/);
assert.match(source, /예상 업로드\(요청 본문\)/);
const saved = restore('a\r\nb\r\n', 'a\nB\n');
const savedAgain = restore(saved, 'A\nB\n');
assert.equal(savedAgain, 'A\r\nB\r\n');
assert.equal(apply(saved, build(saved, savedAgain)), savedAgain);
console.log('PASS: change summary and consecutive CRLF saves');
