"""Isolate chord aggregation from beat recognition using a known composition grid."""
import argparse,json,subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from run import synth,score
from chords import analyze_chords

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    work=Path(args.work_dir);work.mkdir(parents=True,exist_ok=True)
    reference=[(0,4,'C:maj'),(4,7.75,'A:min7'),(7.75,12,'F:maj'),(12,14.5,'G:7'),(14.5,20,'C:maj'),(20,24,'N')]
    y,sr=synth(reference,1,606)
    # Explicit 120 BPM, 4 beats/bar score; grid is supplied, not inferred here.
    audio=work/'harmony-grid.wav';sf.write(audio,y,sr,subtype='FLOAT')
    result=analyze_chords(audio,'harmony-grid')
    grid={'beats':np.arange(0,20,.5).tolist(),'downbeats':np.arange(0,20,2).tolist(),'beatsPerBar':4,'barAnchorIndex':0}
    inp=work/'input.json';out=work/'derived.json';inp.write_text(json.dumps({'result':result,'grid':grid}),encoding='utf8')
    subprocess.run(['node',str(Path(__file__).with_name('beat_chords.cjs')),str(inp),str(out)],check=True)
    derived=json.loads(out.read_text())
    report={'kind':'synthetic musical score; known beat grid supplied, not end-to-end song accuracy',
            'reference':[{'startSec':a,'endSec':b,'label':label} for a,b,label in reference],
            'baseline':score(reference,result['events']),'beatCells':score(reference,derived['events']),
            'candidateEvents':derived['events'],'limitations':['Half-beat cells cannot represent all triplets, swing or free-time changes.','No model weights changed.']}
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:report[k] for k in ('baseline','beatCells')},ensure_ascii=False))

if __name__=='__main__':main()
