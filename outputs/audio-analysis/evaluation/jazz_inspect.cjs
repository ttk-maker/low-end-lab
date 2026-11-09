const fs=require('fs'),R=require('../rhythm-grid.js'),H=require('../harmony-structure.js');
const [input,output]=process.argv.slice(2),d=JSON.parse(fs.readFileSync(input)),a=d.analysis,c=d.chords;
const grid=R.build({beats:a.beats,downbeats:a.downbeats,beatsPerBar:a.beatsPerBarCandidate,meterSegments:a.meterSegments,activityEndSec:a.activityEndSec},a.durationSec);
let stable=null,error=null;try{stable=H.decode(grid,c);}catch(e){error=e.message;}
const occupancy=events=>{const counts={};for(const e of events)counts[e.label]=(counts[e.label]||0)+e.endSec-e.startSec;return {unknownSeconds:counts.X||0,noChordSeconds:counts.N||0,shorterThan200ms:events.filter(e=>e.endSec-e.startSec<.2).length,events:events.length};};
const distribution={};for(const b of stable?.bars||[])distribution[b.learning.level]=(distribution[b.learning.level]||0)+1;
fs.writeFileSync(output,JSON.stringify({meter:grid.meter,bars:grid.bars.length,downbeats:grid.downbeats,normalBars:grid.bars.filter(b=>!b.uncertain).length,uncertainBars:grid.bars.filter(b=>b.uncertain).length,normalSeconds:grid.bars.filter(b=>!b.uncertain).reduce((v,b)=>v+b.endSec-b.startSec,0),tonalCorroboratedBars:stable?.bars.filter(b=>b.tonalCorroboration).length||0,endSec:grid.endSec,anomalies:grid.anomalies,conflicts:grid.conflicts,
 stableAvailable:!!stable,stableError:error,raw:occupancy(c.events),stable:stable?occupancy(stable.events):null,
 learning:distribution,barFragmentCounts:stable?.bars.map(b=>({bar:b.number,raw:b.originalFragments,stable:b.stableFragments,omitted:b.omittedLabels})),proposal:stable},null,2));
