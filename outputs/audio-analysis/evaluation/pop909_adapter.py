"""Tempo-aware symbolic references. No CHORDS audio enters the renderer."""
import bisect,csv,collections,json,math,re
from pathlib import Path
import mido
import mir_eval
from dataset_io import DATA,REPORT,save,digest

def absolute(track):
    tick=0
    for msg in track:
        tick+=msg.time
        yield tick,msg

def tempo_map(midi):
    tempos={0:500000}
    for track in midi.tracks:
        for tick,msg in absolute(track):
            if msg.type=='set_tempo':tempos[tick]=msg.tempo
    ticks=sorted(tempos);seconds=[0.]
    for a,b in zip(ticks,ticks[1:]):seconds.append(seconds[-1]+mido.tick2second(b-a,midi.ticks_per_beat,tempos[a]))
    def convert(tick):
        i=bisect.bisect_right(ticks,tick)-1
        return seconds[i]+mido.tick2second(tick-ticks[i],midi.ticks_per_beat,tempos[ticks[i]])
    return convert

QUALITIES={'M':'maj','m':'min','M7':'maj7','m7':'min7','7':'7','D7':'7','dim':'dim','dim7':'dim7','hdim7':'hdim7','aug':'aug','sus2':'sus2','sus4':'sus4','mM7':'minmaj7','6':'maj6','m6':'min6','o':'dim','o7':'dim7','/o7':'hdim7','+':'aug','+7':'aug(b7)'}

def normalize_marker(text):
    if text in ['N','X']:return text
    root,quality=text.split(':',1);bass=None
    match=re.search(r'/([A-G][#b]*)$',quality)
    if match:bass=match.group(1);quality=quality[:match.start()]
    if quality not in QUALITIES:raise ValueError('Unsupported source quality: '+quality)
    label=root+':'+QUALITIES[quality]
    if bass:
        interval=(mir_eval.chord.pitch_class_to_semitone(bass)-mir_eval.chord.pitch_class_to_semitone(root))%12
        label+='/'+['1','b2','2','b3','3','4','b5','5','b6','6','b7','7'][interval]
    mir_eval.chord.encode(label)
    return label

def references(midi):
    sec=tempo_map(midi);end=max(t for track in midi.tracks for t,_ in absolute(track));ppq=midi.ticks_per_beat
    meters={};markers=[]
    for track in midi.tracks:
        for t,msg in absolute(track):
            if msg.type=='time_signature':meters[t]=(msg.numerator,msg.denominator)
            if msg.type=='marker':markers.append((t,msg.text))
    if not meters or 0 not in meters:raise ValueError('Missing initial meter')
    beats=[];positions=[];segments=[];meter_ticks=sorted(meters)
    for k,start in enumerate(meter_ticks):
        stop=meter_ticks[k+1] if k+1<len(meter_ticks) else end;n,d=meters[start]
        # Compound 6/8 uses two dotted-quarter pulses. 3/8 retains three eighth-note pulses.
        pulse=ppq*4/d*(3 if n>=6 and n%3==0 and d==8 else 1)
        count=n//3 if n>=6 and n%3==0 and d==8 else n
        lo=len(beats);j=0
        while start+j*pulse<stop-1e-6:
            beats.append(sec(start+j*pulse));positions.append(j%count+1);j+=1
        segments.append({'startBeatIndex':lo,'endBeatIndex':len(beats),'beatsPerBar':count,'anchorBeatIndex':lo,'source':'MIDI_meter','notatedMeter':f'{n}/{d}'})
    down=[t for t,p in zip(beats,positions) if p==1]
    chord_tracks=[t for t in midi.tracks if t.name.upper()=='CHORDS']
    if len(chord_tracks)!=1:raise ValueError('Expected exactly one CHORDS reference track')
    # Only score intervals where the reference track actually sustains notes.
    changes=collections.defaultdict(list)
    for t,msg in absolute(chord_tracks[0]):
        if msg.type in ['note_on','note_off']:changes[t].append(msg)
    active=collections.Counter();spans=[];last=0
    for t,messages in sorted(changes.items()):
        if t>last and any(active.values()):spans.append((last,t))
        for msg in messages:
            if msg.type=='note_on' and msg.velocity:active[msg.note]+=1
            else:active[msg.note]=max(0,active[msg.note]-1)
        last=t
    markers=sorted(set(markers));chords=[]
    for i,(start,label) in enumerate(markers):
        stop=markers[i+1][0] if i+1<len(markers) else end
        normalized=normalize_marker(label)
        for a,b in spans:
            lo=max(a,start);hi=min(b,stop)
            if hi>lo:
                e={'startSec':sec(lo),'endSec':sec(hi),'label':normalized,'sourceLabel':label}
                if chords and chords[-1]['label']==normalized and abs(chords[-1]['endSec']-e['startSec'])<1e-6:chords[-1]['endSec']=e['endSec']
                else:chords.append(e)
    return {'beats':beats,'beatPositions':positions,'downbeats':down,'chords':chords,
            'grid':{'beats':beats,'downbeats':down,'beatsPerBar':segments[0]['beatsPerBar'],'barAnchorIndex':0,'meterSegments':segments}},sec(end)

def import_pop(relative,split_for,finish,revision):
    root=DATA/'pop909/source';metafile=next(root.rglob('metadata.csv'));metadata=list(csv.DictReader(metafile.open(encoding='utf-8-sig')))
    paths={p.stem:p for p in root.rglob('*.mid')};items=[]
    for row in metadata:
        if row['status']!='released':continue
        uid=row['piece_id'].zfill(3);path=paths[uid];midi=mido.MidiFile(path);ref,duration=references(midi)
        group=row['artist']+'|'+row['name'];issues=['upstream_flag'] if row['flags'] else []
        items.append({'id':'pop909_'+uid,'title':row['name'],'artist':row['artist'],'style':row['initial_meter'],'group':group,'split':split_for(group),
            'midi':relative(path),'midiSha256':digest(path),'durationSec':duration,'sampleRate':22050,'channels':1,'audioKind':'soundfont_synthesized',
            'audio':relative(DATA/'pop909/rendered'/f'{uid}.flac'),'audioSha256':None,'renderStatus':'on_demand',
            'qualityIssues':issues,'upstreamFlags':row['flags'],'eligible':{key:not issues for key in ['beat','downbeat','chord']},
            'reference':ref,'referenceSource':{'path':relative(path),'sha256':digest(path),'type':'corrected_MIDI_meter_and_CHORDS_markers','revision':revision},
            'referenceCoverageNote':'Only labeled sustained CHORDS intervals are scored; gaps are unannotated, not invented N',
            'trainingOverlap':'Not listed in published training corpus; composition-level overlap not audited'})
    if len(items)!=906:raise ValueError(f'Expected 906 released MIDI, found {len(items)}')
    return finish('pop909',items,{'repository':'Itsuki-music/POP909-CL-Dataset','revision':revision,'metadataRows':len(metadata),
        'archiveSha256':digest(DATA/'downloads/pop909-processed.zip'),'actualDownload':'https://raw.githubusercontent.com/AndyWeasley2004/POP909-CL-Dataset/0e06063995ef237585c2ad48336cfae1b960beae/POP909_processed.zip',
        'byteIdenticalToPinnedHuggingFaceLfs':True,'missingIds':[r['piece_id'] for r in metadata if r['status']!='released']},
        ['Synthetic score performance, not original commercial audio','CHORDS track removed before synthesis; melody/bridge/piano retained',
         'Reference uses embedded markers and active CHORDS intervals; not every CSV N interval is imported',
         'Tempo, PPQ, meter changes honored; 6/8 evaluated at dotted-quarter pulse','10 upstream flagged pieces excluded by default',
         'Audio generated on demand to conserve disk; symbolic import is complete','Soundfont domain scores do not establish real mixed-audio accuracy'])
