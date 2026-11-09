const fs=require('fs'),R=require('../rhythm-grid.js'),H=require('../harmony-structure.js');
const [input,output]=process.argv.slice(2);const {result,grid}=JSON.parse(fs.readFileSync(input,'utf8'));
fs.writeFileSync(output,JSON.stringify(H.decode(R.build(grid,result.durationSec),result)));
