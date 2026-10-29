'use strict';
// Native asynchronous Web Crypto; keys live only in this page's memory.
class ChatTransport {
 constructor(url, csrf) { this.url=url; this.csrf=csrf; this.channel=null; this.opening=null; this.encoder=new TextEncoder(); this.decoder=new TextDecoder(); }
 bytes(value) { return Uint8Array.from(atob(value), c=>c.charCodeAt(0)); }
 base64(value) { const bytes=new Uint8Array(value); let result=''; for(let i=0;i<bytes.length;i+=8192)result+=String.fromCharCode(...bytes.subarray(i,i+8192)); return btoa(result); }
 async json(response) {
  const raw=await response.text();
  if(/^\s*</.test(raw))throw new Error(`API가 HTML을 반환했습니다 (HTTP ${response.status}). 접속 주소와 게이트웨이 로그인을 확인해 주세요.`);
  let data;try{data=JSON.parse(raw);}catch{throw new Error(`API 응답을 읽을 수 없습니다 (HTTP ${response.status}).`);}
  if(!response.ok){const error=new Error(data.error||`요청 실패 (${response.status})`);error.code=data.code;throw error;}
  return data;
 }
 async channelForRequest() {
  if(!globalThis.isSecureContext||!globalThis.crypto?.subtle)throw new Error('암호화에는 HTTPS 접속이 필요합니다. HTTPS 게이트웨이 주소로 접속해 주세요. 로컬에서는 localhost를 사용할 수 있습니다.');
  if(this.channel&&this.channel.expires>Date.now()+30000)return this.channel;
  if(this.opening)return this.opening;
  this.opening=this.handshake();
  try{return this.channel=await this.opening;}finally{this.opening=null;}
 }
 async handshake() {
  const subtle=crypto.subtle;
  const pair=await subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
  const publicKey=await subtle.exportKey('raw',pair.publicKey);
  const data=await this.json(await fetch(this.url('/api/crypto-session'),{method:'POST',credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-Chat-CSRF':this.csrf},body:JSON.stringify({client_public_key:this.base64(publicKey)})}));
  if(data.algorithm!=='ECDH-P256-HKDF-SHA256-AES-256-GCM')throw new Error('지원하지 않는 암호화 연결입니다.');
  const remote=await subtle.importKey('raw',this.bytes(data.server_public_key),{name:'ECDH',namedCurve:'P-256'},false,[]);
  const shared=await subtle.deriveBits({name:'ECDH',public:remote},pair.privateKey,256);
  const seed=await subtle.importKey('raw',shared,'HKDF',false,['deriveBits']);new Uint8Array(shared).fill(0);
  const material=new Uint8Array(await subtle.deriveBits({name:'HKDF',hash:'SHA-256',salt:this.bytes(data.salt),info:this.encoder.encode('workbench-conversation-transport-v1')},seed,512));
  try{return {id:data.crypto_session_id,expires:data.expires_at*1000,
   requestKey:await subtle.importKey('raw',material.subarray(0,32),'AES-GCM',false,['encrypt']),
   responseKey:await subtle.importKey('raw',material.subarray(32),'AES-GCM',false,['decrypt'])};
  }finally{material.fill(0);}
 }
 async seal(channel,payload) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:this.encoder.encode(channel.id+':request')},channel.requestKey,this.encoder.encode(JSON.stringify(payload)));
  return {encrypted:true,crypto_session_id:channel.id,iv:this.base64(iv),ciphertext:this.base64(ciphertext)};
 }
 async unseal(channel,requestIv,envelope,seq=0) {
  if(envelope.encrypted!==true||envelope.crypto_session_id!==channel.id||envelope.seq!==seq)throw new Error('암호화 응답 순서 또는 세션이 올바르지 않습니다.');
  try{const raw=await crypto.subtle.decrypt({name:'AES-GCM',iv:this.bytes(envelope.iv),additionalData:this.encoder.encode(`${channel.id}:response:${requestIv}:${seq}`)},channel.responseKey,this.bytes(envelope.ciphertext));return JSON.parse(this.decoder.decode(raw));}
  catch{throw new Error('암호화 응답 검증에 실패했습니다. 전송을 중단했습니다.');}
 }
 async open(path,method,body,signal,retry=true) {
  const channel=await this.channelForRequest(),envelope=await this.seal(channel,{path,method,body});
  const response=await fetch(this.url('/api/secure'),{method:'POST',credentials:'same-origin',cache:'no-store',signal,headers:{'Content-Type':'application/json','X-Chat-CSRF':this.csrf},body:JSON.stringify(envelope)});
  if(!response.ok){try{await this.json(response);}catch(error){
   // Expiration is rejected before dispatch, so retry cannot repeat a mutation.
   if(retry&&error.code==='crypto_session_expired'){if(this.channel===channel)this.channel=null;return this.open(path,method,body,signal,false);}throw error;
  }}
  return {channel,envelope,response};
 }
 async request(path,method='GET',body,signal) {
  const {channel,envelope,response}=await this.open(path,method,body,signal);
  const result=await this.unseal(channel,envelope.iv,await this.json(response));
  if(result.status>=400)throw new Error(result.body.error||`요청 실패 (${result.status})`);
  return result.body;
 }
 async *stream(path,signal,timeoutMs=15000) {
  const controller=new AbortController();let timer;
  const abort=()=>controller.abort(signal.reason);
  const reset=()=>{clearTimeout(timer);timer=setTimeout(()=>controller.abort(new Error('이벤트 수신 시간이 초과되었습니다.')),timeoutMs);};
  if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
  reset();
  try{yield* this.readStream(path,controller.signal,reset);}
  finally{clearTimeout(timer);signal.removeEventListener('abort',abort);controller.abort();}
 }
 async *readStream(path,signal,received) {
  const {channel,envelope,response}=await this.open(path,'GET',undefined,signal);
  if(!response.headers.get('Content-Type')?.startsWith('text/event-stream')){
   const result=await this.unseal(channel,envelope.iv,await this.json(response));throw new Error(result.body?.error||'이벤트 연결을 열 수 없습니다.');
  }
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='',seq=0;
  try{while(true){const {value,done}=await reader.read();if(done){if(pending.trim())throw new Error('이벤트 응답이 중간에 끊겼습니다.');return;}
   pending+=decoder.decode(value,{stream:true});if(pending.length>4*1024*1024)throw new Error('이벤트 크기 제한을 초과했습니다.');
   let end;while((end=pending.indexOf('\n\n'))!==-1){const frame=pending.slice(0,end);pending=pending.slice(end+2);if(!frame.startsWith('data: '))throw new Error('암호화 이벤트 형식이 올바르지 않습니다.');
    const data=await this.unseal(channel,envelope.iv,JSON.parse(frame.slice(6)),seq++);received();yield data.chunk;
   }
  }}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
 }
}
