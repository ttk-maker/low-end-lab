/* Bar-aware duration decoding. Scores are evidence, never calibrated confidence. */
(function(root,factory){if(typeof module==='object')module.exports=factory(require('./rhythm-grid.js'));else root.HarmonyStructure=factory(root.RhythmGrid);})(globalThis,R=>{
 'use strict';
 const VERSION='bar-stability-v3';
 const PARAMETERS=Object.freeze({changeCost:.10,minScore:.32,minMargin:.08,unknownRunBeats:1,
  minimumSpanBeats:.75,shortSpanScore:.75,shortSpanMargin:.30});
 const ROOTS=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
 const INTERVALS={maj:[0,4,7],min:[0,3,7],dim:[0,3,6],aug:[0,4,8],maj6:[0,4,7,9],min6:[0,3,7,9],
  maj7:[0,4,7,11],min7:[0,3,7,10],minmaj7:[0,3,7,11],'7':[0,4,7,10],dim7:[0,3,6,9],hdim7:[0,3,6,10],sus2:[0,2,7],sus4:[0,5,7]};
 function corroborate(pitch,scores,labels){
  const norm=Math.hypot(...pitch),sum=pitch.reduce((a,b)=>a+b,0),max=Math.max(...pitch);
  if(norm<1e-7)return null;
  const ranked=labels.map((label,i)=>{const [r,q]=label.split(':'),pc=ROOTS.indexOf(r),ints=INTERVALS[q];
   if(pc<0||!ints)return null;const tones=ints.map(n=>(n+pc)%12),inside=tones.reduce((s,n)=>s+pitch[n],0);
   return {label,index:i,tones,fit:inside/(norm*Math.sqrt(tones.length)),outside:1-inside/sum,minTone:Math.min(...tones.map(n=>pitch[n]))/max};
  }).filter(Boolean).sort((a,b)=>b.fit-a.fit);
  const a=ranked[0],known=ranked.slice().sort((a,b)=>scores[b.index]-scores[a.index]);
  // Duplicate pitch sets (e.g. C6 / Am7) cannot establish a unique root.
  if(!a||a.fit<.90||a.fit-ranked[1].fit<.06||a.outside>.26||a.minTone<.4||known[0].index!==a.index||scores[a.index]<.10)return null;
  return {...a,fitMargin:a.fit-ranked[1].fit,btcScore:scores[a.index]};
 }
 function decode(g,result){
  const frames=result.rawFrames||[],labels=result.method?.labelOrder;
  if(!g.bars.length)throw Error('尚无可用拍点区间；先练自由节奏闷音。');
  if(!labels||!frames.length||!frames.every(f=>f.scores?.length===labels.length))throw Error('需要 BTC 完整分数，请先分析本曲和弦。');
  const known=labels.map((_,i)=>i).filter(i=>!['X','N'].includes(labels[i]));
  const times=frames.map(f=>f.timeSec),silence=result.events.filter(e=>e.label==='N'&&e.reason==='sustained_low_energy');
  const events=[],bars=[];
  function add(a,b,label,reason){
   if(b-a<1e-6)return;
   if(events.length&&events.at(-1).label===label&&Math.abs(events.at(-1).endSec-a)<1e-5)events.at(-1).endSec=b;
   else events.push({id:`stable-${events.length+1}`,startSec:a,endSec:b,label,bassNote:null,status:'candidate',source:VERSION,reason});
  }
  function outside(a,b){for(const e of result.events){const lo=Math.max(a,e.startSec),hi=Math.min(b,e.endSec);if(hi>lo)add(lo,hi,e.label,'outside_grid_original');}}
  function average(a,b){
   const scores=Array(labels.length).fill(0);let weight=0;
   for(let i=Math.max(0,R.at(times,a));i<frames.length&&times[i]<b;i++){
    const w=Math.max(0,Math.min(b,times[i+1]??g.durationSec)-Math.max(a,times[i]));weight+=w;
    for(let k=0;k<labels.length;k++)scores[k]+=frames[i].scores[k]*w;
   }
   return scores.map(x=>weight?x/weight:0);
  }
  function rank(scores){const order=[...known].sort((a,b)=>scores[b]-scores[a]);const first=order[0];return {label:labels[first],score:scores[first]||0,margin:(scores[first]||0)-(scores[order[1]]||0)};}
  function pitchAverage(a,b){
   const out=Array(12).fill(0);let weight=0;
   for(let i=Math.max(0,R.at(times,a));i<frames.length&&times[i]<b;i++){
    const p=frames[i].pitchEnergy;if(!p||p.length!==12||p.some(v=>!Number.isFinite(v)||v<0))return null;
    const w=Math.max(0,Math.min(b,times[i+1]??g.durationSec)-Math.max(a,times[i]));weight+=w;
    for(let k=0;k<12;k++)out[k]+=p[k]*w;
   }
   return weight?out.map(v=>v/weight):null;
  }
  outside(0,g.bars[0].startSec);
  for(const bar of g.bars){
   if(bar.uncertain){
    const fullySilent=silence.some(s=>s.startSec<=bar.startSec&&s.endSec>=bar.endSec);
    const label=fullySilent?'N':'X';add(bar.startSec,bar.endSec,label,'rhythm_uncertain');
    bars.push({number:bar.number,startSec:bar.startSec,endSec:bar.endSec,uncertain:true,
     spans:[{startSec:bar.startSec,endSec:bar.endSec,label,score:0,margin:0}],
     learning:{level:fullySilent?'rest':'rhythm',title:fullySilent?'这一区间先留白':'这一区间先练闷音',exercise:'先不猜和弦音高；按自己舒适的慢速练闷音，不把未确定拍点当作准确节奏。',basis:bar.meterUnknown?'每小节拍数尚未确定，这里是练习区间，不是已识别的小节。':'仅本区间节奏存在疑点，其他正常区间继续分析。'},
     omittedLabels:[],originalFragments:result.events.filter(e=>e.startSec<bar.endSec&&e.endSec>bar.startSec).length,stableFragments:1,bridgedUnknownSeconds:0});
    continue;
   }
   const cut=[bar.startSec,bar.endSec];
   for(let i=bar.startIndex;i<bar.endIndex;i++){
    const a=g.beats[i],b=g.beats[i+1]??g.endSec;cut.push(a,(a+b)/2,Math.min(b,bar.endSec));
   }
   for(const s of silence)for(const t of [s.startSec,s.endSec])if(t>bar.startSec&&t<bar.endSec)cut.push(t);
   const edges=[...new Set(cut)].sort((a,b)=>a-b),cells=[];
   for(let i=0;i<edges.length-1;i++){
    const a=edges[i],b=edges[i+1],scores=average(a,b),top=rank(scores),bi=Math.max(0,R.at(g.beats,a));
    const period=(g.beats[bi+1]??g.endSec)-g.beats[bi];
    cells.push({a,b,scores,top,beats:(b-a)/period,silent:silence.some(s=>s.startSec<=a+1e-6&&s.endSec>=b-1e-6),hardUnknown:false});
   }
   // Long weak evidence is a barrier; never fill it solely to simplify the bar.
   for(let i=0;i<cells.length;){
    if(cells[i].silent||!(cells[i].top.score<.28||cells[i].top.margin<.04)){i++;continue;}
    let j=i,total=0;while(j<cells.length&&!cells[j].silent&&(cells[j].top.score<.28||cells[j].top.margin<.04)){total+=cells[j].beats;j++;}
    if(total>PARAMETERS.unknownRunBeats+1e-6)for(let k=i;k<j;k++)cells[k].hardUnknown=true;
    i=j;
   }
   const totalDuration=bar.endSec-bar.startSec,n=cells.length,dp=Array(n+1).fill(-Infinity),back=Array(n+1);
   dp[0]=0;
   for(let end=1;end<=n;end++)for(let start=0;start<end;start++){
    const chunk=cells.slice(start,end),duration=chunk.at(-1).b-chunk[0].a;
    const allSilent=chunk.every(c=>c.silent),allUnknown=chunk.every(c=>c.hardUnknown);
    if(!allSilent&&chunk.some(c=>c.silent)||!allUnknown&&chunk.some(c=>c.hardUnknown))continue;
    const scores=Array(labels.length).fill(0);let beats=0;
    for(const c of chunk){beats+=c.beats;for(let k=0;k<labels.length;k++)scores[k]+=c.scores[k]*(c.b-c.a)/duration;}
    const top=rank(scores);
    let label=allSilent?'N':allUnknown?'X':top.score>=PARAMETERS.minScore&&top.margin>=PARAMETERS.minMargin?top.label:'X';
    if(label!=='X'&&label!=='N'&&beats<PARAMETERS.minimumSpanBeats-1e-6){
     const strong=beats>=.45&&top.score>=PARAMETERS.shortSpanScore&&top.margin>=PARAMETERS.shortSpanMargin;
     if(!strong&&!(start===0&&end===n))label='X';
    }
    const utility=(label==='N'?1:label==='X'?.20:top.score)*duration/totalDuration;
    // Silence/long-unknown boundaries carry no musical change penalty.
    const forced=start>0&&(cells[start-1].silent!==cells[start].silent||cells[start-1].hardUnknown!==cells[start].hardUnknown);
    const cost=start>0&&!forced?PARAMETERS.changeCost:0;
    const value=dp[start]+utility-cost;
    if(value>dp[end]+1e-10){dp[end]=value;back[end]={start,label,top,beats};}
   }
   let spans=[];for(let end=n;end>0;){const s=back[end];if(!s)throw Error('小节候选无法解码，请保留原始时间轴。');spans.unshift({startSec:cells[s.start].a,endSec:cells[end-1].b,label:s.label,score:s.top.score,margin:s.top.margin});end=s.start;}
   const pitch=pitchAverage(bar.startSec,bar.endSec),avg=average(bar.startSec,bar.endSec);
   let joint=pitch&&!cells.some(c=>c.silent)?corroborate(pitch,avg,labels):null;
   if(joint){
    const competing=cells.some(c=>c.top.label!==joint.label&&c.top.score>=.65&&c.top.margin>=.25);
    // Comping decays while walking bass articulates chord tones. Require
    // continued pitch-set support, not simultaneous re-articulation of every
    // note in every half beat. The full-bar fit still requires all chord tones.
    const support=cells.reduce((sum,c)=>{const p=pitchAverage(c.a,c.b),total=p?.reduce((a,b)=>a+b,0)||0;return sum+(total&&joint.tones.reduce((s,n)=>s+p[n],0)/total>=.65?c.b-c.a:0);},0)/totalDuration;
    if(competing||support<.75)joint=null;
   }
   if(joint)spans=[{startSec:bar.startSec,endSec:bar.endSec,label:joint.label,score:joint.btcScore,margin:rank(avg).margin,evidence:'btc_and_persistent_tones'}];
   for(const s of spans)add(s.startSec,s.endSec,s.label,s.evidence|| (s.label==='N'?'sustained_low_energy':s.label==='X'?'insufficient_evidence':'bar_duration_evidence'));
   const old=result.events.filter(e=>e.startSec<bar.endSec&&e.endSec>bar.startSec);
   const omitted=[...new Set(old.filter(e=>e.label!=='X'&&!spans.some(s=>s.label===e.label)).map(e=>e.label))];
   let learning=learningAdvice(avg,labels,spans);
   if(joint&&learning.level==='rhythm'){const root=joint.label.split(':')[0];learning={level:'root',root,chord:null,title:`先练 ${root} 根音`,exercise:`先用 ${root} 根音练稳定节拍；暂不添加三音、七音与加花。`,basis:'持续音高与 BTC 的首选已知和弦相符；联合证据仍是候选，先采用较保守的根音练习。'};}
   bars.push({number:bar.number,startSec:bar.startSec,endSec:bar.endSec,spans,learning,tonalCorroboration:joint,omittedLabels:omitted,
    originalFragments:old.length,stableFragments:spans.length,
    bridgedUnknownSeconds:old.filter(e=>e.label==='X').reduce((sum,e)=>sum+spans.filter(s=>!['X','N'].includes(s.label)).reduce((v,s)=>v+Math.max(0,Math.min(e.endSec,s.endSec)-Math.max(e.startSec,s.startSec)),0),0)});
  }
  outside(g.endSec,g.durationSec);
  // Keep serialized coordinates within the precision used by the backend.
  for(const e of events){e.startSec=Number(e.startSec.toFixed(5));e.endSec=Number(e.endSec.toFixed(5));}
  return {version:VERSION,parameters:PARAMETERS,events,bars,warning:'结构化机器候选；短暂未知可由上下文支持，持续未知仍保留。少数真实快速换和弦可能被抑制，请与原始时间轴回听比较。'};
 }
 function learningAdvice(scores,labels,spans){
  if(spans.every(s=>s.label==='N'))return {level:'rest',title:'这一小节先留白',exercise:'暂不加音高，数拍或休止，观察下一小节的进入。',basis:'低能量候选，不代表原曲一定完全静音。'};
  const roots={};let known=0;
  labels.forEach((label,i)=>{if(label.includes(':')){const root=label.split(':')[0];roots[root]=(roots[root]||0)+scores[i];known+=scores[i];}});
  const order=Object.entries(roots).sort((a,b)=>b[1]-a[1]),best=order[0];
  const changes=new Set(spans.filter(s=>!['X','N'].includes(s.label)).map(s=>s.label.split(':')[0]));
  const hasRest=spans.some(s=>s.label==='N');
  if(!best||known<.8||best[1]<.75||best[1]-(order[1]?.[1]||0)<.3||changes.size>1||hasRest)
   return {level:'rhythm',title:'这一小节先练节奏',exercise:'轻触琴弦做闷音，跟随拍点；先不加入需要猜测的音高。',basis:changes.size>1?'本小节可能有换根音，暂不压成一个根音。':'音高证据不足，系统暂不指定和弦或根音。'};
  const confident=spans.length===1&&!['X','N'].includes(spans[0].label)&&spans[0].score>=.65&&spans[0].margin>=.25;
  return {level:confident?'chord':'root',root:best[0],chord:confident?spans[0].label:null,
   title:`先练 ${best[0]} 根音`,exercise:`以 ${best[0]} 作为本小节的练习起点，每拍一个音，先弹稳并留白；暂不加花。`,
   basis:confident?'完整和弦证据较集中；这是基于机器候选的练习，不是原曲贝斯谱。':'根音证据较集中，和弦性质或七音仍不明确；先不练三音、七音。'};
 }
 return {decode,learningAdvice,corroborate,VERSION,PARAMETERS};
});
