const assert=require('node:assert/strict'),T=require('../chord-theory.js'),M=require('../../fretboard-model.js');
const event=(label,bassNote=null,status='confirmed')=>({id:'test',startSec:0,endSec:4,label,bassNote,status});
assert.deepEqual(T.explain(event('A:min7')).tones.map(x=>x.name),['A','C','E','G']);
assert.deepEqual(T.explain(event('C#:minmaj7')).tones.map(x=>x.name),['C#','E','G#','B#']);
assert.deepEqual(T.explain(event('C:dim7')).tones.map(x=>x.name),['C','Eb','Gb','Bbb']);
assert.deepEqual(T.explain(event('F:maj6')).tones.map(x=>x.name),['F','A','C','D']);
let slash=T.explain(event('G:maj','B'));assert.equal(slash.root,'G');assert.match(slash.bassMeaning,/大三度/);assert.equal(slash.bassNote,'B');
assert.match(T.explain(event('G:maj','F')).bassMeaning,/不在/);
assert.equal(T.explain(event('A:min7',null,'candidate')).available,false);assert.equal(T.explain(event('X')).available,false);assert.equal(T.explain(event('N')).available,false);
for(const quality of Object.keys(T.qualityMap))for(const root of ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']){const t=T.explain(event(root+':'+quality));assert(t.tones.every(n=>M.parseNote(n.name)===n.pc));assert(t.exercise.includes('四分音符'));}
console.log('Step 3: 168 root/quality combinations, spelling, inversion and abstention passed');
