/* One measured timeline for counting, clicks, bar views and harmonic evidence. */
(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.RhythmGrid=api;})(globalThis,()=>{
 'use strict';
 const median=a=>{const s=[...a].sort((x,y)=>x-y);return s.length?s[Math.floor(s.length/2)]:0;};
 function at(a,t){let lo=0,hi=a.length-1,k=-1;while(lo<=hi){const m=(lo+hi)>>1;if(a[m]<=t){k=m;lo=m+1;}else hi=m-1;}return k;}
 function nearest(a,t){if(!a.length)return -1;const k=at(a,t);return k<0?0:k===a.length-1||t-a[k]<=a[k+1]-t?k:k+1;}
 function phase(beats,downs,meter){
  if(!meter||!beats.length)return 0;
  const votes=Array(meter).fill(0);
  for(const t of downs){const k=nearest(beats,t);if(Math.abs(beats[k]-t)<.08)votes[k%meter]++;}
  return votes.indexOf(Math.max(...votes));
 }
 function build(edit,duration){
  const beats=edit.beats||[],meter=edit.beatsPerBar||null;
  const anchor=Number.isInteger(edit.barAnchorIndex)?edit.barAnchorIndex:phase(beats,edit.downbeats||[],meter);
  const gaps=beats.slice(1).map((t,i)=>t-beats[i]);const typical=median(gaps);
  const end=beats.length?Math.min(duration,edit.activityEndSec??duration,beats.at(-1)+median(gaps.slice(-8))):0;
  const anomalies=[];
  for(let i=0;i<gaps.length;i++){
   const nearby=gaps.slice(Math.max(0,i-8),i).concat(gaps.slice(i+1,i+9));const local=median(nearby)||typical;
   if(local&&(gaps[i]>local*1.5||gaps[i]<local*.55))anomalies.push({index:i,startSec:beats[i],endSec:beats[i+1],ratio:gaps[i]/local});
  }
  const segments=edit.meterSegments?.length?edit.meterSegments:[{startBeatIndex:0,endBeatIndex:beats.length,beatsPerBar:meter,anchorBeatIndex:anchor}];
  const bars=[],downbeats=[];let nextNumber=anchor>0?0:1,approximate=false;
  for(const segment of segments){
   const lo=segment.startBeatIndex,hi=segment.endBeatIndex,m=segment.beatsPerBar;
   const splits=[lo,...anomalies.filter(a=>a.index>=lo&&a.index+1<hi).map(a=>a.index+1),hi];
   for(let si=0;si<splits.length-1;si++){
    const start=splits[si],stop=splits[si+1];let localAnchor=segment.anchorBeatIndex??lo,phaseUncertain=false;
    if(si>0&&m){
     approximate=true;const votes=Array(m).fill(0);
     for(const d of edit.downbeats||[]){const k=nearest(beats,d);if(k>=start&&k<stop&&Math.abs(beats[k]-d)<.08)votes[(k-start)%m]++;}
     const total=votes.reduce((a,b)=>a+b,0),best=Math.max(...votes);
     phaseUncertain=best<3||best/Math.max(1,total)<.7;
     localAnchor=start+votes.indexOf(best);
    }
    if(!m)approximate=true;
    const starts=[start];
    if(m){for(let i=start;i<stop;i++)if(((i-localAnchor)%m+m)%m===0){downbeats.push(beats[i]);if(i!==start)starts.push(i);}}
    else for(let i=start+4;i<stop;i+=4)starts.push(i);
    starts.forEach((i,k)=>{
     const j=starts[k+1]??stop,a=beats[i],b=j<beats.length?beats[j]:end;
     const number=nextNumber++;
     if(a!==undefined&&b>a)bars.push({number,startIndex:i,endIndex:j,startSec:a,endSec:b,meter:m,
      partial:!m||j-i<m||i<localAnchor,uncertain:!m||phaseUncertain||anomalies.some(x=>x.index>=i&&x.index<j),
      meterUnknown:!m,numberApproximate:approximate,source:segment.source||'global_grouping'});
    });
   }
  }
  const conflicts=(edit.downbeats||[]).filter(t=>!downbeats.some(d=>Math.abs(d-t)<.08)).length;
  return {beats,meter,anchor,meterSegments:segments,downbeats,bars,endSec:end,durationSec:duration,anomalies,conflicts,
   signature:JSON.stringify([beats,meter,anchor,edit.meterSegments||[],edit.activityEndSec??null])};
 }
 function position(g,t){
  const i=at(g.beats,t);
  if(i<0||t>=g.endSec)return null;
  const next=g.beats[i+1]??g.endSec,frac=next>g.beats[i]?(t-g.beats[i])/(next-g.beats[i]):0;
  const bar=g.bars.find(b=>i>=b.startIndex&&i<b.endIndex);
  return {index:i,bar:bar?.meter?bar.number:null,beat:bar?.meter?i-bar.startIndex+1:null,fraction:frac,
   uncertain:!!bar?.uncertain,numberApproximate:!!bar?.numberApproximate};
 }
 function label(g,t){const p=position(g,t);if(!p)return g.beats.length&&t<g.beats[0]?'起点在首拍前':'拍点范围外';if(p.bar===null)return `拍点 ${p.index+1} · 分组未确定`;
  const f=p.fraction<.12?'':Math.abs(p.fraction-.5)<.12?' + 半拍':` + ${p.fraction.toFixed(2)} 拍`;
  return `${p.bar<=0?'弱起/前置':`${p.numberApproximate?'候选区间':'第'} ${p.bar}${p.numberApproximate?'':' 小节'}`} · ${p.beat}${f} 拍${p.uncertain?'（待校正）':''}`;
 }
 function barHarmony(g,events){return g.bars.map(bar=>({...bar,events:events.map((e,i)=>({...e,eventIndex:i,
  startSec:Math.max(e.startSec,bar.startSec),endSec:Math.min(e.endSec,bar.endSec)})).filter(e=>e.endSec-e.startSec>1e-6)}));}
 function beatChords(g,result){
  const frames=result.rawFrames||[],labels=result.method?.labelOrder;
  if(!g.meter||!g.bars.length)throw Error('先设置每小节拍数与第一拍。');
  if(g.anomalies.length)throw Error('仍有疑似漏拍或多拍区间，请先校正节奏。');
  if(!labels||!frames.length||!frames.every(f=>Array.isArray(f.scores)&&f.scores.length===labels.length))throw Error('需要新版 BTC 完整分数；请先完成和弦分析。');
  const cuts=[0];
  for(let i=0;i<g.beats.length;i++){const a=g.beats[i],b=g.beats[i+1]??g.endSec;cuts.push(a,(a+b)/2,b);}
  cuts.push(g.durationSec);
  // Keep acoustic silence boundaries exact, even if they fall between beats.
  const silenceEvents=result.events.filter(e=>e.label==='N'&&e.reason==='sustained_low_energy');
  for(const e of silenceEvents)cuts.push(e.startSec,e.endSec);
  const sorted=[...new Set(cuts.map(t=>Math.round(t*1e5)/1e5))].filter(t=>t>=0&&t<=g.durationSec).sort((a,b)=>a-b);
  const events=[];let frameIndex=0;
  for(let c=0;c<sorted.length-1;c++){
   const a=sorted[c],b=sorted[c+1];if(b-a<1e-6)continue;
   const silent=silenceEvents.some(e=>e.startSec<=a+1e-5&&e.endSec>=b-1e-5);
   const scores=Array(labels.length).fill(0);let weight=0;
   while(frameIndex+1<frames.length&&frames[frameIndex+1].timeSec<=a)frameIndex++;
   for(let j=frameIndex;j<frames.length&&frames[j].timeSec<b;j++){
    const overlap=Math.max(0,Math.min(b,frames[j+1]?.timeSec??g.durationSec)-Math.max(a,frames[j].timeSec));
    weight+=overlap;for(let k=0;k<scores.length;k++)scores[k]+=overlap*frames[j].scores[k];
   }
   const order=scores.map((s,i)=>i).sort((x,y)=>scores[y]-scores[x]);
   const score=weight?scores[order[0]]/weight:0,margin=weight?(scores[order[0]]-scores[order[1]])/weight:0;
   const inside=a>=g.beats[0]-1e-5&&b<=g.endSec+1e-5;
   const chord=silent?'N':inside&&score>=.35&&margin>=.08?labels[order[0]]:'X';
   if(events.length&&events.at(-1).label===chord)events.at(-1).endSec=b;
   else events.push({id:`beat-chord-${events.length+1}`,startSec:a,endSec:b,label:chord,bassNote:null,status:'candidate',source:'beat-half-cell-v1'});
  }
  return events;
 }
 return {build,position,label,phase,barHarmony,beatChords,nearest,at};
});
