"""Evaluation-only imports. Raw labels retained; never writes production projects.

Manifests distinguish imported labels from independent human re-review. No
reference is manufactured by running the model under evaluation.
"""
import argparse,collections,hashlib,json,os,re
from pathlib import Path
import numpy as np
import soundfile as sf
from dataset_io import DATA,REPORT,save,digest,download,extract_tar,extract_zip

GTZAN_REV='d2146561ecc7df707d9e6b8318885fe6a39668a2'
ANNOTATION_REV='890407d158078527ab396b49fea3c8a83e5734ee'
POP_REV='6d2f91ae545f7ee78fdef903fe5d40992c1dc420'

def relative(path):return os.path.relpath(Path(path).resolve(),REPORT.resolve()).replace('\\','/')

def split_for(group,denominator=5):
    return 'diagnostic' if int(hashlib.sha256(group.encode()).hexdigest()[:8],16)%denominator==0 else 'frozen_test'

def validate_beats(beats,positions,duration):
    issues=[]
    if len(beats)<2:issues.append('insufficient_beats')
    if len(beats)!=len(positions):issues.append('position_length_mismatch')
    if any(not np.isfinite(t) or not 0<=t<duration for t in beats):issues.append('beat_out_of_audio_bounds')
    gaps=np.diff(beats)
    if np.any(gaps<=0):issues.append('non_monotonic_beats')
    if np.any((gaps>0)&(gaps<.08)):issues.append('implausibly_close_reference_beats')
    if any(p<0 or p>16 for p in positions):issues.append('invalid_beat_position')
    return issues

def audio_fields(path):
    info=sf.info(path)
    return {'audio':relative(path),'audioSha256':digest(path),'durationSec':info.frames/info.samplerate,
            'sampleRate':info.samplerate,'channels':info.channels,'audioKind':'real_recording'}

def finish(name,items,upstream,notes):
    counts=collections.Counter(i['split'] for i in items)
    summary={'dataset':name,'items':len(items),'splitCounts':dict(counts),
             'eligible':{key:sum(bool(i.get('eligible',{}).get(key)) for i in items) for key in ['beat','downbeat','chord']},
             'issueCounts':dict(collections.Counter(x for i in items for x in i.get('qualityIssues',[]))),
             'durationHours':sum(i.get('durationSec',0) for i in items)/3600,'notes':notes}
    save(REPORT/(name+'-manifest.json'),{'schemaVersion':2,'dataset':name,'upstream':upstream,
         'splitPolicy':'deterministic groups; frozen_test is not used for tuning or initial smoke tests',
         'independentlyHumanReviewedByProject':False,'summary':summary,'items':items})
    save(REPORT/(name+'-import.json'),summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary

def gtzan():
    archive=DATA/'downloads/gtzan-genres.tar.gz'
    source={'requestedAudioRepository':'marsyas/gtzan','requestedRevision':GTZAN_REV,'annotationsRevision':ANNOTATION_REV}
    if archive.exists():
        if digest(archive)!='b28cc067ff6199bd826f5d1a6931458586d64acae7f44b2e882b7a97af057531':raise ValueError('GTZAN archive SHA256 mismatch')
        extract_tar(archive,DATA/'gtzan/audio',lambda n:n.lower().endswith('.wav'))
        paths=sorted((DATA/'gtzan/audio').rglob('*.wav'));source['actualDownload']='huggingface'
    else:
        archive=DATA/'downloads/gtzan-kaggle-original-au.zip'
        if not archive.exists():raise FileNotFoundError('Download and verify GTZAN first')
        extract_zip(archive,DATA/'gtzan/audio',lambda n:n.lower().endswith('.au'))
        paths=sorted((DATA/'gtzan/audio').rglob('*.au'))
        source.update(actualDownload='https://www.kaggle.com/datasets/carlthome/gtzan-genre-collection',reason='HF/CDN connections failed; same dataset original AU release',archiveSha256=digest(archive),hfByteIdentityClaimed=False)
    extract_zip(DATA/'downloads/beat-this-annotations-v1.1.zip',DATA/'gtzan/reference-source',lambda n:'/gtzan/' in n or n.endswith(('LICENSE','README.md')))
    labels={p.stem:p for p in (DATA/'gtzan/reference-source').rglob('*.beats')};items=[]
    for original_path in paths:
        path=original_path
        if path.suffix=='.au':
            # Lossless container conversion only: preserve every PCM sample.
            path=DATA/'gtzan/normalized'/original_path.with_suffix('.flac').name
            if not path.exists():
                y,sr=sf.read(original_path,dtype='int16',always_2d=True);path.parent.mkdir(parents=True,exist_ok=True);sf.write(path,y,sr,subtype='PCM_16')
                decoded,sr2=sf.read(path,dtype='int16',always_2d=True)
                if sr!=sr2 or not np.array_equal(y,decoded):raise ValueError('Container conversion changed PCM')
        uid='gtzan_'+path.stem.replace('.','_');item={'id':uid,'genre':path.stem.split('.')[0],'reference':{},'qualityIssues':[],
               'eligible':{'beat':False,'downbeat':False,'chord':False},'beatTrainingOverlap':'excluded_by_small0_official_training_description'}
        try:item.update(audio_fields(path))
        except Exception as e:item.update(audio=relative(path),audioSha256=digest(path),qualityIssues=['audio_decode_error'],decodeError=type(e).__name__)
        item['sourceAudioSha256']=digest(original_path);item['sourceAudio']=relative(original_path)
        group=item['audioSha256'];item.update(group=group,split=split_for(group))
        if uid not in labels:item['qualityIssues'].append('missing_reference')
        elif 'durationSec' in item:
            lab=labels[uid];lines=[line.split() for line in lab.read_text().splitlines() if line.strip()]
            beats=[float(v[0]) for v in lines];positions=[int(v[1]) if len(v)>1 else 0 for v in lines]
            item['reference']={'beats':beats,'beatPositions':positions,'downbeats':[t for t,p in zip(beats,positions) if p==1]}
            item['referenceSource']={'path':relative(lab),'sha256':digest(lab),'type':'published_beat_annotations','revision':ANNOTATION_REV}
            item['qualityIssues']+=validate_beats(beats,positions,item['durationSec'])
            item['eligible']['beat']=not item['qualityIssues'];item['eligible']['downbeat']=not item['qualityIssues'] and bool(item['reference']['downbeats'])
        items.append(item)
    if len(items)!=1000:raise ValueError(f'Expected 1000 GTZAN recordings, found {len(items)}')
    return finish('gtzan',items,source,
                  ['30-second excerpts do not validate long-song drift','Reference anomalies are excluded with reasons; source annotations are never rewritten','HF genre labels are not used as beat truth','Exact file hashes group duplicates; cross-recording/song-level duplicates not fully audited'])

def guitarset():
    archives=[('guitarset-mic.zip','275966d6610ac34999b58426beb119c3'),('guitarset-annotation.zip','b39b78e63d3446f2e54ddb7a54df9b10')]
    for name,checksum in archives:
        if digest(DATA/'downloads'/name,'md5')!=checksum:raise ValueError('Official GuitarSet MD5 mismatch: '+name)
    extract_zip(DATA/'downloads/guitarset-mic.zip',DATA/'guitarset/audio',lambda n:n.endswith('.wav'))
    extract_zip(DATA/'downloads/guitarset-annotation.zip',DATA/'guitarset/annotations',lambda n:n.endswith('.jams'))
    audio={p.stem.removesuffix('_mic'):p for p in (DATA/'guitarset/audio').rglob('*.wav')};items=[]
    for label in sorted((DATA/'guitarset/annotations').rglob('*.jams')):
        key=label.stem;d=json.loads(label.read_text('utf8'));path=audio[key];parts=key.split('_')
        group=parts[1].split('-')[0]  # Keep tempo/key variants of each template together too.
        # These templates already entered diagnostic smoke tests. All their variants
        # stay diagnostic permanently; never promote observed examples to holdout.
        split='diagnostic' if group in {'BN3','Funk1','SS2'} else 'frozen_test'
        item={'id':'guitarset_'+key,**audio_fields(path),'group':group,'split':split,
              'style':parts[1][:2],'performer':parts[0],'performanceStyle':parts[-1],'qualityIssues':[],
              'beatTrainingOverlap':'GuitarSet is an upstream Beat This training source; diagnostic only, not independent generalization',
              'referenceSource':{'path':relative(label),'sha256':digest(label),'type':'published_JAMS_leadsheet_and_inferred','record':'3371780'}}
        anns=d['annotations'];beat=next(a for a in anns if a['namespace']=='beat_position')['data']
        rows=[x for x in beat if x['time']<item['durationSec']-1e-6]
        beats=[float(x['time']) for x in rows];pos=[int(x['value']['position']) for x in rows]
        segments=[]
        for i,x in enumerate(rows):
            m=int(x['value']['num_beats'])
            if not segments or segments[-1]['beatsPerBar']!=m:
                if segments:segments[-1]['endBeatIndex']=i
                segments.append({'startBeatIndex':i,'endBeatIndex':len(rows),'beatsPerBar':m,'anchorBeatIndex':i-(pos[i]-1),'source':'reference_JAMS'})
        downs=[t for t,p in zip(beats,pos) if p==1]
        chords=[a for a in anns if a['namespace']=='chord']
        inferred=[a for a in chords if a.get('annotation_metadata',{}).get('annotation_rules')]
        lead=[a for a in chords if a not in inferred]
        if len(lead)!=1 or len(inferred)!=1:raise ValueError('Ambiguous GuitarSet chord annotation roles')
        def events(annotation):
            return [{'startSec':float(x['time']),'endSec':min(item['durationSec'],float(x['time']+x['duration'])),'label':x['value']}
                    for x in annotation['data'] if x['duration']>0 and x['time']<item['durationSec']]
        item['reference']={'beats':beats,'beatPositions':pos,'downbeats':downs,'chords':events(lead[0]),'inferredChords':events(inferred[0]),
            'grid':{'beats':beats,'downbeats':downs,'beatsPerBar':segments[0]['beatsPerBar'],'barAnchorIndex':segments[0]['anchorBeatIndex'],'meterSegments':segments}}
        item['referenceEndBeatExcluded']=len(beat)-len(rows)
        item['qualityIssues']=validate_beats(beats,pos,item['durationSec'])
        item['eligible']={'beat':not item['qualityIssues'],'downbeat':not item['qualityIssues'] and bool(downs),'chord':bool(item['reference']['chords'])}
        items.append(item)
    if len(items)!=360 or len(audio)!=360:raise ValueError('Expected 360 GuitarSet performances')
    return finish('guitarset',items,{'officialSource':'https://zenodo.org/records/3371780','license':'CC BY 4.0',
        'archives':{name:{'md5':checksum,'sha256':digest(DATA/'downloads'/name)} for name,checksum in archives}},
        ['Microphone recordings only; no hexaphonic redundant audio download','Lead-sheet and performed/inferred labels remain separate',
         'Inferred chords use leadsheet boundaries/root and are not fully independent manual truth','Same template across tempo/key/player/comp/solo shares split',
         'BN3, Funk1 and SS2 remain diagnostic because their variants were used in initial smoke tests; no observed template is promoted to frozen_test',
         'Beat This training overlap prevents claiming independent beat generalization','Chord smoke tests select comp; solo labels are harmonic context, not necessarily sounding chords',
         'Beats exactly at or beyond audio end are omitted from scored events; original JAMS preserved'])

def pop909():
    if digest(DATA/'downloads/pop909-processed.zip')!='d18882cb5f4a633fe607bcb69c76c47021032d74b9c3b143aa3d34b85269b4a7':raise ValueError('Pinned POP909 LFS SHA256 mismatch')
    extract_zip(DATA/'downloads/pop909-processed.zip',DATA/'pop909/source')
    from pop909_adapter import import_pop
    return import_pop(relative,split_for,finish,POP_REV)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('dataset',choices=['gtzan','guitarset','pop909']);a=p.parse_args()
    {'gtzan':gtzan,'guitarset':guitarset,'pop909':pop909}[a.dataset]()
