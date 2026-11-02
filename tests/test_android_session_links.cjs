// Exercise production session selection/detail loading without starting a real Codex task.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../codex-web-app/static/js/app.js'),'utf8');
function production(start,end){return source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));}
async function scenario({query='',stored=null,active=null,explicit=null,storageFails=false}){
 const location=new URL('https://current.trycloudflare.com/dev/?keep=1'+query+'#thread');
 const values=new Map(stored?[['codex-active-session:/dev/',stored]]:[]),errors=[];
 const context={URL,URLSearchParams,console,Date,Promise,location,
  state:{loading:false,sessions:[],activeSessionId:active},sessionLoadLockStartedAt:0,
  REFRESH_BUTTON_STALE_MS:1000,SESSION_LIST_REQUEST_TIMEOUT_MS:1000,SESSION_DETAIL_REQUEST_TIMEOUT_MS:1000,
  sessionStorage:{getItem:k=>{if(storageFails)throw Error('storage disabled');return values.get(k)||null;},setItem:(k,v)=>{if(storageFails)throw Error('storage disabled');values.set(k,v);}},
  history:{state:null,replaceState:(_,__,url)=>{location.href=url.href;}},
  fetchChatResponseJson:async url=>url==='/api/codex/sessions'?{sessions:[{id:'recent'},{id:'completed'}]}:{session:{id:url.split('/').pop(),messages:[]}},
  normalizeError:e=>e.message,setStatus:(_,failed)=>{if(failed)errors.push(_);},
 };
 for(const name of ['updateSessionStorageSummary','ensureSessionState','renderSessions','updateHeader','renderMessages','updateChatSessionNavigationButtons','syncActiveSessionControls','syncActiveSessionStatus','upsertSessionSummary','syncSessionPendingQueue','detachSessionStreamEntry','attachSessionStreamEntry','maybeAttachRemoteStreamToActiveSession','showToast'])context[name]=()=>{};
 vm.createContext(context);
 vm.runInContext(production('async function loadSessions(', '\nfunction normalizeCodexAccountsSummary')+'\n'+production('async function loadSession(sessionId)', '\nfunction renderMessages('),context);
 await context.loadSessions({selectSessionId:explicit});
 assert.deepEqual(errors,[]);
 assert.equal(location.searchParams.get('session'),null);
 assert.equal(location.searchParams.get('keep'),'1');
 assert.equal(location.hash,'#thread');
 return {selected:context.state.activeSessionId,stored:values.get('codex-active-session:/dev/')};
}
(async()=>{
 assert.equal((await scenario({query:'&session=completed',active:'recent'})).selected,'completed');
 assert.equal((await scenario({query:'&session=deleted'})).selected,'recent');
 assert.equal((await scenario({stored:'completed'})).selected,'completed');
 assert.equal((await scenario({stored:'completed',active:'recent'})).selected,'recent');
 assert.equal((await scenario({query:'&session=recent',explicit:'completed'})).stored,'completed');
 assert.equal((await scenario({storageFails:true})).selected,'recent');
 console.log('PASS 6 work-session cases: notification link, missing session, resume, active selection, explicit selection, unavailable storage');
})().catch(error=>{console.error(error);process.exitCode=1;});
