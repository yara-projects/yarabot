// Execute the actual feedback UI with synthetic responses, no browser/network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8').match(/function attachAnswerFeedback\(bubble, response\) \{[\s\S]*?\n\}/)[0];
function node(tag) {
    return {tag, children: [], disabled: false, isConnected: true, textContent: '',
        setAttribute() {}, appendChild(child) { this.children.push(child); },
        querySelectorAll(tag) { return this.children.filter(child => child.tag === tag); },
        addEventListener(_, action) { this.action = action; }};
}
async function check(statusCode, throws = false) {
    let expired = 0;
    const bubble = node('div');
    const context = vm.createContext({chatSessionGeneration: 1,
        document: {createElement: node}, handleSessionExpired() { expired++; },
        fetch: async () => { if (throws) throw Error('offline'); return {ok: statusCode === 200, status: statusCode}; }});
    vm.runInContext(source, context);
    context.bubble = bubble;
    vm.runInContext("attachAnswerFeedback(bubble, {headers:{get:()=> 'synthetic-token'}})", context);
    const controls = bubble.children[0], buttons = controls.querySelectorAll('button');
    await buttons[0].action();
    const text = controls.children[2].textContent;
    if (statusCode === 401) assert.equal(expired, 1);
    else assert.equal(expired, 0);
    if (statusCode === 403) assert.match(text, /earlier session/);
    if (statusCode === 200) assert.match(text, /Thanks/);
    if (statusCode === 409) assert.match(text, /already recorded/);
    if ([200, 401, 403, 409].includes(statusCode)) assert(buttons.every(button => button.disabled));
    else assert(buttons.every(button => !button.disabled));
    console.log('PASS feedback', throws ? 'network failure' : statusCode);
}
(async () => {
    for (const code of [200, 401, 403, 409, 429, 503]) await check(code);
    await check(0, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
