"""Additional composed cases after fixing tonal-evidence parameters; not real jazz."""
import sys,json
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chords import analyze_chords
from jazz_fixes import inspect,write
from run import score

def main():
    out=Path('outputs/audio-analysis/evaluation/jazz-fixes-2026-11-08');work=Path('work/v07-fixes/validation');work.mkdir(parents=True,exist_ok=True);rows=[]
    for name,plan in [('Ebmaj7',[(2,18,3,'maj7')]),('Fmin7',[(2,18,5,'min7')]),('two_chords',[(2+i,3+i,3 if i%2==0 else 8,'maj7' if i%2==0 else '7') for i in range(16)])]:
        sr=22050;y=np.zeros(sr*20);rng=np.random.default_rng(903);quality={'maj7':[0,4,7,11],'min7':[0,3,7,10],'7':[0,4,7,10]};roots=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        def tone(midi,d,amp):
            t=np.arange(round(d*sr))/sr;f=440*2**((midi-69)/12)
            return amp*(np.sin(2*np.pi*f*t)+.22*np.sin(4*np.pi*f*t)+.08*np.sin(6*np.pi*f*t))*np.minimum(1,t/.008)*np.exp(-t*2.8)
        def add(t,v):
            k=round(t*sr);y[k:k+len(v)]+=v
        for a,b,pc,q in plan:
            for start in np.arange(a,b,2):
                for iv in quality[q]:add(start,tone(48+pc+iv,min(2,b-start),.055))
            for i,t in enumerate(np.arange(a,b,.5)):
                add(t,tone(36+pc+quality[q][i%4],.44,.12));h=np.arange(880)/sr
                add(t,rng.normal(0,.015,len(h))*np.exp(-h*100));add(t+1/3,rng.normal(0,.01,len(h))*np.exp(-h*100))
        path=work/(name+'.wav');sf.write(path,np.tanh(y),sr);c=analyze_chords(path,name)
        a={'durationSec':20,'beats':np.arange(2,18,.5).tolist(),'downbeats':np.arange(2,18,2).tolist(),'beatsPerBarCandidate':4}
        d=inspect(a,c,out/'additional'/(name+'.json'));reference=[(0,2,'N')]+[(a,b,roots[pc]+':'+q) for a,b,pc,q in plan]+[(18,20,'N')]
        baseline=json.loads(json.dumps(c))
        for f in baseline['rawFrames']:f.pop('pitchEnergy',None)
        old=inspect(a,baseline,out/'additional'/(name+'-without-tonal.json'))
        rows.append({'name':name,'before':score(reference,old['proposal']['events']),'after':score(reference,d['proposal']['events']),'tonalCorroboratedBars':d['tonalCorroboratedBars'],'wholeBarSpans':[len(b['spans']) for b in d['proposal']['bars']]})
        print(json.dumps(rows[-1]),flush=True)
    write(out/'additional-harmony.json',{'parametersFrozenBeforeRun':True,'knownScoreNotRealSongAccuracy':True,'rows':rows})

if __name__=='__main__':main()
