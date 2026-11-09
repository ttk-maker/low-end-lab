/* LOW END LAB — deterministic pitch model; sounding pitch, MIDI C4=60. */
(function (root) {
  'use strict';
  const mod = n => ((n % 12) + 12) % 12;
  const natural = {C:0,D:2,E:4,F:5,G:7,A:9,B:11};
  const names = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];
  const types = {
    major:[[0,4,7],['1','3','5']], minor:[[0,3,7],['1','b3','5']],
    diminished:[[0,3,6],['1','b3','b5']], augmented:[[0,4,8],['1','3','#5']],
    sus2:[[0,2,7],['1','2','5']], sus4:[[0,5,7],['1','4','5']],
    dominant7:[[0,4,7,10],['1','3','5','b7']], major7:[[0,4,7,11],['1','3','5','7']],
    minor7:[[0,3,7,10],['1','b3','5','b7']], halfDim7:[[0,3,6,10],['1','b3','b5','b7']],
    dim7:[[0,3,6,9],['1','b3','b5','bb7']],
    minor6:[[0,3,7,9],['1','b3','5','6']], major6:[[0,4,7,9],['1','3','5','6']],
    minorMajor7:[[0,3,7,11],['1','b3','5','7']]
  };
  function parseNote(note) {
    const m = /^([A-G])([#b]{0,2})$/.exec(note);
    if (!m) throw new RangeError('音名应为 C、F#、Bb 等');
    return mod(natural[m[1]]+[...m[2]].reduce((n,c)=>n+(c==='#'?1:-1),0));
  }
  function chord(rootNote,quality) {
    if(!types[quality]) throw new RangeError('尚不支持此和弦类型');
    const pc=parseNote(rootNote), letters='CDEFGAB', start=letters.indexOf(rootNote[0]);
    return types[quality][0].map((interval,i)=>{
      const role=types[quality][1][i], degree=Number(role.replace(/[^0-9]/g,''));
      const letter=letters[(start+degree-1)%7], target=mod(pc+interval);
      let accidental=mod(target-natural[letter]); if(accidental>6) accidental-=12;
      const name=letter+(accidental>=0?'#'.repeat(accidental):'b'.repeat(-accidental));
      return {pc:target,interval,role,name};
    });
  }
  function spelledOctave(midi,name) {
    parseNote(name);
    const raw=natural[name[0]]+[...name.slice(1)].reduce((n,c)=>n+(c==='#'?1:-1),0);
    if(mod(midi)!==mod(raw)) throw new RangeError('拼写与音高不一致');
    return (midi-raw)/12-1;
  }
  function position(string,fret,tuning=[28,33,38,43],frets=21) {
    if(!Array.isArray(tuning)||!tuning.length||tuning.some(n=>!Number.isInteger(n)||n<0||n>127)) throw new RangeError('调弦需有效 MIDI 数组');
    if(!Number.isInteger(frets)||frets<0||!Number.isInteger(string)||string<0||string>=tuning.length||!Number.isInteger(fret)||fret<0||fret>frets) throw new RangeError('弦或品位越界');
    const midi=tuning[string]+fret;
    if(midi>127) throw new RangeError('超出 MIDI 音域');
    return {string,fret,midi,pc:mod(midi),name:names[mod(midi)],octave:Math.floor(midi/12)-1,frequency:440*2**((midi-69)/12)};
  }
  function query({root='A',quality='minor7',tuning=[28,33,38,43],frets=21,window=[0,frets]}={}) {
    if(!Array.isArray(window)||window.length!==2||!window.every(Number.isInteger)||window[0]<0||window[1]>frets||window[0]>window[1]) throw new RangeError('品位窗口无效');
    position(0,0,tuning,frets);
    const tones=chord(root,quality),result=[];
    for(let s=0;s<tuning.length;s++)for(let f=window[0];f<=window[1];f++){
      const p=position(s,f,tuning,frets),t=tones.find(t=>t.pc===p.pc);
      if(t)result.push({...p,name:t.name,octave:spelledOctave(p.midi,t.name),role:t.role});
    }
    return result;
  }
  function fretDistance(f1,f2,scaleLength=863.6) {
    if(![f1,f2,scaleLength].every(Number.isFinite)||f1<0||f2<0||scaleLength<=0) throw new RangeError('无效距离参数');
    return Math.abs(scaleLength*(2**(-f1/12)-2**(-f2/12)));
  }
  const api={mod,parseNote,chord,position,query,fretDistance,spelledOctave,types};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.BassModel=api;
})(typeof window!=='undefined'?window:globalThis);
