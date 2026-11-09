/* Evaluate derived beat cells using a supplied (independently annotated) grid. */
const fs=require('fs'),R=require('../rhythm-grid.js');
const [input,output]=process.argv.slice(2);
const {result,grid}=JSON.parse(fs.readFileSync(input,'utf8'));
const g=R.build(grid,result.durationSec);
fs.writeFileSync(output,JSON.stringify({events:R.beatChords(g,result),bars:R.barHarmony(g,result.events)}));
