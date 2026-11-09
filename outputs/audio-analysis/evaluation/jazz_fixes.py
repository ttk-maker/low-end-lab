"""Post-audit regression: immutable neural outputs + newly measured audio evidence.

No real-track ground truth is invented. Run from workspace root with local
baseline work files present. Neither baseline reports nor live projects change.
"""
import argparse,json,sys,subprocess,hashlib,copy
from pathlib import Path
import numpy as np
import soundfile as sf
import soxr
import librosa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhythm_pipeline import from_file
from tonal_evidence import from_cqt
from chords import analyze_chords
from run import score
from rhythm_long import metrics


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def inspect(a,c,destination):
    inp=destination.with_suffix('.input.json');write(inp,{'analysis':a,'chords':c})
    subprocess.run(['node',str(Path(__file__).with_name('jazz_inspect.cjs')),str(inp),str(destination)],check=True)
    return json.loads(destination.read_text('utf8'))


def enrich(path,c):
    y,sr=sf.read(path,always_2d=True,dtype='float32');y=y.mean(axis=1)
    if sr!=22050:y=soxr.resample(y,sr,22050)
    mag=np.abs(librosa.cqt(y*c['method'].get('featureGain',1),sr=22050,n_bins=144,bins_per_octave=24,hop_length=2048))
    pitch=from_cqt(mag[:,:len(c['rawFrames'])]);out=copy.deepcopy(c)
    for f,p in zip(out['rawFrames'],pitch):f['pitchEnergy']=np.round(p,7).tolist()
    out['tonalEvidence']={'version':'harmonic-pitch-evidence-v1','cachedBTCUnchanged':True};return out


def revise(a,r):
    return {**a,'beats':r['beats'],'downbeats':r['downbeats'],'meterSegments':r['meterSegments'],
            'activityEndSec':r['activity']['activityEndSec'],'rhythmEvidence':r}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',default='C:/Users/jj183/Music/测试素材');ap.add_argument('--report-dir',default='outputs/audio-analysis/evaluation/jazz-fixes-2026-11-08');ap.add_argument('--part',choices=['tracks','controls','harmony','long','all'],default='all');args=ap.parse_args()
    out=Path(args.report_dir);out.mkdir(parents=True,exist_ok=True)
    if args.part in ('tracks','all'):
        rows=[]
        for folder in sorted(Path('work/jazz-audit/results').iterdir()):
            a=json.loads((folder/'analysis.json').read_text('utf8'));c=json.loads((folder/'chords.json').read_text('utf8'));audio=Path(args.source)/a['name']
            r=from_file(audio,a['beats'],a['downbeats'],a['beatsPerBarCandidate']);aa=revise(a,r);cc=enrich(audio,c)
            detail=inspect(aa,cc,out/'tracks'/(a['id']+'.json'));write(out/'tracks'/(a['id']+'-analysis.json'),aa);write(out/'tracks'/(a['id']+'-chords.json'),cc)
            row={'name':a['name'],'id':a['id'],'decodedDurationSec':a['durationSec'],'beatsBefore':len(a['beats']),'beatsAfter':len(r['beats']),
                 'removedQuietBeats':r['removedQuietBeats'],'insertedBeats':len(r['pulseRepair']['changes']),
                 **{k:detail[k] for k in ['bars','normalBars','uncertainBars','normalSeconds','anomalies','conflicts','stableAvailable','raw','stable','learning','tonalCorroboratedBars']}}
            rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        write(out/'tracks.json',rows)
    if args.part in ('controls','all'):
        rows=[];p=Path('work/jazz-audit/controls')
        for name,meters in [('swing_4',[4]*32),('meter_4_to_3',[4]*16+[3]*16)]:
            a=json.loads((p/(name+'-analysis.json')).read_text('utf8'));r=from_file(p/(name+'.wav'),a['beats'],a['downbeats'],a['beatsPerBarCandidate']);aa=revise(a,r)
            c=json.loads((p/(name+'-chords.json')).read_text('utf8'));d=inspect(aa,c,out/(name+'.json'))
            truth=2+np.arange(sum(meters))*.5;downs=2+np.r_[0,np.cumsum(meters)[:-1]]*.5
            rows.append({'name':name,'beat':metrics(r['beats'],truth),'downbeat':metrics(d['downbeats'],downs),'meterSegments':r['meterSegments'],'normalBars':d['normalBars'],
                         'beatsInExactSilence':[b for b in r['beats'] if b<2 or b>=truth[-1]+.2]})
        write(out/'controls-fixed.json',rows);print(json.dumps(rows,ensure_ascii=False),flush=True)
    if args.part in ('harmony','all'):
        p=Path('work/jazz-audit/harmony-control');c=analyze_chords(p/'constant-Cmaj7-swing-walking.wav','constant-jazz-control');write(out/'constant-chords.json',c)
        a={'durationSec':36,'beats':np.arange(2,34,.5).tolist(),'downbeats':np.arange(2,34,2).tolist(),'beatsPerBarCandidate':4}
        d=inspect(a,c,out/'constant-stable.json');ref=[(0,2,'N'),(2,34,'C:maj7'),(34,36,'N')]
        report={'knownScoreControl':True,'gridGivenByScore':True,'raw':score(ref,c['events']),'stable':score(ref,d['proposal']['events']),
                'correctWholeBars':sum(all(s['label']=='C:maj7' for s in b['spans']) for b in d['proposal']['bars']),
                'tonalCorroboratedBars':d['tonalCorroboratedBars']}
        write(out/'harmony-fixed.json',report);print(json.dumps(report),flush=True)
        rows=[]
        for item in json.loads(Path('outputs/audio-analysis/evaluation/fixtures/manifest.json').read_text('utf8')):
            c=analyze_chords(Path('outputs/audio-analysis/evaluation/fixtures')/item['audio'],item['id']);duration=c['durationSec']
            a={'durationSec':duration,'beats':np.arange(0,duration,.5).tolist(),'downbeats':np.arange(0,duration,2).tolist(),'beatsPerBarCandidate':4}
            d=inspect(a,c,out/'frozen'/(item['id']+'.json'));ref=[(e['startSec'],e['endSec'],e['label']) for e in item['reference']]
            without=copy.deepcopy(c)
            for frame in without['rawFrames']:frame.pop('pitchEnergy',None)
            old=inspect(a,without,out/'frozen'/(item['id']+'-without-tonal.json'))
            rows.append({'id':item['id'],'raw':score(ref,c['events']),'stableWithoutTonal':score(ref,old['proposal']['events']),'stableWithTonal':score(ref,d['proposal']['events'])})
            print('frozen',item['id'],rows[-1]['stableWithTonal']['weightedAccuracy'],flush=True)
        write(out/'frozen-harmony.json',rows)
    if args.part in ('long','all'):
        rows=[];p=Path('work/v06/long-final')
        for name in ['steady','variable','triple_swing']:
            ref=json.loads((p/(name+'-reference.json')).read_text('utf8'));r=from_file(p/(name+'-long.wav'),ref['rawBeats'],ref['rawDownbeats'],None)
            rows.append({'name':name,'beats':metrics(r['beats'],np.array(ref['beats'])),'inserted':len(r['pulseRepair']['changes']),'removed':r['removedQuietBeats'],'meterSegments':r['meterSegments']})
        write(out/'long-fixed.json',rows);print(json.dumps(rows,ensure_ascii=False),flush=True)
    write(out/'code-manifest.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('outputs/audio-analysis').glob('*') if p.is_file() and p.suffix in ('.py','.js')})

if __name__=='__main__':main()
