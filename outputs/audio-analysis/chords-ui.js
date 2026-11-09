/* Independent chord workspace. Does not edit the original beat/segment project. */
(() => {
 'use strict';
 const q=id=>document.getElementById(id),copy=x=>JSON.parse(JSON.stringify(x));
 const qualities={maj:['major','大三'],min:['minor','小三'],dim:['diminished','减三'],aug:['augmented','增三'],min6:['minor6','小六'],maj6:['major6','大六'],min7:['minor7','小七'],minmaj7:['minorMajor7','小大七'],maj7:['major7','大七'],'7':['dominant7','属七'],dim7:['dim7','减七'],hdim7:['halfDim7','半减七'],sus2:['sus2','挂二'],sus4:['sus4','挂四']};
 const suffix={maj:'',min:'m',dim:'dim',aug:'aug',min6:'m6',maj6:'6',min7:'m7',minmaj7:'m(maj7)',maj7:'maj7','7':'7',dim7:'dim7',hdim7:'m7♭5',sus2:'sus2',sus4:'sus4'};
 const notes=['C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B'];
 const symbol=e=>e.label==='N'?'N · 无和弦':e.label==='X'?'X · 未知':e.label.split(':')[0]+suffix[e.label.split(':')[1]]+(e.bassNote?'/'+e.bassNote:'');
 let project=null,result=null,events=[],selected=0,history=[],dirty=false,loadToken=0,job=null,lastActive=-2,oscContext=null;
 let rhythm=null,chordRhythmRevision=null,beatPreview=null,lastBar=-2,structureCache=null;
 const section=document.createElement('section');section.id='ch-workspace';section.className='analysis-block chord-workspace';
 section.innerHTML=`<div class="section-header"><div><div class="eyebrow">HARMONY / HEAR & CONFIRM</div><h2>② 按小节听和弦 → 指板落点</h2></div><span class="badge small muted">BTC · 170 类候选</span></div>
 <p class="muted">先按每小节的练习建议弹起来。系统会区分可用根音与暂不确定的细节；你不需要先学会听辨和弦才能开始练习。</p>
 <div class="ch-actions"><button id="ch-analyze" class="primary">分析本曲和弦</button><button id="ch-reload">重新载入和弦</button><button id="ch-cancel" class="hidden">取消和弦分析</button><label><input id="ch-follow" type="checkbox" checked> 跟随播放选择</label></div>
 <p id="ch-status" role="status" aria-live="polite">先载入音频。</p><div id="ch-content" class="hidden">
 <div class="ch-now">正在播放：<strong id="ch-current">—</strong><span id="ch-state"></span></div>
 <label class="ch-detail">小节视图 <select id="ch-structure-view"><option value="stable">小节稳定候选</option><option value="raw">原始 / 当前编辑区间</option></select></label><p id="ch-structure-note" class="ch-detail" role="status"></p><p id="ch-rhythm-status" class="ch-detail"></p><div class="ch-actions"><button id="ch-beat-preview">按已锁定节奏生成稳定候选</button><button id="ch-rhythm-rebase" class="hidden">沿用现有标签，重新核对</button><button id="ch-beat-adopt" class="hidden">采用按拍候选（可撤销）</button></div><p id="ch-beat-preview-note" class="ch-detail" role="status"></p><div id="ch-bars" class="ch-bars" aria-label="按小节排列的和弦，可横向滚动"></div><details><summary>逐区间编辑与原始时间</summary><div id="ch-timeline" class="ch-timeline" aria-label="和弦区间，可点击选择"></div>
 </details><div class="ch-edit-grid"><label>根音 / 未知<select id="ch-root"></select></label><label>和弦性质<select id="ch-quality"></select></label><label>人工指定低音<select id="ch-bass"></select></label><button id="ch-apply">应用标签</button><label>本段开始（秒）<input id="ch-start" type="number" step="0.01"></label><button id="ch-boundary">移动边界</button></div>
 <div class="ch-actions"><button id="ch-loop">循环所选和弦</button><button id="ch-confirm" class="primary">已回听，确认此和弦</button><button id="ch-split">在播放位置拆分</button><button id="ch-merge">沿用本段合并后段</button></div>
 <p id="ch-selected" class="ch-detail"></p><p id="ch-board-gate" class="ch-detail"></p><div class="ch-board-scroll"><div id="ch-board" class="ch-board" aria-label="已确认和弦的四弦 21 品指板"></div></div><p id="ch-note" class="ch-detail">点击亮起的音，试听并查看弦品。</p>
 <div id="ch-theory"></div>
 <div class="ch-actions"><button id="ch-save" class="primary">保存和弦校正</button><button id="ch-undo">撤销和弦修改</button><button id="ch-reset">恢复机器和弦</button><button id="ch-export">导出和弦 JSON</button></div>
 <p id="ch-warning" class="ch-detail"></p></div>`;
 q('an-rhythm-section').after(section);
 for(const n of [...notes,'X','N'])q('ch-root').add(new Option(n==='X'?'未知':n==='N'?'无和弦':n,n));
 for(const [k,v] of Object.entries(qualities))q('ch-quality').add(new Option(v[1],k));
 q('ch-bass').add(new Option('未识别 / 不指定',''));for(const n of notes)q('ch-bass').add(new Option(n,n));
 function status(message,error=false){q('ch-status').textContent=message;q('ch-status').classList.toggle('error',error);}
 async function request(url,options={}){const r=await fetch(url,{...options,headers:{'X-Requested-With':'LowEndLab','Content-Type':'application/json',...options.headers}});const body=await r.json();if(!r.ok)throw Error(body.error||'和弦服务请求失败');return body;}
 const endpoint=()=>'/api/projects/'+project.id+'/chords';
 function snapshot(){history.push({events:copy(events),rhythmRevision:chordRhythmRevision});if(history.length>40)history.shift();}
 function mark(){dirty=true;render();}
 function announce(){window.dispatchEvent(new CustomEvent('lowend:chord-selection',{detail:{event:copy(events[selected]),projectId:project.id,revision:result.revision,dirty}}));}
 async function load(p){
  const token=++loadToken;project=p;rhythm=window.LowEndAnalysis.getRhythm();chordRhythmRevision=null;beatPreview=null;structureCache=null;lastBar=-2;result=null;events=[];history=[];dirty=false;selected=0;lastActive=-2;
  q('ch-beat-preview-note').textContent='';q('ch-structure-note').textContent='';
  q('ch-structure-view').value='stable';q('ch-content').classList.add('hidden');q('ch-analyze').disabled=!!job;status('正在读取本曲和弦…');
  try{const r=await request(endpoint());if(token!==loadToken)return;if(!r.available){status('本曲尚未分析和弦。点击“分析本曲和弦”开始。');return;}
   result=r;chordRhythmRevision=r.annotation?.rhythmRevision??null;events=copy(r.annotation?.events||r.events);render();status(`已载入 ${events.length} 个${r.annotation?"已保存":"原始机器"}和弦区间。稳定预览另行解码，需回听确认。`);
  }catch(e){if(token===loadToken)status(e.message,true);}
 }
 function render(){
  if(!result)return;selected=Math.max(0,Math.min(selected,events.length-1));q('ch-content').classList.remove('hidden');
  q('ch-state').textContent=dirty?'有未保存的和弦校正':`和弦保存版本 ${result.revision}`;q('ch-undo').disabled=!history.length;
  q('ch-timeline').replaceChildren();for(const [i,e] of events.entries()){
   const b=document.createElement('button');b.className='ch-chip'+(i===selected?' selected':'')+(e.status==='confirmed'?' confirmed':'');b.dataset.index=i;
   b.textContent=`${rhythm?.grid?.meter?RhythmGrid.label(rhythm.grid,e.startSec)+' · ':''}${e.startSec.toFixed(2)}–${e.endSec.toFixed(2)} s · ${symbol(e)}${e.status==='confirmed'?' ✓':''}`;
   b.onclick=()=>{q('ch-follow').checked=false;selected=i;renderSelection();};q('ch-timeline').append(b);
  }
  renderBars();q('ch-warning').textContent=`引擎 ${result.engineVersion}。${result.preservedAnnotationFrom&&result.annotation?'原有人工校正已保留；恢复机器和弦可查看新版候选，仍可撤销。':''}`+result.warnings.join(' ');renderSelection();lastActive=-2;updateClock(window.LowEndAnalysis.getTime());
 }
 function structure(){if(!rhythm?.grid||!result)return null;const key=rhythm.grid.signature+'|'+result.revision;if(structureCache?.key===key)return structureCache.value;structureCache=null;const value=HarmonyStructure.decode(rhythm.grid,result);structureCache={key,value};return value;}
 function renderBars(){
  const ready=rhythm?.projectId===project.id&&rhythm.grid.bars.length;
  q('ch-beat-preview').disabled=!ready||!rhythm.locked||dirty;
  const stale=chordRhythmRevision!==null&&chordRhythmRevision!==rhythm?.revision;q('ch-rhythm-rebase').classList.toggle('hidden',!stale);q('ch-rhythm-rebase').disabled=!rhythm?.locked;
  q('ch-rhythm-status').textContent=!ready?'请先设置每小节拍数与第一拍。':`${rhythm.locked?'使用已锁定节奏':'节奏尚未锁定，小节坐标待确认'} · 节奏版本 ${rhythm.revision}。${stale?'这些按拍候选基于旧节奏，请重新生成或人工复核。':''}一小节可有多个和弦，跨小节延续保留；半拍之外的切分请用边界编辑保留。${rhythm.grid.endSec<project.durationSec?rhythm.grid.endSec.toFixed(2)+' 秒之后不编小节，可展开逐区间查看尾段。':''}`;
  q('ch-beat-adopt').classList.toggle('hidden',!beatPreview||beatPreview.signature!==rhythm?.grid.signature||beatPreview.revision!==rhythm?.revision||!rhythm?.locked);
  q('ch-bars').replaceChildren();lastBar=-2;if(!ready){q('ch-structure-note').textContent='节奏尚未建立，先使用上方拍点提示练习闷音；暂不指定音高。';return;}
  let preview=null;const wantsPreview=q('ch-structure-view').value==='stable'&&!dirty&&!result.annotation;
  if(wantsPreview){try{preview=structure();}catch(e){q('ch-structure-note').textContent=e.message;}}
  if(preview)q('ch-structure-note').textContent=`正在显示学习建议与机器候选（${rhythm.locked?'已锁定节奏':'节奏未确认'}），尚未采用或保存。可直接从卡片上的根音或闷音练习开始，无需人工确认；确认与编辑留给需要校正时使用。`;
  else if(!wantsPreview)q('ch-structure-note').textContent=result.annotation||dirty?'显示当前编辑 / 已保存的和弦；不会用新算法覆盖人工校正。':'显示原始机器区间，可与稳定候选比较。';
  for(const bar of RhythmGrid.barHarmony(rhythm.grid,preview?preview.events:events)){
   const card=document.createElement('div');card.className='ch-bar';card.dataset.bar=bar.number;
   const title=document.createElement('button');title.className='ch-bar-title';title.textContent=`${bar.meterUnknown?'练习区间 '+bar.number:bar.numberApproximate?'候选区间 '+bar.number:bar.number<=0?'弱起/前置':'第 '+bar.number+' 小节'}${bar.partial?' · 不完整':''}${bar.uncertain?' · 拍点待校正':''}`;
   title.title=`${bar.startSec.toFixed(2)}–${bar.endSec.toFixed(2)} 秒，点击循环此小节`;title.onclick=()=>window.LowEndAnalysis.loop(bar.startSec,bar.endSec);card.append(title);
   const line=document.createElement('div');line.className='ch-bar-chords';
   for(const e of bar.events){const b=document.createElement('button');b.dataset.event=e.eventIndex;b.className='ch-bar-chord'+(e.status==='confirmed'?' confirmed':'');
    b.style.flexGrow=String(e.endSec-e.startSec);b.textContent=symbol(e);b.title=RhythmGrid.label(rhythm.grid,e.startSec)+` · ${e.startSec.toFixed(2)}–${e.endSec.toFixed(2)} 秒`;
    if(preview){b.dataset.preview=e.eventIndex;delete b.dataset.event;b.onclick=()=>{q('ch-follow').checked=false;window.LowEndAnalysis.loop(e.startSec,e.endSec);status('正在回听稳定候选 '+symbol(e)+'。锁定节奏并采用候选后，可编辑和确认；当前下方编辑器仍是原始区间。');};}else b.onclick=()=>{q('ch-follow').checked=false;selected=e.eventIndex;renderSelection();};line.append(b);}
   const diagnostic=preview?.bars.find(x=>x.number===bar.number);
   if(diagnostic?.learning){const advice=diagnostic.learning,box=document.createElement('div');box.className='ch-learning';box.dataset.level=advice.level;const heading=document.createElement('strong');heading.textContent=advice.title;const exercise=document.createElement('p');exercise.textContent=advice.exercise;const basis=document.createElement('p');basis.className='ch-detail';basis.textContent=advice.basis;box.append(heading,exercise,basis);card.append(box);const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='查看识别候选与依据';details.append(summary,line);if(diagnostic.omittedLabels.length||diagnostic.bridgedUnknownSeconds>.005){const note=document.createElement('p');note.className='ch-detail';note.textContent=[diagnostic.bridgedUnknownSeconds>.005?'上下文处理短 X：'+diagnostic.bridgedUnknownSeconds.toFixed(2)+' 秒':'',diagnostic.omittedLabels.length?'未采纳候选：'+diagnostic.omittedLabels.map(label=>symbol({label})).join('、'):''].filter(Boolean).join('；');details.append(note);}card.append(details);
   }else card.append(line);q('ch-bars').append(card);
  }
 }
 function updateBarClock(t){const p=rhythm?.grid?RhythmGrid.position(rhythm.grid,t):null,bar=p?.bar??null;if(bar===lastBar)return;lastBar=bar;
  q('ch-bars').querySelectorAll('.ch-bar').forEach(el=>{const active=bar!==null&&Number(el.dataset.bar)===bar;el.classList.toggle('current',active);if(active&&q('ch-follow').checked){const container=q('ch-bars');if(el.offsetLeft<container.scrollLeft||el.offsetLeft+el.offsetWidth>container.scrollLeft+container.clientWidth)container.scrollLeft=el.offsetLeft;}});
 }
 q('ch-structure-view').onchange=()=>{renderBars();renderSelection();lastActive=-2;updateClock(window.LowEndAnalysis.getTime());};
 q('ch-beat-preview').onclick=()=>{if(!rhythm?.locked||dirty)return;try{const candidate=structure().events;beatPreview={events:candidate,signature:rhythm.grid.signature,revision:rhythm.revision};q('ch-beat-preview-note').textContent=`已结合小节、持续时长与换和弦代价解码，得到 ${candidate.length} 个连续候选。持续不确定部分仍为 X；保留有强证据的小节内变化。采用会替换当前编辑副本，可撤销，不覆盖原始机器结果。`;q('ch-beat-adopt').classList.remove('hidden');}catch(e){status(e.message,true);}};
 q('ch-rhythm-rebase').onclick=()=>{if(!rhythm?.locked)return;snapshot();chordRhythmRevision=rhythm.revision;events=events.map(e=>({...e,status:'user_corrected'}));mark();status('已保留标签和时间，撤销旧确认状态。请按新节奏逐小节重新核对后保存。');};
 q('ch-beat-adopt').onclick=()=>{if(!beatPreview||!rhythm?.locked||beatPreview.signature!==rhythm.grid.signature||beatPreview.revision!==rhythm.revision)return;snapshot();events=copy(beatPreview.events);chordRhythmRevision=beatPreview.revision;beatPreview=null;selected=0;mark();status('按拍候选已采用，尚未保存。请逐小节回听；可撤销。');};
 window.addEventListener('lowend:rhythm',e=>{if(!project||e.detail?.projectId!==project.id)return;rhythm=e.detail;if(result)render();});
 function renderSelection(){
  const e=events[selected];if(!e)return;
  q('ch-timeline').querySelectorAll('button').forEach((b,i)=>b.classList.toggle('selected',i===selected));q('ch-bars').querySelectorAll('[data-event]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.event)===selected));
  const [root,quality]=e.label.split(':');q('ch-root').value=root;q('ch-quality').value=quality||'maj';q('ch-quality').disabled=['N','X'].includes(root);q('ch-bass').disabled=['N','X'].includes(root);q('ch-bass').value=e.bassNote||'';
  q('ch-start').value=e.startSec.toFixed(5);q('ch-start').disabled=selected===0;q('ch-boundary').disabled=selected===0;q('ch-merge').disabled=selected===events.length-1;
  q('ch-selected').textContent=`${q('ch-structure-view').value==='stable'&&!dirty&&!result.annotation?'下方编辑器为原始区间（预览尚未采用） · ':''}所选 ${symbol(e)} · ${e.startSec.toFixed(2)}–${e.endSec.toFixed(2)} 秒 · ${rhythm?.grid?RhythmGrid.label(rhythm.grid,e.startSec)+' · ':''}${e.status==='confirmed'?'人工已确认':e.status==='candidate'?'机器候选':'人工已修改，待确认'}`;
  renderBoard(e);announce();
 }
 function renderBoard(e){
  q('ch-board').replaceChildren();q('ch-note').textContent='点击亮起的音，试听并查看弦品。';
  if(e.status!=='confirmed'||['X','N'].includes(e.label)){q('ch-board-gate').textContent=e.status!=='confirmed'?'回听并确认此和弦后，显示构成音与指板落点。':'此区间没有已知和弦，不生成构成音落点。';return;}
  const [root,quality]=e.label.split(':'),tones=BassModel.chord(root,qualities[quality][0]);
  q('ch-board-gate').textContent=`${symbol(e)} 构成音：${tones.map(t=>t.name+'（'+t.role+'）').join(' · ')}。标准调弦 E–A–D–G，0–21 品（可横向滚动）。${e.bassNote?' 斜线低音 '+e.bassNote+' 为人工指定。':''}`;
  for(const label of ['',...Array.from({length:22},(_,i)=>i===0?'空弦':String(i))]){const cell=document.createElement('span');cell.className='ch-fret-label';cell.textContent=label;q('ch-board').append(cell);}
  for(let string=3;string>=0;string--){const label=document.createElement('span');label.className='ch-fret-label';label.textContent=['E','A','D','G'][string];q('ch-board').append(label);for(let fret=0;fret<=21;fret++){
   const p=BassModel.position(string,fret),t=tones.find(t=>t.pc===p.pc),b=document.createElement('button');
   b.className=t?'tone'+(t.role==='1'?' root':''):'';b.dataset.string=string;b.dataset.fret=fret;b.disabled=!t;b.textContent=t?t.name:'·';
   b.title=`${4-string} 弦 ${fret} 品 · ${t?t.name:p.name}${p.octave}${t?' · '+t.role:''}`;b.setAttribute('aria-label',b.title);
   if(e.bassNote&&p.pc===BassModel.parseNote(e.bassNote))b.classList.add('bass');
   if(t)b.onclick=async()=>{q('ch-note').textContent=b.title;oscContext=oscContext||new AudioContext();await oscContext.resume();let o=oscContext.createOscillator(),g=oscContext.createGain(),now=oscContext.currentTime;o.type='triangle';o.frequency.value=p.frequency;g.gain.setValueAtTime(.08,now);g.gain.exponentialRampToValueAtTime(.001,now+.5);o.connect(g);g.connect(oscContext.destination);o.start(now);o.stop(now+.5);o.onended=()=>{o.disconnect();g.disconnect();};};
   q('ch-board').append(b);
  }}
 }
 function updateClock(t){if(!events.length)return;updateBarClock(t);if(q('ch-structure-view').value==='stable'&&!dirty&&!result.annotation&&structureCache?.key===rhythm?.grid.signature+'|'+result.revision&&rhythm?.grid.bars.length){const proposed=structureCache.value.events,idx=proposed.findIndex(e=>t>=e.startSec&&t<e.endSec);q('ch-current').textContent=idx<0?'区间之外':symbol(proposed[idx])+' · 稳定候选预览';q('ch-bars').querySelectorAll('[data-preview]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.preview)===idx));return;}const active=events.findIndex(e=>t>=e.startSec&&t<e.endSec);if(active===lastActive)return;lastActive=active;q('ch-current').textContent=active<0?'区间之外':symbol(events[active])+(events[active].status==='confirmed'?' · 已确认':' · 候选');if(q('ch-follow').checked&&active>=0){selected=active;renderSelection();}}
 q('ch-follow').onchange=()=>{lastActive=-2;updateClock(window.LowEndAnalysis.getTime());};
 q('ch-workspace').querySelector('.ch-edit-grid').addEventListener('focusin',()=>q('ch-follow').checked=false);
 q('ch-root').onchange=()=>{const none=['N','X'].includes(q('ch-root').value);q('ch-quality').disabled=none;q('ch-bass').disabled=none;};
 q('ch-apply').onclick=()=>{snapshot();const e=events[selected],root=q('ch-root').value;e.label=['N','X'].includes(root)?root:root+':'+q('ch-quality').value;e.bassNote=['N','X'].includes(root)?null:q('ch-bass').value||null;e.status='user_corrected';mark();};
 q('ch-boundary').onclick=()=>{const e=events[selected],prev=events[selected-1],t=Number(q('ch-start').value);if(!prev||!Number.isFinite(t)||t<=prev.startSec+.02||t>=e.endSec-.02){status('边界前后至少各保留 0.02 秒。',true);return;}snapshot();e.startSec=prev.endSec=t;e.status=prev.status='user_corrected';mark();};
 q('ch-loop').onclick=()=>{const e=events[selected];q('ch-follow').checked=false;window.LowEndAnalysis.loop(e.startSec,e.endSec);};
 q('ch-confirm').onclick=()=>{snapshot();events[selected].status='confirmed';mark();status('此和弦已标为人工确认；点击“保存和弦校正”持久保存。');};
 q('ch-split').onclick=()=>{const t=window.LowEndAnalysis.getTime(),i=events.findIndex(e=>t>e.startSec+.02&&t<e.endSec-.02);if(i<0){status('请定位在和弦区间内部，前后至少各留 0.02 秒。',true);return;}snapshot();const e=events[i],next={...e,id:'manual-'+crypto.randomUUID(),startSec:t,status:'user_corrected'};e.endSec=t;e.status='user_corrected';events.splice(i+1,0,next);selected=i+1;q('ch-follow').checked=false;mark();};
 q('ch-merge').onclick=()=>{if(selected>=events.length-1)return;snapshot();events[selected].endSec=events[selected+1].endSec;events[selected].status='user_corrected';events.splice(selected+1,1);mark();};
 q('ch-undo').onclick=()=>{if(history.length){const old=history.pop();events=old.events;chordRhythmRevision=old.rhythmRevision;mark();}};
 q('ch-reset').onclick=()=>{snapshot();events=copy(result.events);chordRhythmRevision=null;mark();};
 q('ch-save').onclick=async()=>{try{const r=await request(endpoint(),{method:'PATCH',body:JSON.stringify({revision:result.revision,annotation:{events,...(chordRhythmRevision!==null?{rhythmRevision:chordRhythmRevision}:{})}})});result=r;events=copy(r.annotation.events);dirty=false;render();status('和弦校正已保存；原始和弦及节拍/段落保持独立。');}catch(e){status(e.message,true);}};
 q('ch-reload').onclick=()=>{if(dirty){status('请先保存和弦校正再重新载入。',true);return;}if(project)load(project);};
 q('ch-export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({...result,annotation:{events,...(chordRhythmRevision!==null?{rhythmRevision:chordRhythmRevision}:{})},hasUnsavedChanges:dirty},null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='chords-'+project.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 q('ch-analyze').onclick=async()=>{
  if(!project||job)return;if(dirty){status('请先保存当前和弦校正。',true);return;}const pid=project.id;q('ch-analyze').disabled=true;
  try{const r=await request(endpoint()+'/analyze',{method:'POST'});if(r.cached){await load(project);return;}job=r.jobId;q('ch-cancel').classList.remove('hidden');
   while(job){const j=await request('/api/jobs/'+job);status(j.message);if(j.status!=='running'){if(j.status==='complete'&&project.id===pid)await load(project);else if(j.status==='failed')status(j.message,true);break;}await new Promise(r=>setTimeout(r,700));}
  }catch(e){status(e.message,true);}finally{job=null;q('ch-analyze').disabled=false;q('ch-cancel').classList.add('hidden');}
 };
 q('ch-cancel').onclick=async()=>{if(job)try{await request('/api/jobs/'+job+'/cancel',{method:'POST'});}catch(e){status(e.message,true);}};
 window.LowEndChords={get dirty(){return dirty;},getSelection:()=>events[selected]?{event:copy(events[selected]),projectId:project.id,revision:result.revision,dirty}:null,qualities,symbol};
 window.addEventListener('lowend:project',e=>load(e.detail));window.addEventListener('lowend:clock',e=>updateClock(e.detail.displayTimeSec??e.detail.timeSec));
 if(window.LowEndAnalysis.getProject())load(window.LowEndAnalysis.getProject());
})();
