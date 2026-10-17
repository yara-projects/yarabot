// Real UI functions, synthetic DOM/network/viewport. No providers or school DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
    class Element {
        constructor() {
            this.children = []; this.attributes = {}; this.isConnected = true;
            this.textContent = ''; this.disabled = false; this.events = {};
            this.scrollHeight = 1000; this.scrollTop = 300; this.clientHeight = 400;
            const classes = new Set();
            this.classList = {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x)};
        }
        setAttribute(key, value) { this.attributes[key] = value; }
        appendChild(child) { this.children.push(child); }
        addEventListener(key, fn) { this.events[key] = fn; }
        querySelectorAll(selector) { return selector === 'button' ? this.children : []; }
        querySelector(selector) { return this.children.find(x => selector === '.' + x.className) || null; }
    }
    const nodes = new Map();
    const node = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
    const timers = new Map(); let nextTimer = 0; let scrollCalls = 0;
    const properties = {};
    const viewport = {height: 800, scale: 1, addEventListener(key, fn) {this[key] = fn;}};
    const context = vm.createContext({
        document: {createElement: () => new Element(), getElementById: node, addEventListener() {},
            activeElement: null, documentElement: {style: {setProperty: (key, value) => properties[key] = value}}},
        window: {visualViewport: viewport, addEventListener() {}, scrollTo() { scrollCalls++; }},
        setTimeout: fn => { timers.set(++nextTimer, fn); return nextTimer; },
        clearTimeout: id => timers.delete(id), console, fetch: async () => ({ok: true, status: 200})
    });
    vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
    return {context, node, viewport, properties, timers, scrollCalls: () => scrollCalls,
        run: code => vm.runInContext(code, context), bubble: new Element()};
}
function feedback(u) {
    u.context.bubble = u.bubble;
    u.context.response = {headers: {get: key => key === 'X-Answer-ID' ? 'sample-answer' : 'sample-csrf'}};
    u.run('attachAnswerFeedback(bubble, response)');
    return u.bubble.children[0].children;
}
async function feedbackOnceAndToast() {
    const u = fixture(); let calls = 0; let finish;
    u.context.fetch = () => {calls++; return new Promise(resolve => finish = resolve);};
    const [up, down] = feedback(u);
    u.run('attachAnswerFeedback(bubble, response)');
    assert.equal(u.bubble.children.length, 1);
    const pending = up.events.click();
    assert(up.classList.contains('is-selected')); assert.equal(up.attributes['aria-pressed'], 'true');
    await down.events.click(); await up.events.click(); assert.equal(calls, 1);
    finish({ok: true, status: 200}); await pending;
    assert.equal(u.node('feedback-toast').textContent, 'Thanks for your feedback.');
    assert(u.node('feedback-toast').classList.contains('is-visible'));
    assert.equal(u.bubble.children[0].children.length, 2, 'no permanent thank-you inside answer');
    await up.events.click(); assert.equal(calls, 1);
    for (const fn of [...u.timers.values()]) fn();
    assert.equal(u.node('feedback-toast').textContent, '');
    assert(!u.node('feedback-toast').classList.contains('is-visible'));
}
async function failedVoteCanRetry() {
    const u = fixture(); const [up, down] = feedback(u);
    u.context.fetch = async () => {throw new Error('offline');};
    await up.events.click();
    assert(!up.disabled); assert(!down.disabled); assert(!up.classList.contains('is-selected'));
    u.context.fetch = async () => ({ok: true, status: 200});
    await down.events.click(); assert(down.classList.contains('is-selected'));
    assert(!up.classList.contains('is-selected'));
}
async function expiredAnswerDoesNotClaimSaved() {
    for (const status of [403, 409]) {
        const u = fixture(); const [up] = feedback(u);
        u.context.fetch = async () => ({ok: false, status});
        await up.events.click(); assert(up.disabled);
        assert(!up.classList.contains('is-selected'));
        assert(!u.node('feedback-toast').textContent.includes('Thanks'));
    }
}
async function staleVoteDoesNotToast() {
    const u = fixture(); let finish; const [up] = feedback(u);
    u.context.fetch = () => new Promise(resolve => finish = resolve);
    const pending = up.events.click();
    u.run('chatSessionGeneration++');
    finish({ok: true, status: 200}); await pending;
    assert.equal(u.node('feedback-toast').textContent, '');
}
function pinchZoomDoesNotResizeOrScroll() {
    const u = fixture(); u.run('initViewportHeightFix()');
    assert.equal(u.properties['--vvh'], '800px');
    u.viewport.scale = 2; u.viewport.height = 400; u.viewport.resize();
    assert.equal(u.properties['--vvh'], '800px');
    assert.equal(u.node('chat-messages').scrollTop, 300); assert.equal(u.scrollCalls(), 0);
    u.viewport.scale = 1; u.viewport.resize(); assert.equal(u.properties['--vvh'], '400px');
    assert.equal(u.node('chat-messages').scrollTop, 300);
}
function keyboardResizesWithoutDiscardingReadingPosition() {
    const u = fixture(); u.context.document.activeElement = u.node('chat-input');
    u.run('initViewportHeightFix()');
    u.viewport.height = 450; u.viewport.resize();
    assert.equal(u.properties['--vvh'], '450px'); assert.equal(u.node('chat-messages').scrollTop, 300);
    u.node('chat-messages').scrollTop = 600; u.viewport.height = 800; u.viewport.resize();
    assert.equal(u.properties['--vvh'], '800px'); assert.equal(u.node('chat-messages').scrollTop, 1000);
    u.viewport.height = 0; u.viewport.resize(); assert.equal(u.properties['--vvh'], '800px');
}
(async () => {
    for (const test of [feedbackOnceAndToast, failedVoteCanRetry, expiredAnswerDoesNotClaimSaved,
        staleVoteDoesNotToast, pinchZoomDoesNotResizeOrScroll, keyboardResizesWithoutDiscardingReadingPosition]) {
        await test(); console.log('PASS', test.name);
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
