"""Offline FluidSynth rendering with reference track removed and bounded disk use."""
import subprocess
from pathlib import Path
import mido,numpy as np,soundfile as sf
from dataset_io import DATA,save,digest

def strip_reference(source,destination):
    midi=mido.MidiFile(source);removed=[];tracks=[]
    for track in midi.tracks:
        if track.name.upper()=='CHORDS':removed.append(track.name);continue
        output=mido.MidiTrack();pending=0
        for message in track:
            pending+=message.time
            if message.type in ['marker','lyrics','text']:continue
            output.append(message.copy(time=pending));pending=0
        if pending:output.append(mido.MetaMessage('end_of_track',time=pending))
        tracks.append(output)
    if removed!=['CHORDS']:raise ValueError('Reference track removal not confirmed')
    midi.tracks=tracks;midi.save(destination)
    return removed

def render_item(item,report):
    source=(report/item['midi']).resolve();out=(report/item['audio']).resolve();receipt=out.with_suffix('.render.json')
    exe=next((DATA/'renderer/fluidsynth').rglob('fluidsynth.exe'));font=next((DATA/'renderer/soundfont').rglob('*.sf2'))
    identity={'midiSha256':digest(source),'soundfontSha256':digest(font),'rendererSha256':digest(exe),'sampleRate':22050,'channels':1,'removedTrack':'CHORDS','effects':False}
    if identity['midiSha256']!=item['midiSha256']:raise ValueError('Source MIDI changed')
    if out.exists() and receipt.exists():
        import json
        old=json.loads(receipt.read_text('utf8'))
        if all(old.get(k)==v for k,v in identity.items()) and old['audioSha256']==digest(out):return out
        raise ValueError('Existing rendering identity differs; preserve it and inspect before replacing')
    out.parent.mkdir(parents=True,exist_ok=True);clean=out.with_suffix('.score.mid');wav=out.with_suffix('.wav')
    strip_reference(source,clean)
    subprocess.run([str(exe),'-ni','-q','-R','0','-C','0','-r','22050','-g','0.5','-T','wav','-F',str(wav),str(font),str(clean)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    y,sr=sf.read(wav,always_2d=True);y=y.mean(axis=1);count=round(item['durationSec']*sr)
    y=np.pad(y,(0,max(0,count-len(y))))[:count]
    sf.write(out,y,sr,subtype='PCM_16');save(receipt,{**identity,'audioSha256':digest(out),'frames':count,'peak':float(np.max(np.abs(y))),'scoreMidiSha256':digest(clean)})
    wav.unlink()  # Only the renderer-owned intermediate, after verified FLAC creation.
    return out
