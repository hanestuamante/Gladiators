from __future__ import annotations


FLOW_UI = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gladiators · Luồng xử lý live</title>
<style>
:root{color-scheme:dark;--bg:#08111f;--panel:#101c2e;--line:#26364d;--text:#edf3fb;--muted:#9dafc7;--accent:#72e6c1;--warn:#ffc86b;--danger:#ff7a7a}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font:14px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 15% 0,#17334b 0,transparent 35%),var(--bg)}
main{width:min(1180px,calc(100% - 32px));margin:32px auto}
header{margin-bottom:18px}
h1{margin:0 0 4px;font-size:clamp(22px,4vw,32px);letter-spacing:-.03em}
header p,.muted{color:var(--muted)}
a{color:var(--accent)}
.card{padding:18px;border:1px solid var(--line);border-radius:16px;background:#101c2eee;box-shadow:0 20px 60px #0005;margin-bottom:16px}
form{display:flex;gap:10px}
textarea{width:100%;min-height:64px;resize:vertical;padding:12px 14px;border:1px solid var(--line);border-radius:10px;color:var(--text);background:#091525;font:inherit;outline:none}
textarea:focus{border-color:var(--accent)}
button{align-self:stretch;min-width:110px;border:0;border-radius:10px;padding:0 16px;background:var(--accent);color:#062018;font-weight:750;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
.examples{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:#142238;color:var(--muted);font-weight:500;font-size:12.5px;cursor:pointer}
.chip:hover{color:var(--text);border-color:#49617f}

.flow{display:flex;flex-wrap:wrap;align-items:center;gap:0;padding:8px 0}
.node{min-width:150px;max-width:200px;padding:10px 12px;border:1.5px solid var(--line);border-radius:12px;background:#0b1728;transition:all .25s ease;opacity:.4}
.node .label{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:700}
.node .fact{margin-top:5px;font-size:12.5px;word-break:break-word}
.node .fact b{color:var(--text)}
.node.pending{opacity:.35}
.node.active{opacity:1;border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset,0 8px 24px #72e6c122}
.node.warn{opacity:1;border-color:var(--warn);box-shadow:0 0 0 1px var(--warn) inset}
.node.danger{opacity:1;border-color:var(--danger);box-shadow:0 0 0 1px var(--danger) inset}
.node.skipped{opacity:.25}
.node.skipped .fact{color:var(--muted)}
.arrow{width:26px;text-align:center;color:var(--muted);font-size:16px;opacity:.4;transition:all .25s ease}
.arrow.active{color:var(--accent);opacity:1}
.arrow.warn{color:var(--warn);opacity:1}
.arrow.danger{color:var(--danger);opacity:1}
.arrow.skipped{opacity:.2}
.loop-note{width:100%;text-align:center;font-size:11px;color:var(--muted);padding:2px 0 10px}
.loop-note.active{color:var(--warn)}

#answerbox{display:none}
.status{display:inline-block;padding:3px 9px;border-radius:999px;background:#183b35;color:var(--accent);font-size:11px;font-weight:800;text-transform:uppercase}
.status.warn{background:#45351c;color:var(--warn)}
.status.danger{background:#452020;color:var(--danger)}
#answer{white-space:pre-wrap;font-size:15px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin-top:8px}
.evidence{padding:10px;border:1px solid var(--line);border-radius:10px;background:#0b1728;font-size:12.5px}
.evidence strong{color:var(--accent);font-size:12px}
details{margin-top:12px;color:var(--muted)}
pre{overflow:auto;white-space:pre-wrap;font-size:11.5px}
.gbox{margin-top:12px;border:1px solid var(--line);border-radius:12px;background:#0b1728;padding:12px}
.gbox h4{margin:0 0 8px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.grow{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;margin-bottom:4px}
.gtag{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:700;font-size:11px}
.gtag.ok{background:#183b35;color:var(--accent)}
.gtag.bad{background:#452020;color:var(--danger)}
.gtag.warn{background:#45351c;color:var(--warn)}
.gitem{font-size:12px;color:var(--text);margin:2px 0 2px 4px}
.gitem.bad{color:var(--danger)}
.gitem.mut{color:var(--muted)}
@media(max-width:720px){form{display:block}button{width:100%;height:44px;margin-top:8px}.node{min-width:130px}}
</style></head><body><main>
<header><div class="muted">GLADIATORS V2 · LUỒNG XỬ LÝ LIVE</div><h1>Xem agent chạy qua từng cổng.</h1>
<p>Gõ câu hỏi — sơ đồ diễn lại đúng dữ liệu thật trả về từ <code>/ask</code>: parser, gate, tool, evidence, và guardrail chống-hallucination (bộ kiểm số, cổng từ ngữ, fallback). Câu analytical còn hiện <b>Planner path</b>: risk score → critic/N-version. Xem trang form đơn giản tại <a href="/">/</a>.</p>
</header>

<section class="card"><form id="ask"><textarea id="question" maxlength="4000" autofocus placeholder="Ví dụ: Voucher ở VN có hiệu quả không?"></textarea><button id="submit">Chạy</button></form>
<div class="examples" id="examples">
<span class="chip">Ngày nào doanh thu cao nhất tại VN?</span>
<span class="chip">Có bao nhiêu listing tại VN?</span>
<span class="chip">Shop nào có nhiều listing nhất tại VN?</span>
<span class="chip">Voucher ở VN có hiệu quả không?</span>
<span class="chip">Shop nào có chiến lược voucher hiệu quả nhất VN?</span>
<span class="chip">Lợi nhuận công ty là bao nhiêu?</span>
</div></section>

<section class="card">
  <div class="flow" id="flow">
    <div class="node pending" id="n-input"><div class="label">1 · User Input</div><div class="fact" id="f-input">chưa có câu hỏi</div></div>
    <div class="arrow" id="a-1">→</div>
    <div class="node pending" id="n-parser"><div class="label">2 · Parser</div><div class="fact" id="f-parser">regex, không gọi LLM</div></div>
    <div class="arrow" id="a-2">→</div>
    <div class="node pending" id="n-gate"><div class="label">3 · Gate</div><div class="fact" id="f-gate">chờ dữ liệu</div></div>
    <div class="arrow" id="a-3">→</div>
    <div class="node pending skipped" id="n-entity"><div class="label">4 · Entity Resolution</div><div class="fact" id="f-entity">—</div></div>
    <div class="arrow skipped" id="a-4">→</div>
    <div class="node pending skipped" id="n-tool"><div class="label">5 · Tool Call</div><div class="fact" id="f-tool">—</div></div>
    <div class="arrow skipped" id="a-5">→</div>
    <div class="node pending skipped" id="n-evidence"><div class="label">6 · Evidence</div><div class="fact" id="f-evidence">—</div></div>
    <div class="arrow skipped" id="a-6">→</div>
    <div class="node pending skipped" id="n-generation"><div class="label">7 · Generation loop</div><div class="fact" id="f-generation">—</div></div>
    <div class="arrow skipped" id="a-7">⇄</div>
    <div class="node pending skipped" id="n-verifier"><div class="label">8 · Verifier</div><div class="fact" id="f-verifier">—</div></div>
    <div class="arrow" id="a-8">→</div>
    <div class="node pending" id="n-output"><div class="label">9 · Output</div><div class="fact" id="f-output">—</div></div>
    <div class="loop-note" id="loop-note"></div>
  </div>
</section>

<section id="answerbox" class="card"><span id="status" class="status"></span><p id="answer"></p><div id="guardrails"></div><div id="planning"></div><h3 style="margin:14px 0 4px">Evidence</h3><div id="evidence" class="grid"></div><details><summary>JSON đầy đủ</summary><pre id="raw"></pre></details></section>

</main><script>
const $=s=>document.querySelector(s);
const form=$('#ask'),input=$('#question'),submit=$('#submit');
document.querySelectorAll('.chip').forEach(x=>x.onclick=()=>{input.value=x.textContent;input.focus()});

const NODES=['input','parser','gate','entity','tool','evidence','generation','verifier','output'];
const ARROWS=['a-1','a-2','a-3','a-4','a-5','a-6','a-7','a-8'];

function resetFlow(){
  NODES.forEach(n=>{const el=$('#n-'+n);el.className='node pending'+(['entity','tool','evidence','generation','verifier'].includes(n)?' skipped':'')});
  ARROWS.forEach(a=>{$('#'+a).className='arrow'+(['a-4','a-5','a-6','a-7'].includes(a)?' skipped':'')});
  $('#loop-note').textContent='';$('#loop-note').className='loop-note';
  $('#answerbox').style.display='none';
}

function setNode(id,cls,fact){
  const el=$('#n-'+id);el.className='node active'+(cls?(' '+cls):'');
  if(fact!==undefined)$('#f-'+id).innerHTML=fact;
}
function setArrow(id,cls){$('#'+id).className='arrow active'+(cls?(' '+cls):'')}
function skipNode(id,label){const el=$('#n-'+id);el.className='node skipped';$('#f-'+id).textContent=label||'bỏ qua — gate chặn';}
function skipArrow(id){$('#'+id).className='arrow skipped'}

function wait(ms){return new Promise(r=>setTimeout(r,ms))}
function esc(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function gateCls(action){return action==='allow'?'':(action==='clarify'?'warn':'danger')}
function caughtFrom(gen){
  const out={unsupported:[],unknown_citations:[],wording:[]};
  (gen.errors||[]).forEach(e=>{
    (e.unsupported||[]).forEach(x=>out.unsupported.push(x));
    (e.unknown_citations||[]).forEach(x=>out.unknown_citations.push(x));
    (e.wording||[]).forEach(x=>out.wording.push(x.rule?(x.rule+' ('+x.term+')'):x));
  });
  return out;
}

async function run(text){
  resetFlow();
  setNode('input',null,'<b>'+esc(text)+'</b>');
  await wait(250);

  let data,res;
  try{
    res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    data=await res.json();
  }catch(err){
    setNode('parser','danger','fetch lỗi: '+esc(err.message));return;
  }
  if(!res.ok){setNode('parser','danger','HTTP '+res.status+': '+esc(JSON.stringify(data.detail||data)));return}

  setArrow('a-1');
  await wait(280);
  const r=data.request||{};
  setNode('parser',null,'intent=<b>'+esc(r.intent)+'</b><br>entity=<b>'+esc(r.entity_text??'null')+'</b><br>country=<b>'+esc(r.country??'null')+'</b>');
  setArrow('a-2');
  await wait(320);

  const g=data.gate||{};
  const gcls=gateCls(g.action);
  setNode('gate',gcls,'<b>'+esc(g.action)+'</b> ('+esc(g.rule_id)+')<br>'+esc(g.reason));

  if(g.action!=='allow'){
    setArrow('a-3',gcls);
    ['entity','tool','evidence','generation','verifier'].forEach(n=>skipNode(n));
    ['a-4','a-5','a-6','a-7'].forEach(skipArrow);
    await wait(280);
    setArrow('a-8',gcls);
    await wait(280);
    setNode('output',gcls,esc((data.answer||'').slice(0,140))+((data.answer||'').length>140?'…':''));
    renderAnswer(data);
    return;
  }

  setArrow('a-3');
  await wait(300);

  if(r.entity_text && data.resolved_listing_key){
    setNode('entity',null,'resolved_listing_key=<br><b>'+esc(data.resolved_listing_key)+'</b>');
  } else {
    skipNode('entity','không cần resolve cho intent này');
  }
  setArrow('a-4');
  await wait(280);

  const calls=data.tool_calls||[];
  if(calls.length){
    const c=calls[calls.length-1];
    setNode('tool',c.status==='ok'?null:'warn','<b>'+esc(c.name)+'</b>('+esc(JSON.stringify(c.args))+')<br>status=<b>'+esc(c.status)+'</b>');
  } else {
    skipNode('tool');
  }
  setArrow('a-5');
  await wait(300);

  const ev=data.evidence||[];
  setNode('evidence',ev.length?null:'warn',ev.length+' evidence thu được'+(ev.length?('<br>vd: <b>'+esc(ev[0].metric)+'</b>='+esc(ev[0].value)):''));
  setArrow('a-6');
  await wait(300);

  const gen=(data.llm&&data.llm.generation)||{};
  const provider=(data.llm&&data.llm.provider)||'deterministic';
  const caught=caughtFrom(gen);
  const nCaught=caught.unsupported.length+caught.unknown_citations.length+caught.wording.length;
  const genFact=provider==='deterministic'
    ? 'provider=<b>'+esc(provider)+'</b><br>dùng template có sẵn'
    : 'provider=<b>'+esc(provider)+'</b><br>attempts='+esc(gen.attempts)+' fallback=<b>'+esc(gen.fallback)+'</b>'
      +(gen.fallback?'<br>→ rơi về deterministic':'');
  setNode('generation',gen.fallback?'warn':null,genFact);
  setArrow('a-7');
  await wait(300);

  const v=data.verification||{};
  const uc=v.unknown_citations||[],us=v.unsupported||[];
  const vBad=v.passed===false||uc.length||us.length;
  let vFact='passed=<b>'+esc(v.passed)+'</b><br>coverage='+esc(v.coverage);
  if(uc.length)vFact+='<br><b>citation bịa:</b> '+esc(uc.join(', '));
  if(us.length)vFact+='<br><b>số không có evidence:</b> '+esc(us.join(', '));
  if(nCaught&&v.passed!==false)vFact+='<br>đã chặn '+nCaught+' claim trước khi chốt';
  setNode('verifier',vBad?'danger':(nCaught?'warn':null),vFact);
  if(gen.attempts>1||vBad||nCaught){
    $('#loop-note').textContent='⟲ generation ↔ verifier lặp lại '+(gen.attempts||1)+' lần'
      +(nCaught?(' — chặn '+nCaught+' claim (số/citation/wording)'):'')+' trước khi chốt câu trả lời';
    $('#loop-note').className='loop-note active';
  }
  await wait(280);

  setArrow('a-8');
  await wait(280);
  setNode('output',data.degraded?'warn':null,esc((data.answer||'').slice(0,140))+((data.answer||'').length>140?'…':''));
  renderAnswer(data);
}

function renderAnswer(data){
  const action=data.gate?.action||'unknown';
  const badge=$('#status');
  badge.textContent=action+(data.degraded?' · degraded':'');
  badge.className='status'+(action==='allow'?(data.degraded?' warn':''):(action==='clarify'?' warn':' danger'));
  $('#answer').textContent=data.answer;
  const box=$('#evidence');box.innerHTML='';
  (data.evidence||[]).forEach(ev=>{
    const el=document.createElement('div');el.className='evidence';
    const p=ev.provenance;
    el.innerHTML='<strong>'+esc(ev.metric)+'</strong><br>'+esc(ev.value)+' '+esc(ev.unit||'')+'<br><small class="muted">'+esc(ev.evidence_id)+' · '+esc(ev.source_tier)+(p?(' · '+esc(p.source_id)+' · lấy '+esc(p.retrieved_at)):'')+'</small>';
    box.appendChild(el);
  });
  if(!data.evidence?.length)box.innerHTML='<span class="muted">Không có evidence cho phản hồi này.</span>';
  renderGuardrails(data);
  renderPlanning(data);
  $('#raw').textContent=JSON.stringify(data,null,2);
  $('#answerbox').style.display='block';
}

function tag(cls,text){return '<span class="gtag '+cls+'">'+esc(text)+'</span>'}

function renderGuardrails(data){
  const el=$('#guardrails'); el.innerHTML='';
  const v=data.verification||{};
  if(v.disabled){return}
  const gen=(data.llm&&data.llm.generation)||{};
  const caught=caughtFrom(gen);
  const rows=[];
  // Numeric verifier
  const numTag=v.passed===false?tag('bad','FAIL'):tag('ok','PASS');
  rows.push('<div class="grow">Bộ kiểm số: '+numTag
    +' <span class="mut">coverage='+esc(v.coverage)+'</span></div>');
  (v.unsupported||[]).forEach(x=>rows.push('<div class="gitem bad">• số không có evidence: '+esc(x)+'</div>'));
  (v.unknown_citations||[]).forEach(x=>rows.push('<div class="gitem bad">• citation bịa: '+esc(x)+'</div>'));
  // Wording gate
  if(caught.wording.length){
    rows.push('<div class="grow">Cổng từ ngữ: '+tag('warn','ĐÃ CHẶN '+caught.wording.length)+'</div>');
    caught.wording.forEach(x=>rows.push('<div class="gitem bad">• '+esc(x)+'</div>'));
  }else{
    rows.push('<div class="grow">Cổng từ ngữ: '+tag('ok','SẠCH')+' <span class="mut">không có câu nhân quả/forecast/cùng-SKU</span></div>');
  }
  // Generation fallback
  if(gen.fallback){
    rows.push('<div class="grow">Sinh câu trả lời: '+tag('warn','FALLBACK')
      +' <span class="mut">LLM bị từ chối sau '+esc(gen.attempts)+' lần → dùng câu deterministic đã verify</span></div>');
  }else if(gen.attempts>0){
    rows.push('<div class="grow">Sinh câu trả lời: '+tag('ok','LLM qua verify')+' <span class="mut">attempts='+esc(gen.attempts)+'</span></div>');
  }
  el.innerHTML='<div class="gbox"><h4>Guardrails chống-hallucination</h4>'+rows.join('')+'</div>';
}

function renderPlanning(data){
  const el=$('#planning'); el.innerHTML='';
  const p=data.planning||{};
  if(!p.mode||p.mode==='none'){return}
  const rows=[];
  rows.push('<div class="grow">mode=<b>'+esc(p.mode)+'</b>'
    +(p.complexity_level?(' · complexity='+esc(p.complexity_level)):'')
    +(p.plan_id?(' · <span class="mut">'+esc(p.plan_id)+'</span>'):'')+'</div>');
  if(p.risk_score!==undefined){
    rows.push('<div class="grow">risk_score=<b>'+esc(p.risk_score)+'</b>'
      +' · yêu cầu=<b>'+esc(p.requested_escalation)+'</b> → thực thi=<b>'+esc(p.escalation_mode)+'</b></div>');
  }
  // Critic — nổi bật cả issue chặn lẫn issue bị drop (fix cq03)
  if(p.critic){
    const iss=p.critic.issues||[], drp=p.critic.dropped||[];
    rows.push('<div class="grow">Plan Critic ('+esc(p.critic.provider)+'): '
      +(iss.length?tag('bad','CHẶN '+iss.length):tag('ok','KHÔNG CHẶN'))
      +(drp.length?(' '+tag('warn','LỌC '+drp.length+' issue sai')):'')+'</div>');
    iss.forEach(x=>rows.push('<div class="gitem bad">• chặn: '+esc(x.code)+(x.node_id?(' @'+esc(x.node_id)):'')+' — '+esc(x.message)+'</div>'));
    drp.forEach(x=>rows.push('<div class="gitem mut">• lọc (máy chứng minh sai): '+esc(x.code)+(x.node_id?(' @'+esc(x.node_id)):'')+'</div>'));
  }
  // N-version
  if(p.nversion){
    const n=p.nversion;
    rows.push('<div class="grow">N-version: chọn=<b>'+esc(n.selected)+'</b> · plan_bất_đồng='+esc(n.plan_disagreement)
      +' · kết_quả_bất_đồng='+esc(n.result_disagreement)+(n.adjudicated?' · '+tag('warn','ADJUDICATED'):'')+'</div>');
  }
  if(p.validator_feedback&&p.validator_feedback.length){
    rows.push('<div class="grow">Planner repair: '+tag('warn',p.validator_feedback.length+' feedback')+'</div>');
  }
  el.innerHTML='<div class="gbox"><h4>Planner path (analytical)</h4>'+rows.join('')+'</div>';
}

form.onsubmit=async e=>{
  e.preventDefault();
  const text=input.value.trim();if(!text)return;
  submit.disabled=true;submit.textContent='Đang chạy…';
  try{await run(text)}finally{submit.disabled=false;submit.textContent='Chạy'}
};
</script></body></html>'''
