/* Deterministic, evidence-linked theory. Not language-model output. */
(function(root){
 'use strict';
 const model=typeof module!=='undefined'&&module.exports?require('../fretboard-model.js'):root.BassModel;
 const qualityMap={maj:'major',min:'minor',dim:'diminished',aug:'augmented',min6:'minor6',maj6:'major6',min7:'minor7',minmaj7:'minorMajor7',maj7:'major7','7':'dominant7',dim7:'dim7',hdim7:'halfDim7',sus2:'sus2',sus4:'sus4'};
 const roles={'1':'根音','2':'大二度','b3':'小三度','3':'大三度','4':'纯四度','b5':'减五度','5':'纯五度','#5':'增五度','6':'大六度','bb7':'减七度','b7':'小七度','7':'大七度'};
 const sources=[{id:'K03',title:'和弦音优先 · StudyBass',url:'https://www.studybass.com/lessons/bass-chord-patterns/chord-tones-are-primary/'},{id:'K11',title:'斜线和弦 · StudyBass',url:'https://www.studybass.com/lessons/reading-music/slash-chords/'}];
 function explain(event){
  if(!event||event.status!=='confirmed')return {available:false,reason:'先回听并确认和弦，再生成乐理练习。'};
  if(['X','N'].includes(event.label))return {available:false,reason:'这个区间没有已确认的具体和弦，不生成音高练习。'};
  const [rootNote,quality]=event.label.split(':'),type=qualityMap[quality];
  if(!type)throw RangeError('未知和弦类型');
  const tones=model.chord(rootNote,type).map(t=>({...t,intervalName:roles[t.role]}));
  const bass=event.bassNote||null,bassTone=bass?tones.find(t=>t.pc===model.parseNote(bass)):null;
  const fifth=tones.find(t=>['5','b5','#5'].includes(t.role));
  return {available:true,kind:'deterministic_theory',ruleVersion:'1.0',eventId:event.id,
   interval:{startSec:event.startSec,endSec:event.endSec},root:rootNote,quality,tones,
   bassNote:bass,bassMeaning:!bass?'实际低音尚未识别；根音可作为编配练习起点。':bassTone?`人工指定低音 ${bass} 是和弦的${bassTone.intervalName}；根音仍是 ${rootNote}。`:`人工指定低音 ${bass} 不在该和弦构成音中；可能是踏板或经过低音，需要结合上下文确认。`,
   exercise:`循环这个区间，先用 ${bass||rootNote} 跟随你确认的拍点弹稳定四分音符，再尝试 ${rootNote} 与 ${fifth.name} 交替，比较律动与留白。`,
   limitation:'这是基于已确认和弦生成的练习建议，不是原曲贝斯转录。三音、七音或经过音的使用仍要听上下文；本页未自动确定全曲调性。',
   sources:bass?sources:[sources[0]],knowledgeCardIds:bass?['K03','K11']:['K03']};
 }
 const api={explain,qualityMap,roles};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ChordTheory=api;
})(typeof window!=='undefined'?window:globalThis);
