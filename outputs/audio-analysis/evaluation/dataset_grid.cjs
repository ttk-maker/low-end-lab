const fs=require('fs'),R=require('../rhythm-grid.js');
const [input,output]=process.argv.slice(2),a=JSON.parse(fs.readFileSync(input));
fs.writeFileSync(output,JSON.stringify(R.build({beats:a.beats,downbeats:a.downbeats,beatsPerBar:a.beatsPerBarCandidate,meterSegments:a.meterSegments,activityEndSec:a.activityEndSec},a.durationSec)));
