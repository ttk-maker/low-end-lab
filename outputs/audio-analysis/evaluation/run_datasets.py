"""Reference-aware evaluation adapters, separate from production projects.

Initial runs use diagnostic only. Test split selection must be explicit. Input
reference labels never enter the audio model; oracle grid is reported separately.
"""
import argparse,collections,hashlib,json,sys,time,subprocess,warnings
from pathlib import Path
import numpy as np
import mir_eval
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import analyze
from chords import analyze_chords
from dataset_io import DATA,REPORT,save,digest

def rhythm_scores(pred,truth,duration):
    a=np.asarray(truth,dtype=float);b=np.asarray(pred,dtype=float)
    if not len(a):return None
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        c=mir_eval.beat.continuity(a,b)
        out={'f1At70ms':mir_eval.beat.f_measure(a,b,f_measure_threshold=.07),
             'f1At30ms':mir_eval.beat.f_measure(a,b,f_measure_threshold=.03),
             'CMLc':c[0],'CMLt':c[1],'AMLc':c[2],'AMLt':c[3],
             'referenceCount':len(a),'predictedCount':len(b),'trimStartSeconds':0}
    matches=mir_eval.util.match_events(a,b,.07);errors=[(float(a[i]),float(b[j]-a[i])) for i,j in matches]
    out['p95AbsoluteErrorMs']=float(np.percentile([abs(e)*1000 for _,e in errors],95)) if errors else None
    out['perMinute']=[{'startSec':start,'matched':len(e:=[v*1000 for t,v in errors if start<=t<start+60]),
                       'medianSignedErrorMs':float(np.median(e)) if e else None} for start in range(0,int(duration)+1,60)]
    return out

def chord_scores(reference,events):
    # Score only annotated intervals; X means unavailable reference, never N.
    ref=[e for e in reference if e['label']!='X'];total=sum(e['endSec']-e['startSec'] for e in ref)
    if not total:return None
    cuts=sorted({t for e in ref+events for t in [e['startSec'],e['endSec']]});weights=[];truth=[];pred=[]
    i=j=0
    for a,b in zip(cuts,cuts[1:]):
        t=(a+b)/2
        while i<len(ref) and ref[i]['endSec']<=t:i+=1
        while j<len(events) and events[j]['endSec']<=t:j+=1
        if i>=len(ref) or not ref[i]['startSec']<=t<ref[i]['endSec']:continue
        truth.append(ref[i]['label']);pred.append(events[j]['label'] if j<len(events) and events[j]['startSec']<=t<events[j]['endSec'] else 'X');weights.append(b-a)
    w=np.asarray(weights);out={'annotatedSeconds':total,'unknownReferenceSeconds':sum(e['endSec']-e['startSec'] for e in reference if e['label']=='X'),
                             'predictionCoverage':float(w[np.array([p!='X' for p in pred])].sum()/total)}
    for name,fn in [('root',mir_eval.chord.root),('majmin',mir_eval.chord.majmin),('triads',mir_eval.chord.triads),('sevenths',mir_eval.chord.sevenths),('tetrads',mir_eval.chord.tetrads)]:
        s=fn(truth,pred);keep=s>=0;seconds=float(w[keep].sum());out[name]={'accuracy':float(np.dot(s[keep],w[keep])/seconds) if seconds else None,'scoredSeconds':seconds,'excludedSeconds':total-seconds}
    out['exactLabelDurationAccuracy']=float(np.dot(np.array(truth)==np.array(pred),w)/total)
    known=np.array([p!='X' for p in pred]);out['exactSelectiveAccuracy']=float(np.dot((np.array(truth)==np.array(pred))[known],w[known])/w[known].sum()) if known.any() else None
    boundaries=np.array([e['startSec'] for i,e in enumerate(ref) if i and e['label']!=ref[i-1]['label'] and abs(e['startSec']-ref[i-1]['endSec'])<1e-5])
    estimates=np.array([e['startSec'] for i,e in enumerate(events) if i and e['label']!=events[i-1]['label'] and ref[0]['startSec']<e['startSec']<ref[-1]['endSec']])
    matched=len(mir_eval.util.match_events(boundaries,estimates,.2)) if len(boundaries) and len(estimates) else 0
    out['boundariesAt200ms']={'precision':matched/len(estimates) if len(estimates) else None,'recall':matched/len(boundaries) if len(boundaries) else None,'reference':len(boundaries),'predicted':len(estimates)}
    return out

def candidates(items,task,split,limit):
    selected=[i for i in items if i['split']==split and i['eligible'].get('beat' if task=='rhythm' else 'chord')]
    if task=='chord' and any('performanceStyle' in i for i in selected):selected=[i for i in selected if i.get('performanceStyle')=='comp']
    # Round-robin strata fixed before any predictions, with deterministic order.
    buckets=collections.defaultdict(list)
    for i in selected:buckets[i.get('genre',i.get('style','all'))].append(i)
    for bucket in buckets.values():bucket.sort(key=lambda i:hashlib.sha256(i['id'].encode()).hexdigest())
    order=[]
    while any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key]:order.append(buckets[key].pop(0))
    return order[:limit] if limit else order

def main():
    ap=argparse.ArgumentParser();ap.add_argument('dataset',choices=['gtzan','guitarset','pop909']);ap.add_argument('--task',choices=['rhythm','chord'],required=True);ap.add_argument('--split',choices=['diagnostic','frozen_test'],default='diagnostic');ap.add_argument('--limit',type=int,default=10);args=ap.parse_args()
    manifest=REPORT/(args.dataset+'-manifest.json');d=json.loads(manifest.read_text('utf8'));selected=candidates(d['items'],args.task,args.split,args.limit)
    if not selected:raise ValueError('No eligible items selected')
    work=DATA/'runs'/f'{args.dataset}-{args.task}-{args.split}';work.mkdir(parents=True,exist_ok=True)
    report={'dataset':args.dataset,'task':args.task,'split':args.split,'selectionIds':[i['id'] for i in selected],'selectedBeforePredictions':True,'trainingPerformed':False,'rows':[]}
    destination=REPORT/f'{args.dataset}-{args.task}-{args.split}-report.json';save(destination,report)
    for item in selected:
        started=time.monotonic()
        if args.dataset=='pop909':
            from render_pop909 import render_item
            render_item(item,REPORT)
        path=(manifest.parent/item['audio']).resolve();row={'id':item['id'],'durationSec':item['durationSec'],'audioSha256':digest(path),'referenceProvenance':item.get('referenceSource')}
        if item.get('audioSha256') and row['audioSha256']!=item['audioSha256']:raise ValueError('Audio changed since import')
        try:
            if args.task=='rhythm':
                a=analyze(path);save(work/(item['id']+'-analysis.json'),a)
                subprocess.run(['node',str(Path(__file__).with_name('dataset_grid.cjs')),str(work/(item['id']+'-analysis.json')),str(work/(item['id']+'-grid.json'))],check=True)
                grid=json.loads((work/(item['id']+'-grid.json')).read_text('utf8'));ref=item['reference'];duration=item['durationSec']
                row.update(rawBeat=rhythm_scores(a['neuralRawBeats'],ref['beats'],duration),processedBeat=rhythm_scores(a['beats'],ref['beats'],duration),
                           rawDownbeat=rhythm_scores(a['neuralRawDownbeats'],ref['downbeats'],duration),groupedDownbeat=rhythm_scores(grid['downbeats'],ref['downbeats'],duration),
                           inserted=len(a['rhythmEvidence']['pulseRepair']['changes']),removed=a['rhythmEvidence']['removedQuietBeats'])
            else:
                c=analyze_chords(path,item['id']);save(work/(item['id']+'-chords.json'),c)
                ref=item['reference'];grid={**ref['grid'],'activityEndSec':None}
                inp=work/(item['id']+'-stable-input.json');save(inp,{'grid':grid,'result':c});stable=work/(item['id']+'-stable.json')
                subprocess.run(['node',str(Path(__file__).with_name('stable_chords.cjs')),str(inp),str(stable)],check=True)
                result=json.loads(stable.read_text('utf8'));row.update(raw=chord_scores(ref['chords'],c['events']),stableOracleGrid=chord_scores(ref['chords'],result['events']),referenceGridGiven=True)
                if ref.get('inferredChords'):row['rawAgainstInferred']=chord_scores(ref['inferredChords'],c['events'])
                a=analyze(path);save(work/(item['id']+'-analysis.json'),a)
                predicted={'beats':a['beats'],'downbeats':a['downbeats'],'beatsPerBar':a['beatsPerBarCandidate'],
                           'meterSegments':a.get('meterSegments'),'activityEndSec':a.get('activityEndSec')}
                inp=work/(item['id']+'-predicted-input.json');save(inp,{'grid':predicted,'result':c})
                out=work/(item['id']+'-predicted-stable.json')
                try:
                    subprocess.run(['node',str(Path(__file__).with_name('stable_chords.cjs')),str(inp),str(out)],check=True,capture_output=True)
                    row['stablePredictedGrid']=chord_scores(ref['chords'],json.loads(out.read_text('utf8'))['events'])
                except subprocess.CalledProcessError:
                    row['stablePredictedGrid']=None;row['predictedGridFailure']='Production harmony decoder rejected predicted grid; not replaced with reference'
            row['status']='complete'
        except Exception as e:row.update(status='failed',error=type(e).__name__+': '+str(e)[:300])
        row['elapsedSeconds']=round(time.monotonic()-started,3);report['rows'].append(row);save(destination,report)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    report['complete']=all(r['status']=='complete' for r in report['rows']);save(destination,report)

if __name__=='__main__':main()
