// Execute the real UI functions with controllable network completion order.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; }
function ui() {
    const nodes = new Map();
    const node = id => {
        if (!nodes.has(id)) nodes.set(id, {value:'', disabled:false, innerHTML:'', textContent:'', style:{}, classList:{add(){},remove(){},toggle(){}},focus(){},hasChildNodes(){return true;}});
        return nodes.get(id);
    };
    const ctx = vm.createContext({document:{getElementById:node,addEventListener(){},querySelectorAll(){return [];},documentElement:{}},window:{addEventListener(){}},console,AbortController,TextDecoder,setTimeout,clearTimeout,history:{replaceState(){}},fetch:async()=>({ok:true}),alert(){}});
    vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
    vm.runInContext(`autoResize=()=>{}; mountBotLottie=()=>{}; cleanupDetachedLottie=()=>{}; closeSidebar=()=>{}; initKillSwitch=()=>{}; checkNotificationsCount=()=>{}; checkComplaintsNotificationsCount=()=>{}; checkComplaintDot=()=>{}; buildIDCard=()=>{}; showTypingBubble=()=>{}; removeTypingBubble=()=>{}; renderGreeting=()=>{}; buildQuickActions=()=>{}; appendMessage=(role,text)=>{document.getElementById('chat-messages').innerHTML += role+':'+text+'\\n';};`,ctx);
    return {ctx,node,run:s=>vm.runInContext(s,ctx)};
}
async function lateJSON() {
    const u=ui(), reply=deferred();
    u.run("userRole='principal'; currentProfile={name:'Principal'}; messageCount=1;");
    u.ctx.fetch=async url=>url==='/api/chat'?{status:200,headers:{get(){return 'application/json';}},json:()=>reply.promise}:{ok:true};
    u.node('chat-input').value='pending fees 10a';
    const pending=u.run('sendMessage()');
    await new Promise(r=>setImmediate(r));
    await u.run('handleLogout()');
    u.run("userRole='guest';showChatPage({name:'Guest'});");
    reply.resolve({reply:'PRIVATE PRINCIPAL REPORT'}); await pending;
    assert(!u.node('chat-messages').innerHTML.includes('PRIVATE'),'late JSON leaked to guest');
    assert(!u.node('chat-messages').innerHTML.includes('pending fees'),'old user history survived logout');
}
async function lateStream() {
    const u=ui(), chunk=deferred(); let read=0;
    u.run("userRole='principal';currentProfile={name:'Principal'};messageCount=1;");
    u.ctx.fetch=async url=>url==='/api/chat'?{status:200,headers:{get(){return 'text/event-stream';}},body:{getReader(){return {read:()=>read++?Promise.resolve({done:true}):chunk.promise,cancel:async()=>{}};}}}:{ok:true};
    u.node('chat-input').value='list students with low attendance';
    const pending=u.run('sendMessage()'); await new Promise(r=>setImmediate(r));
    await u.run('handleLogout()');u.run("userRole='guest';showChatPage({name:'Guest'});");
    u.ctx.marked={parse:x=>x};u.run("buildMessageWrapper=()=>{document.getElementById('chat-messages').innerHTML='PRIVATE';return {innerHTML:''};}");
    chunk.resolve({value:new TextEncoder().encode('data: {"chunk":"PRIVATE"}\n\n'),done:false});await pending;
    assert(!u.node('chat-messages').innerHTML.includes('PRIVATE'),'late stream leaked to guest');
}
function parentChips() {
    const u=ui();u.run("userRole='parent';buildQuickActions="+fs.readFileSync('static/app.js','utf8').match(/function buildQuickActions\(\) \{[\s\S]*?\n\}/)[0].replace('function buildQuickActions','function')+';buildQuickActions();');
    const html=u.node('quick-actions').innerHTML;
    assert(html,'parent chips missing');
    for(const match of html.matchAll(/onclick="([^"]*)"/g)) new vm.Script(match[1]);
}
(async()=>{let failed=0;for(const test of [lateJSON,lateStream,parentChips]){try{await test();console.log('PASS',test.name);}catch(e){failed++;console.error('FAIL',test.name,e.message);}}process.exitCode=failed?1:0;})();
