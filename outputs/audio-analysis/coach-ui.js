(() => {
 'use strict';
 const panel=document.createElement('section');panel.className='analysis-block coach-panel';panel.id='qa-panel';
 panel.innerHTML=`<div class="section-header"><h2>和 Astra 聊乐理</h2><span class="badge small muted">Qwen · 中文知识问答</span></div>
 <p class="ch-detail">发送文字问题、知识卡，以及你选择的已确认和弦。不会上传音频；模型没有直接听到原曲。</p>
 <div class="ch-actions"><button id="qa-refresh">检查本机配置</button><a href="/audio-analysis/QWEN-配置说明.md" target="_blank" rel="noopener">配置步骤 ↗</a><a href="/audio-analysis/evaluation/index.html" target="_blank" rel="noopener">BTC 独立评测 ↗</a></div>
 <p id="qa-status" role="status" aria-live="polite">正在检查本机配置…</p>
 <label class="ch-detail"><input id="qa-use-event" type="checkbox"> 使用当前已确认并保存的和弦作为依据</label><p id="qa-context" class="ch-detail"></p>
 <label for="qa-question" class="ch-detail">你的问题</label><textarea id="qa-question" rows="3" maxlength="1500" placeholder="例如：小七和弦的三音和七音，对贝斯线有什么作用？"></textarea>
 <div class="ch-actions"><button id="qa-ask" class="primary" disabled>向 Qwen 提问</button><button id="qa-export">导出本段问答依据</button></div>
 <p class="ch-detail">发送会调用百炼并可能计费。相同问题与依据的成功回答会在服务运行期间复用；不自动重试失败请求。</p>
 <div id="qa-answer" class="ch-theory-card hidden" aria-live="polite"></div><div id="qa-sources" class="ch-detail"></div>`;
 document.getElementById('ch-workspace').after(panel);
 const q=id=>document.getElementById(id);let configured=false,busy=false,selection=null,requestToken=0;
 const valid=()=>selection&&!selection.dirty&&selection.event.status==='confirmed'&&!['N','X'].includes(selection.event.label);
 function state(){
  q('qa-use-event').disabled=busy||!valid();if(!valid())q('qa-use-event').checked=false;
  q('qa-ask').disabled=busy||!configured;q('qa-export').disabled=!valid();
  q('qa-context').textContent=valid()?`可用依据：${LowEndChords.symbol(selection.event)}，${selection.event.startSec.toFixed(2)}–${selection.event.endSec.toFixed(2)} 秒，保存版本 ${selection.revision}。`:'当前没有已确认并保存的具体和弦，可以直接问一般乐理知识。';
 }
 async function status(){try{const r=await fetch('/api/coach/status');const s=await r.json();configured=!!s.configured;q('qa-status').textContent=s.message+' 模型：'+s.model;state();}catch{configured=false;q('qa-status').textContent='本机问答服务未连接，请运行最新版启动脚本。';state();}}
 q('qa-refresh').onclick=status;
 window.addEventListener('lowend:chord-selection',e=>{selection=e.detail;state();});
 window.addEventListener('lowend:project',()=>{selection=null;requestToken++;q('qa-answer').replaceChildren();q('qa-answer').classList.add('hidden');q('qa-sources').replaceChildren();state();});
 q('qa-ask').onclick=async()=>{
  const question=q('qa-question').value.trim();if(question.length<2){q('qa-status').textContent='请先输入至少两个字符的问题。';return;}
  const body={question};let requestLabel='一般乐理知识';
  if(q('qa-use-event').checked){if(!valid())return;Object.assign(body,{projectId:selection.projectId,eventId:selection.event.id,revision:selection.revision});requestLabel=LowEndChords.symbol(selection.event)+` · ${selection.event.startSec.toFixed(2)}–${selection.event.endSec.toFixed(2)} 秒`;}
  const token=++requestToken;busy=true;state();q('qa-status').textContent='Qwen 正在生成回答…';
  try{
   const response=await fetch('/api/coach/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'LowEndLab'},body:JSON.stringify(body)}),r=await response.json();
   if(token!==requestToken)return;if(!response.ok)throw Error(r.error||'问答失败');
   const answer=q('qa-answer');answer.replaceChildren();answer.classList.remove('hidden');const title=document.createElement('strong');title.textContent=`${r.model} · ${requestLabel}${r.cached?' · 已复用缓存':''}`;const text=document.createElement('p');text.textContent=r.answer;text.style.whiteSpace='pre-wrap';answer.append(title,text);
   q('qa-sources').replaceChildren();for(const card of r.knowledgeCards){const p=document.createElement('p');p.textContent=`[${card.id}] ${card.title} · 知识卡待教师复核`;q('qa-sources').append(p);}
   for(const source of r.sources){const a=document.createElement('a');a.href=source.url;a.target='_blank';a.rel='noopener';a.textContent=source.title+' ↗ ';q('qa-sources').append(a);}
   for(const warning of r.warnings){const p=document.createElement('p');p.textContent=warning;q('qa-sources').append(p);}
   q('qa-status').textContent=`回答已生成，仅使用文字依据。${r.usage?.total_tokens?'本次响应总 Token：'+r.usage.total_tokens+'。':''}请回听或查阅来源验证建议。`;
  }catch(e){if(token===requestToken)q('qa-status').textContent=e.message;}finally{busy=false;state();}
 };
 q('qa-export').onclick=()=>{if(!valid())return;const data={schemaVersion:1,kind:'music_question_evidence',audioIncluded:false,...selection,theory:ChordTheory.explain(selection.event)};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='music-evidence-'+selection.event.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 selection=window.LowEndChords?.getSelection();state();status();
})();
