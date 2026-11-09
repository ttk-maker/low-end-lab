"""Fixed composed harmony plus walking bass and swing: a labeled control only."""
import argparse,json,sys,subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chords import analyze_chords
from run import score

def main():
    p=argparse.ArgumentParser();p.add_argument('--work-dir',required=True);p.add_argument('--report',required=True);args=p.parse_args()
    out=Path(args.work_dir);out.mkdir(parents=True,exist_ok=True);sr=22050;duration=36;y=np.zeros(sr*duration);rng=np.random.default_rng(811)
    def add(t,s):
        k=round(t*sr);y[k:k+len(s)]+=s
    def tone(midi,seconds,amp):
        t=np.arange(round(seconds*sr))/sr;freq=440*2**((midi-69)/12)
        return amp*(np.sin(2*np.pi*freq*t)+.25*np.sin(4*np.pi*freq*t)+.1*np.sin(6*np.pi*freq*t))*np.minimum(1,t/.008)*np.exp(-t*3)
    for bar in range(16):
        start=2+bar*2
        # Sustained complete Cmaj7 comping; rhythm and bass articulation vary.
        for midi in [48,55,59,64]:add(start,tone(midi,2,.065))
        for beat in range(4):
            t=start+beat*.5;add(t,tone([36,40,43,47][beat],.45,.13))
            h=np.arange(round(.04*sr))/sr;add(t,rng.normal(0,1,len(h))*.018*np.exp(-h*100));add(t+1/3,rng.normal(0,1,len(h))*.012*np.exp(-h*100))
        if bar%2:add(start+1.83,tone(38,.16,.04)) # Quiet passing D, not a composed chord change.
    file=out/'constant-Cmaj7-swing-walking.wav';sf.write(file,np.tanh(y),sr)
    c=analyze_chords(file,'constant-jazz-control');(out/'chords.json').write_text(json.dumps(c),encoding='utf8')
    reference=[(0,2,'N'),(2,34,'C:maj7'),(34,36,'N')]
    raw=score(reference,c['events']);root_ref=[(a,b,l.split(':')[0] if ':' in l else l) for a,b,l in reference]
    root_events=[{**e,'label':e['label'].split(':')[0] if ':' in e['label'] else e['label']} for e in c['events']]
    result={'kind':'synthetic composed constant Cmaj7, swing subdivisions, walking chord tones and quiet passing note; not real-song accuracy',
            'reference':[{'startSec':a,'endSec':b,'label':l} for a,b,l in reference],'raw':raw,'rawRoot':score(root_ref,root_events)}
    grid={'beats':np.arange(2,34,.5).tolist(),'downbeats':np.arange(2,34,2).tolist(),'beatsPerBar':4,'barAnchorIndex':0}
    inp=out/'input.json';inp.write_text(json.dumps({'result':c,'grid':grid}),encoding='utf8')
    proc=subprocess.run(['node',str(Path(__file__).with_name('stable_chords.cjs')),str(inp),str(out/'stable.json')],capture_output=True,text=True)
    if proc.returncode:result['stableError']='decoder failed; see control work folder';(out/'stable-error.txt').write_text(proc.stderr,encoding='utf8')
    else:
        stable=json.loads((out/'stable.json').read_text());result['stable']=score(reference,stable['events'])
        result['stableRoot']=score(root_ref,[{**e,'label':e['label'].split(':')[0] if ':' in e['label'] else e['label']} for e in stable['events']])
        result['barLabels']=[{'bar':b['number'],'labels':[s['label'] for s in b['spans']]} for b in stable['bars']]
    Path(args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
