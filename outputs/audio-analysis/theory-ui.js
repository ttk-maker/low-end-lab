(() => {
 'use strict';
 function render(detail){
  const target=document.getElementById('ch-theory');if(!target)return;target.replaceChildren();
  const theory=ChordTheory.explain(detail?.event),card=document.createElement('div');card.className='ch-theory-card';
  const title=document.createElement('strong');title.textContent='和弦乐理卡 · 规则计算';card.append(title);
  const line=text=>{const p=document.createElement('p');p.textContent=text;card.append(p);};
  if(!theory.available)line(theory.reason);
  else{
   line(theory.tones.map(t=>`${t.name} = ${t.intervalName}（${t.interval} 半音）`).join(' · '));
   line(theory.bassMeaning);line(theory.exercise);line(theory.limitation);
   line(`依据：${theory.interval.startSec.toFixed(2)}–${theory.interval.endSec.toFixed(2)} 秒，已确认事件 ${theory.eventId}。${detail.dirty?'当前校正尚未保存。':''}`);
   for(const source of theory.sources){let a=document.createElement('a');a.href=source.url;a.target='_blank';a.rel='noopener';a.textContent=source.title+' ↗ ';card.append(a);}
  }
  target.append(card);

 }
 window.addEventListener('lowend:chord-selection',e=>render(e.detail));
 const current=window.LowEndChords?.getSelection();if(current)render(current);
})();
