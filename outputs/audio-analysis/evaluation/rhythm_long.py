"""Reproducible long-form synthetic audio test, not a real-song benchmark.
Run: python rhythm_long.py --work-dir <scratch directory> --report <report.json>
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import beat_tracker
from rhythm import review

def make_audio(path,kind):
    sr=22050;duration=180. if kind=='triple_swing' else 240.;rng=np.random.default_rng({'steady':2401,'variable':2402,'triple_swing':2403}[kind])
    meter=3 if kind=='triple_swing' else 4
    beats=[];t=.3;i=0
    while t<duration-.5:
        beats.append(t);t+=60/(123.456 if kind=='steady' else 96 if kind=='triple_swing' else 112+16*t/duration);i+=1
    beats=np.array(beats);audio=np.zeros(int(sr*duration),dtype=np.float32)
    def add(t,sound,gain=1):
        k=round(t*sr);n=min(len(sound),len(audio)-k)
        if k>=0 and n>0:audio[k:k+n]+=sound[:n]*gain
    x=np.arange(int(sr*.22))/sr
    kick=np.sin(2*np.pi*(48*x+2*(1-np.exp(-x*30))))*np.exp(-x*23)
    snare=rng.normal(0,1,len(x))*np.exp(-x*36)
    h=np.arange(int(sr*.045))/sr;hat=rng.normal(0,1,len(h))*np.exp(-h*100)
    for i,t in enumerate(beats):
        p=beats[i+1]-t if i+1<len(beats) else beats[i]-beats[i-1]
        add(t,kick,.55 if i%meter==0 else .12)
        if i%meter in (1,3):add(t,snare,.2)
        add(t,hat,.07);add(t+p*(2/3 if kind=='triple_swing' else .5),hat,.045)
        root=[55,65.406,73.416,49][(i//16)%4]
        n=np.arange(int(sr*p*.85))/sr
        bass=(np.sin(2*np.pi*root*n)+.25*np.sin(4*np.pi*root*n))*np.exp(-n*7)
        add(t,bass,.17)
    audio=np.tanh(audio)*.7
    sf.write(path,audio,sr,subtype='PCM_16')
    return audio,beats,duration,meter

def metrics(pred,truth):
    pred=np.asarray(pred);used=set();errs=[];matched=[]
    for k,t in enumerate(truth):
        if not len(pred):break
        i=int(np.argmin(np.abs(pred-t)))
        if i not in used and abs(pred[i]-t)<=.07:
            used.add(i);errs.append(float(pred[i]-t));matched.append((k,i))
    n=len(errs);precision=n/max(1,len(pred));recall=n/len(truth)
    bins=[]
    for start in range(0,240,60):
        e=[float(pred[i]-truth[k]) for k,i in matched if start<=truth[k]<start+60]
        bins.append({'startSec':start,'matched':len(e),'medianSignedErrorMs':round(float(np.median(e))*1000,2) if e else None})
    return {'count':len(pred),'truthCount':len(truth),'f1At70ms':2*precision*recall/max(1e-9,precision+recall),
            'p95AbsoluteErrorMs':float(np.percentile(np.abs(errs),95)*1000) if errs else None,
            'perMinute':bins,'oneToOneMatching':True,
            'matchedBeatIndexErrors':sum(k!=i for k,i in matched)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--work-dir',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    work=Path(a.work_dir);work.mkdir(parents=True,exist_ok=True);rows=[];tracker=beat_tracker()
    for kind in ('steady','variable','triple_swing'):
        path=work/(kind+'-long.wav');audio,truth,duration,meter=make_audio(path,kind)
        started=time.monotonic();beats,downs=tracker(audio,22050)
        annotation={'beats':list(map(float,beats)),'downbeats':list(map(float,downs)),'beatsPerBar':meter}
        proposal=review(path,annotation,duration,'repair')
        row={'kind':kind,'durationSec':duration,'meterGivenByFixture':meter,'raw':metrics(beats,truth),'repaired':metrics(proposal['beats'],truth),
             'groupedDownbeats':metrics(proposal['downbeats'],truth[::meter]),
             'changes':proposal['changes'],'unresolved':proposal['unresolved'],'elapsedSec':round(time.monotonic()-started,2)}
        # Separate assisted condition: the score supplies the first downbeat index.
        anchor=int(np.argmin(np.abs(np.asarray(proposal['beats'])-truth[0])))
        row['assistedFirstBeatGiven']=metrics(proposal['beats'][anchor::meter],truth[::meter])
        try:
            fitted=review(path,annotation,duration,'steady');row['steadyFit']=metrics(fitted['beats'],truth);row['fit']=fitted['fit']
        except ValueError as e:row['steadyFitRejected']=str(e)
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        (work/(kind+'-reference.json')).write_text(json.dumps({'beats':truth.tolist(),'downbeats':truth[::meter].tolist(),'rawBeats':annotation['beats'],'rawDownbeats':annotation['downbeats'],'proposal':proposal}),encoding='utf8')
    report={'kind':'synthetic three-to-four-minute regression; not real-song accuracy','beatModel':'Beat This! small0; weights unchanged','rows':rows}
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
