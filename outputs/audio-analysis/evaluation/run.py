"""Reproducible synthetic benchmark, independent generated labels, never model labels.
Run: python evaluation/run.py --output <directory> [--split dev|test|all]
No training; test split is evaluated only after inference parameters are fixed.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chords import analyze_chords, validate_annotation
from chords_baseline import analyze_chords as baseline

INTERVALS={'maj':[0,4,7],'min':[0,3,7],'7':[0,4,7,10],'min7':[0,3,7,10],
           'maj7':[0,4,7,11],'sus4':[0,5,7]}
ROOTS=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def fixtures(split):
    shift=0 if split=='dev' else 5
    # Different roots and synthesis seeds; same stress categories. No original song.
    def chord(pc,q):return ROOTS[(pc+shift)%12]+':'+q
    return [
        ('triads',[(0,4,chord(0,'maj')),(4,8,chord(2,'min'))],1),
        ('sevenths',[(0,4,chord(9,'min7')),(4,8,chord(7,'7'))],1),
        ('window_boundary',[(0,9.8,chord(5,'maj')),(9.8,14,chord(7,'maj'))],1),
        ('fast_changes',[(i*.5,(i+1)*.5,chord([0,2,5,7][i%4],'min' if i%4==1 else 'maj')) for i in range(16)],1),
        ('quiet',[(0,4,chord(0,'maj')),(4,8,chord(9,'min'))],.008),
        ('tail',[(0,4,chord(0,'maj')),(4,8,'N')],1),
        ('silence',[(0,8,'N')],1),
        ('major7_sus',[(0,4,chord(0,'maj7')),(4,8,chord(7,'sus4'))],1),
    ]

def synth(events,gain,seed):
    sr=22050;y=np.zeros(int(events[-1][1]*sr));rng=np.random.default_rng(seed)
    for a,b,label in events:
        if label=='N':continue
        root,quality=label.split(':');pc=ROOTS.index(root);length=int(b*sr)-int(a*sr)
        t=np.arange(length)/sr;chunk=np.zeros(length)
        for interval in INTERVALS[quality]:
            f=440*2**((48+pc+interval-69)/12)
            for harmonic in [1,2,3,4]:
                chunk+=np.sin(2*np.pi*f*harmonic*t+rng.uniform(-.1,.1))/(harmonic**1.4)
        envelope=np.minimum(1,t/.008)*np.minimum(1,(b-a-t)/.015)
        y[int(a*sr):int(b*sr)]=chunk*envelope*.07*gain
    return y.astype('float32'),sr

def score(reference,predicted):
    # Exact interval intersection, not sampled frames. N is scored separately.
    correct=covered=duration=music=music_correct=silent=silent_correct=0
    for a,b,label in reference:
        duration+=b-a
        if label=='N':silent+=b-a
        else:music+=b-a
        for e in predicted:
            overlap=max(0,min(b,e['endSec'])-max(a,e['startSec']))
            if e['label']!='X':covered+=overlap
            if e['label']==label:
                correct+=overlap
                if label=='N':silent_correct+=overlap
                else:music_correct+=overlap
    truth=[b for _,b,_ in reference[:-1]]
    estimates=[e['startSec'] for i,e in enumerate(predicted) if i and e['label']!=predicted[i-1]['label']]
    remaining=estimates.copy();matched=0
    for t in truth:
        if remaining:
            nearest=min(remaining,key=lambda x:abs(x-t))
            if abs(nearest-t)<=.2:matched+=1;remaining.remove(nearest)
    precision=matched/len(estimates) if estimates else None
    recall=matched/len(truth) if truth else None
    return {'durationSec':duration,'correctSeconds':correct,'weightedAccuracy':correct/duration,
            'coverage':covered/duration,'selectiveAccuracy':correct/covered if covered else None,
            'musicSeconds':music,'musicCorrectSeconds':music_correct,'silenceSeconds':silent,
            'silenceCorrectSeconds':silent_correct,'segments':len(predicted),
            'boundaryToleranceSec':.2,'boundaryPrecision':precision,'boundaryRecall':recall}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--split',choices=['dev','test','all'],default='all')
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    manifest=[];rows=[]
    for split in (['dev','test'] if args.split=='all' else [args.split]):
        for number,(name,ref,gain) in enumerate(fixtures(split)):
            seed=(100 if split=='dev' else 700)+number;audio,sr=synth(ref,gain,seed)
            path=out/(split+'-'+name+'.wav');sf.write(path,audio,sr,subtype='FLOAT')
            item={'id':path.stem,'split':split,'audio':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'reference':[{'startSec':a,'endSec':b,'label':label}for a,b,label in ref],
                  'annotationOrigin':'known synthesis score, independent of model','seed':seed}
            manifest.append(item);row={'id':path.stem,'split':split}
            for key,fn in [('v1',baseline),('v2',analyze_chords)]:
                result=json.loads(json.dumps(fn(path,path.stem)));validate_annotation({'events':result['events']},result['durationSec'])
                row[key]=score(ref,result['events']);row[key]['analysisSeconds']=result['analysisSeconds']
                (out/(path.stem+'-'+key+'.json')).write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
            rows.append(row);print(json.dumps(row),flush=True)
    summary={}
    for split in sorted({x['split'] for x in rows}):
        summary[split]={}
        for version in ['v1','v2']:
            scores=[x[version] for x in rows if x['split']==split]
            summary[split][version]={'weightedAccuracy':sum(x['correctSeconds'] for x in scores)/sum(x['durationSec']for x in scores),
                'musicAccuracy':sum(x['musicCorrectSeconds']for x in scores)/sum(x['musicSeconds']for x in scores),
                'silenceAccuracy':sum(x['silenceCorrectSeconds']for x in scores)/sum(x['silenceSeconds']for x in scores),
                'segments':sum(x['segments']for x in scores)}
    report={'schemaVersion':1,'dataset':'generated-chord-suite-v1','kind':'synthetic regression, not real-song benchmark',
            'trainingPerformed':False,'fixedCandidate':'btc-170-v2','rows':rows,'summary':summary,
            'limitations':['Synthetic timbres do not establish real music accuracy.','Real-song teacher annotations are still needed.']}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
