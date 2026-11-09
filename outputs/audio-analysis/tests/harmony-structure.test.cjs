const assert=require('node:assert/strict'),R=require('../rhythm-grid.js'),H=require('../harmony-structure.js');
const labels=['A:min','A:min7','D:maj','E:7','X','N'];
const strong=k=>labels.map((_,i)=>i===k?.95:.01);
const uncertain=[.24,.23,.23,.22,.04,.04];
function fixture(fn,duration=8){
 const grid=R.build({beats:Array.from({length:duration*2},(_,i)=>i*.5),downbeats:Array.from({length:duration/2},(_,i)=>i*2),beatsPerBar:4},duration);
 const result={durationSec:duration,method:{labelOrder:labels},rawFrames:Array.from({length:duration*100},(_,i)=>({timeSec:i/100,scores:fn(i/100)})),events:[{startSec:0,endSec:duration,label:'X'}]};
 return {grid,result};
}
function run(fn,duration=8){const {grid,result}=fixture(fn,duration);const before=JSON.stringify(result);const r=H.decode(grid,result);assert.equal(JSON.stringify(result),before);assert.equal(r.events[0].startSec,0);assert.equal(r.events.at(-1).endSec,duration);for(let i=1;i<r.events.length;i++)assert.equal(r.events[i].startSec,r.events[i-1].endSec);return r;}
let r=run(t=>t>.8&&t<1?uncertain:strong(0));assert.deepEqual(r.events.map(e=>e.label),['A:min']);
r=run(t=>t>=1.96&&t<2?strong(1):t<2?strong(0):strong(1));assert.deepEqual(r.events.map(e=>[e.startSec,e.label]),[[0,'A:min'],[2,'A:min7']]);
r=run(t=>t<1?strong(0):strong(2));assert.equal(r.events[1].startSec,1); // Two chords per bar.
r=run(t=>t<1.75?strong(0):strong(2));assert.equal(r.events[1].startSec,1.75); // Strong half-beat anticipation.
r=run(t=>strong(Math.floor(t/.5)%2?2:0));assert.equal(r.bars[0].spans.length,4); // No hard maximum of two.
r=run(t=>t>=.5&&t<1.5?uncertain:strong(0));assert(r.events.some(e=>e.label==='X'&&e.endSec-e.startSec>=1));
r=run(()=>[.45,.44,.03,.03,.03,.02]);assert.deepEqual(r.events.map(e=>e.label),['X']);
r=run(()=>strong(1));assert.deepEqual(r.events.map(e=>e.label),['A:min7']); // No blanket downgrade of seventh chords.
const f=fixture(()=>strong(0));f.result.events=[{startSec:0,endSec:3.13,label:'A:min'},{startSec:3.13,endSec:3.77,label:'N',reason:'sustained_low_energy'},{startSec:3.77,endSec:8,label:'A:min'}];
r=H.decode(f.grid,f.result);assert(r.events.some(e=>e.label==='N'&&e.startSec===3.13&&e.endSec===3.77));
const short=fixture(()=>strong(0));short.grid=R.build({beats:[.25,.75,1.25,1.75],downbeats:[.25],beatsPerBar:4},8);short.result.events=[{startSec:0,endSec:8,label:'E:7'}];r=H.decode(short.grid,short.result);assert.equal(r.events[0].label,'E:7');assert.equal(r.events.at(-1).label,'E:7');
console.log('PASS: brief X bridge, bar-edge bleed, two/four chords per bar, strong anticipation, sustained unknown, ambiguity, seventh preservation, exact silence, outside-grid preservation, no input mutation.');
const advice=H.learningAdvice([.46,.44,.03,.02,.03,.02],labels,[{label:'X',score:.46,margin:.02}]);
assert.equal(advice.level,'root');assert.equal(advice.root,'A');assert.equal(advice.chord,null);
assert.equal(H.learningAdvice([.45,.02,.44,.03,.03,.03],labels,[{label:'X'}]).level,'rhythm');
assert.equal(H.learningAdvice([.05,.02,.03,.02,.85,.03],labels,[{label:'X'}]).level,'rhythm');
assert.equal(H.learningAdvice(strong(0),labels,[{label:'A:min',score:.95,margin:.94}]).level,'chord');
assert.equal(H.learningAdvice(strong(0),labels,[{label:'A:min'},{label:'D:maj'}]).level,'rhythm');
assert.equal(H.learningAdvice(strong(0),labels,[{label:'N'}]).level,'rest');
console.log('PASS: beginner root-only evidence, conflicting roots, unknown mass, strong chord, multiple roots, rest.');
// Regression: a hard-unknown run followed by one moderate half-beat had no DP path.
r=run(t=>t<1?strong(0):t<1.75?uncertain:[.47,.07,.06,.05,.3,.05]);
assert(r.events.some(e=>e.label==='X'));
const local=fixture(()=>strong(0));local.grid.bars[1].uncertain=true;
r=H.decode(local.grid,local.result);assert.equal(r.bars[0].learning.level,'chord');assert.equal(r.bars[1].learning.level,'rhythm');assert.equal(r.bars[2].learning.level,'chord');
const toneLabels=['C:maj','C:maj7','A:min7','C:maj6','X','N'];
assert.equal(H.corroborate([1,0,0,0,1,0,0,1,0,0,0,1],[.1,.2,.01,.01,.03,.65],toneLabels)?.label,'C:maj7');
assert.equal(H.corroborate([1,0,0,0,1,0,0,1,0,1,0,0],[.1,.1,.3,.3,.1,.1],toneLabels),null); // C6 / Am7 same pitch set.
assert.equal(H.corroborate([1,0,0,0,1,0,0,1,0,0,0,1],[.3,.1,.01,.01,.03,.55],toneLabels),null); // Acoustic / BTC disagreement.
console.log('PASS: DP fallback path, local-only degradation, tonal agreement and ambiguous-root refusal.');
