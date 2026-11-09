"""Known-score controls separate from unlabeled real jazz."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import analyze
from chords import analyze_chords
from rhythm_long import metrics

def main():
    p=argparse.ArgumentParser();p.add_argument('--work-dir',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    out=Path(a.work_dir);out.mkdir(parents=True,exist_ok=True);rows=[]
    for name,meters,swing in [('swing_4',[4]*32,True),('meter_4_to_3',[4]*16+[3]*16,False)]:
        sr=22050;beat=.5;first=2.;duration=first+sum(meters)*beat+3;y=np.zeros(round(duration*sr),dtype='float32');rng=np.random.default_rng(812)
        x=np.arange(round(.18*sr))/sr;kick=np.sin(2*np.pi*65*x)*np.exp(-x*25);snare=rng.normal(0,1,len(x))*np.exp(-x*40)
        h=np.arange(round(.035*sr))/sr;hat=rng.normal(0,1,len(h))*np.exp(-h*100)
        truth=[];down=[];t=first
        def add(t,s,g):
            k=round(t*sr);y[k:k+len(s)]+=s*g
        for meter in meters:
            down.append(t)
            for k in range(meter):
                truth.append(t);add(t,kick,.6 if k==0 else .18)
                if k>0:add(t,snare,.1)
                add(t,hat,.07);add(t+beat*(2/3 if swing else .5),hat,.04)
                t+=beat
        path=out/(name+'.wav');sf.write(path,y,sr);r=analyze(path);c=analyze_chords(path,r['id'])
        (out/(name+'-analysis.json')).write_text(json.dumps(r),encoding='utf8');(out/(name+'-chords.json')).write_text(json.dumps(c),encoding='utf8')
        intervals=[(0,2),(t+.2,duration)]
        rows.append({'name':name,'durationSec':duration,'referenceMeterSequence':meters,'referenceChangeSec':34 if name=='meter_4_to_3' else None,
         'beatMetrics':metrics(r['beats'],np.array(truth)),'downbeatMetrics':metrics(r['downbeats'],np.array(down)),
         'globalMeterOutput':r['beatsPerBarCandidate'],'hasMeterChangeTimeline':False,
         'beatsInExactSilence':[b for b in r['beats'] if any(lo<=b<hi for lo,hi in intervals)],
         'nonNSecondsInExactSilence':sum(max(0,min(e['endSec'],hi)-max(e['startSec'],lo)) for e in c['events'] if e['label']!='N' for lo,hi in intervals)})
    Path(a.report).write_text(json.dumps({'kind':'known-score synthetic controls, separate from real jazz','rows':rows},ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(rows,ensure_ascii=False))

if __name__=='__main__':main()
