const assert=require('node:assert/strict');
const R=require('../rhythm-grid.js');
const beats=Array.from({length:520},(_,i)=>.2+i*60/130.7);
const edit={beats,downbeats:beats.filter((_,i)=>i%4===0&&i!==200),beatsPerBar:4};
const g=R.build(edit,240);
for(let i=0;i<beats.length;i++){
 const p=R.position(g,beats[i]+.001);
 assert.equal(p.bar,Math.floor(i/4)+1);assert.equal(p.beat,i%4+1);
}
assert.equal(R.position(g,240),null);
assert.equal(g.downbeats.length,130);
const pickup=R.build({...edit,barAnchorIndex:2},240);
assert.equal(R.position(pickup,beats[0]).bar,0);assert.equal(R.position(pickup,beats[2]).bar,1);
const thirds=R.build({...edit,beatsPerBar:3,barAnchorIndex:0},240);
assert.equal(R.position(thirds,beats[510]).bar,171);
const broken=R.build({...edit,beats:beats.filter((_,i)=>i!==129)},240);
assert.equal(broken.anomalies.length,1);
console.log('PASS: 520 absolute timestamps, missing downbeat, pickup, 3-beat grouping, missing-beat diagnostic.');
const short=R.build({beats:Array.from({length:16},(_,i)=>i*.5),downbeats:[0,2,4,6],beatsPerBar:4},9);
const labels=['C:maj','G:7','X','N'];
// Known score: change halfway through beat 4, sustain across the next bar, silence at 8.1s.
const frames=Array.from({length:90},(_,i)=>{const t=i*.1;return {timeSec:t,scores:t<1.75?[.9,.04,.03,.03]:t<8.1?[.04,.9,.03,.03]:[0,0,0,1]};});
const model={method:{labelOrder:labels},rawFrames:frames,events:[{startSec:0,endSec:8.1,label:'C:maj'},{startSec:8.1,endSec:9,label:'N',reason:'sustained_low_energy'}]};
const aligned=R.beatChords(short,model);
assert.equal(aligned[0].startSec,0);assert.equal(aligned.at(-1).endSec,9);
assert(aligned.some(e=>e.startSec===1.75&&e.label==='G:7'));
assert(aligned.some(e=>e.startSec===8&&e.label==='X')); // No inferred harmony outside beat coverage.
assert(aligned.some(e=>e.startSec===8.1&&e.label==='N'));
const map=R.barHarmony(short,aligned);assert.equal(map[0].events.length,2);
assert.equal(map[1].events[0].label,'G:7');
assert.equal(model.events.length,2); // Derived view never mutates raw candidates.
const uncertain={...model,rawFrames:frames.map(f=>({...f,scores:[.45,.44,.06,.05]}))};
assert.equal(R.beatChords(short,uncertain)[0].label,'X');
console.log('PASS: half-beat change, cross-bar sustain, uncertain score, unknown tail, exact silence and immutable raw candidates.');
const segmented=R.build({beats:Array.from({length:112},(_,i)=>2+i*.5),downbeats:[],beatsPerBar:null,meterSegments:[
 {startBeatIndex:0,endBeatIndex:64,beatsPerBar:4,anchorBeatIndex:0},
 {startBeatIndex:64,endBeatIndex:112,beatsPerBar:3,anchorBeatIndex:64}]},61);
assert.equal(segmented.bars.length,32);assert.equal(R.position(segmented,34).bar,17);assert.equal(R.position(segmented,35.5).beat,1);
assert.equal(segmented.bars[16].meter,3);assert.equal(segmented.downbeats[16],34);
assert.notEqual(segmented.signature,R.build({...edit,meterSegments:[]},240).signature);
const tail=R.build({beats:[2,2.5,3,3.5],downbeats:[2],beatsPerBar:4,activityEndSec:3.6},8);
assert.equal(tail.endSec,3.6);assert.equal(R.position(tail,3.7),null);
console.log('PASS: piecewise 4-to-3 counting, segment signature, acoustic tail cap.');
