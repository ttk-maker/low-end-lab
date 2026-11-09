"""Audit frozen pipeline on local audio, retaining raw evidence outside deliverables."""
import argparse,hashlib,json,sys,time,subprocess,traceback
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import analyze
from chords import analyze_chords,validate_annotation
from rhythm import review

def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def quiet_edges(path,duration):
    y,sr=sf.read(path,dtype='float32',always_2d=True);hop=round(sr*.02)
    power=np.mean(y.astype('float64')**2,axis=1);power=np.pad(power,(0,(-len(power))%hop))
    rms=np.sqrt(power.reshape(-1,hop).mean(axis=1));threshold=max(1e-5,float(np.percentile(rms,95))*.005)
    active=np.flatnonzero(rms>=threshold)
    if not len(active):return {'thresholdRms':threshold,'intervals':[[0,duration]]}
    start=active[0]*hop/sr;end=min(duration,(active[-1]+1)*hop/sr)
    return {'thresholdRms':threshold,'intervals':([[0,start]] if start>=.3 else [])+([[end,duration]] if duration-end>=.3 else [])}
def core(c):return [(e['startSec'],e['endSec'],e['label']) for e in c['events']]

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--work-dir',required=True);p.add_argument('--report-dir',required=True);args=p.parse_args()
    work=Path(args.work_dir);out=Path(args.report_dir);work.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for file in sorted(Path(args.source).glob('*.mp3')):
        digest=hashlib.sha256(file.read_bytes()).hexdigest();folder=work/digest[:20];folder.mkdir(exist_ok=True)
        row={'file':file.name,'sha256':digest,'bytes':file.stat().st_size};started=time.monotonic()
        print('START '+file.name,flush=True)
        try:
            a=analyze(file);save(folder/'analysis.json',a);print('BEATS '+str(len(a['beats'])),flush=True)
            c=analyze_chords(file,a['id']);save(folder/'chords.json',c);print('CHORDS '+str(len(c['events'])),flush=True)
            validate_annotation({'events':c['events']},a['durationSec'])
            row.update(durationSec=a['durationSec'],beatSeconds=a['analysisSeconds'],chordSeconds=c['analysisSeconds'],beatCount=len(a['beats']),downbeatCount=len(a['downbeats']),bpm=a['bpm'],meter=a['beatsPerBarCandidate'],beatTask=a['taskStatus']['beats'],coverageValid=True,warnings=a['warnings'])
            bs=np.array(a['beats']);gaps=np.diff(bs)
            row['beatsValid']=bool(np.all(gaps>0) and np.all(bs>=0) and np.all(bs<a['durationSec']))
            row['perMinute']=[{'startSec':t,'beats':int(np.sum((bs>=t)&(bs<t+60))),
              'medianBpm':float(60/np.median(gaps[(bs[:-1]>=t)&(bs[:-1]<t+60)])) if np.any((bs[:-1]>=t)&(bs[:-1]<t+60)) else None} for t in range(0,int(a['durationSec'])+1,60)]
            indices=[int(np.argmin(np.abs(bs-t))) for t in a['downbeats']] if len(bs) else []
            values,counts=np.unique(np.diff(indices),return_counts=True);row['downbeatBeatCountHistogram']={str(v):int(n) for v,n in zip(values,counts)}
            silence=quiet_edges(file,a['durationSec'])
            silence['beatsInQuietEdges']=[float(t) for t in bs if any(lo<=t<hi for lo,hi in silence['intervals'])]
            silence['nonNSeconds']=sum(max(0,min(e['endSec'],hi)-max(e['startSec'],lo)) for e in c['events'] if e['label']!='N' for lo,hi in silence['intervals'])
            row['quietEdges']=silence
            inp=folder/'combined.json';save(inp,{'analysis':a,'chords':c})
            subprocess.run(['node',str(Path(__file__).with_name('jazz_inspect.cjs')),str(inp),str(folder/'structure.json')],check=True)
            structure=json.loads((folder/'structure.json').read_text());row['structure']={k:v for k,v in structure.items() if k!='proposal'}
            try:
                r=review(file,{'beats':a['beats'],'downbeats':a['downbeats'],'beatsPerBar':a['beatsPerBarCandidate']},a['durationSec'],'repair');save(folder/'repair.json',r)
                row['repair']={'changes':r['changes'],'unresolved':r['unresolved']}
            except Exception as e:row['repair']={'error':str(e)}
            print('REPEAT '+file.name,flush=True)
            a2=analyze(file);c2=analyze_chords(file,a['id']);save(folder/'repeat-analysis.json',a2);save(folder/'repeat-chords.json',c2)
            row['repeat']={'beatsExact':a['beats']==a2['beats'],'downbeatsExact':a['downbeats']==a2['downbeats'],'chordEventsExact':core(c)==core(c2),
              'scoresMaxAbsDifference':float(np.max(np.abs(np.array([f['scores'] for f in c['rawFrames']])-np.array([f['scores'] for f in c2['rawFrames']]))))}
            row['status']='complete'
        except Exception as e:
            row.update(status='failed',errorType=type(e).__name__,error=str(e));(folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf8')
        row['totalAuditSeconds']=round(time.monotonic()-started,2);rows.append(row);save(out/'results.json',{'baseline':'v0.6.2','referenceAnnotations':False,'rows':rows})
        print('DONE '+json.dumps(row,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
