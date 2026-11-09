"""Measured activity, conservative pulse repair, and segmented meter candidates."""
import numpy as np
import scipy.signal
import soundfile as sf
from scipy.ndimage import maximum_filter1d

VERSION='rhythm-evidence-v1'

def features(signal,sr):
    if signal.ndim==1:signal=signal[:,None]
    hop=max(1,round(sr*.02));power=np.mean(signal.astype('float64')**2,axis=1)
    power=np.pad(power,(0,(-len(power))%hop));rms=np.sqrt(power.reshape(-1,hop).mean(axis=1))
    threshold=max(1e-5,float(np.percentile(rms,95))*.005)
    active=np.flatnonzero(rms>=threshold);duration=len(signal)/sr
    bounds=[float(active[0]*hop/sr),float(min(duration,(active[-1]+1)*hop/sr))] if len(active) else [0.,0.]
    mono=signal.mean(axis=1)
    # Low-frequency flux provides complementary pulse evidence, not ground truth.
    nfft=2**int(np.ceil(np.log2(sr*.046)))
    freqs,times,z=scipy.signal.stft(mono,sr,nperseg=nfft,noverlap=nfft-hop,boundary='zeros')
    magnitude=np.abs(z);positive=np.maximum(0,np.diff(magnitude,axis=1,prepend=magnitude[:,:1]))
    low=positive[(freqs>=35)&(freqs<=450)].sum(axis=0)
    broad=positive.sum(axis=0)
    return {'activityStartSec':bounds[0],'activityEndSec':bounds[1],'thresholdRms':threshold,
            'times':times,'low':low,'broad':broad,'rms':rms,'hopSec':hop/sr}

def gate(beats,downbeats,f):
    a,b=f['activityStartSec'],f['activityEndSec']
    bs=[float(t) for t in beats if a<=t<b]
    ds=[float(t) for t in downbeats if a<=t<b and any(abs(t-x)<.05 for x in bs)]
    return bs,ds


def pulse_repair(beats,f):
    """Repair sparse integer gaps only with onsets; retain every measured timestamp.

    A dominant pulse is NOT a quarter-note or meter assertion. Sustained tempo
    changes and the last eight beats are deliberately excluded from insertion.
    """
    bs=np.asarray(beats);g=np.diff(bs)
    if len(g)<16:return list(beats),[]
    period=float(np.median(g))
    multiples=np.clip(np.rint(g/period),1,4)
    period=float(np.median(g/multiples))
    match=np.abs(g/period-multiples)<.16
    if match.mean()<.85:return list(beats),[]
    peaks,_=scipy.signal.find_peaks(f['broad'],distance=max(1,round(period*.35/f['hopSec'])))
    times=f['times'][peaks];strength=f['broad'][peaks]
    repaired=[];changes=[]
    for i,t in enumerate(bs):
        repaired.append(float(t))
        if i>=len(g)-8 or not match[i]:continue
        count=int(multiples[i])
        if count not in (2,3):continue
        # An extended run of slower pulses may be a tempo change.
        neighbors=multiples[max(0,i-4):i+5]
        if np.count_nonzero(neighbors==1)<len(neighbors)*.5:continue
        hits=[]
        for k in range(1,count):
            predicted=t+g[i]*k/count
            candidates=np.flatnonzero(np.abs(times-predicted)<=min(.065,period*.18))
            nearby=strength[np.abs(times-predicted)<4*period]
            floor=float(np.median(nearby))*.45 if len(nearby) else float('inf')
            candidates=candidates[strength[candidates]>=max(1e-6,floor)]
            if not len(candidates):hits=[];break
            hit=int(candidates[np.argmin(np.abs(times[candidates]-predicted))]);hits.append(float(times[hit]))
        if hits:
            repaired.extend(hits)
            changes.extend({'kind':'insert','timeSec':round(h,5),'reason':'dominant_integer_gap_and_spectral_onset'} for h in hits)
    return repaired,changes


def meter_candidates(beats,downbeats,f,fallback=None):
    """Strong repeated accent intervals support local grouping, not denominators.

    Require >= four consistent measures and an acoustic accent contrast. Neural
    downbeats can support a grouping but never override contradictory audio.
    """
    if len(beats)<12:return []
    sal=np.interp(beats,f['times'],maximum_filter1d(f['low'],size=5))
    # Normalize slow dynamics without erasing every-second-beat accents.
    from scipy.ndimage import median_filter
    floor=median_filter(sal,size=17,mode='reflect')
    ratio=sal/np.maximum(floor,1e-7)
    accents=np.flatnonzero(ratio>=2.5)
    runs=[];i=0
    while i<len(accents)-1:
        m=int(accents[i+1]-accents[i]);j=i+1
        if m not in range(2,8):i+=1;continue
        while j<len(accents)-1 and accents[j+1]-accents[j]==m:j+=1
        if j-i>=4:
            runs.append({'startBeatIndex':int(accents[i]),'endBeatIndex':int(min(len(beats),accents[j]+m)),
                         'beatsPerBar':m,'anchorBeatIndex':int(accents[i]),'beatUnit':None,
                         'source':'repeated_acoustic_accent','status':'candidate'})
        i=max(i+1,j)
    if not runs and fallback is None:
        # Consecutive neural downbeat intervals, rather than a whole-song vote.
        # These remain grouping candidates: 2 vs 4 can be metrically ambiguous.
        indices=sorted(set(int(np.argmin(np.abs(np.asarray(beats)-d))) for d in downbeats))
        i=0
        while i<len(indices)-1:
            m=indices[i+1]-indices[i];j=i+1
            if m not in range(2,8):i+=1;continue
            while j<len(indices)-1 and indices[j+1]-indices[j]==m:j+=1
            if j-i>=4:
                runs.append({'startBeatIndex':indices[i],'endBeatIndex':min(len(beats),indices[j]+m),
                             'beatsPerBar':m,'anchorBeatIndex':indices[i],'beatUnit':None,
                             'source':'repeated_neural_downbeat','status':'candidate'})
            i=max(i+1,j)
    # Keep only non-overlapping evidence. Never extend a candidate through an
    # unsupported region or assume that a note-value denominator was detected.
    clean=[]
    for run in runs:
        if clean and run['startBeatIndex']<clean[-1]['endBeatIndex']:
            clean[-1]['endBeatIndex']=run['startBeatIndex']
        clean.append(run)
    if not clean:return []
    partition=[];cursor=0
    for run in clean:
        if run['startBeatIndex']>cursor:
            partition.append({'startBeatIndex':cursor,'endBeatIndex':run['startBeatIndex'],'beatsPerBar':None,'anchorBeatIndex':cursor,'beatUnit':None,'source':'unsupported','status':'candidate'})
        partition.append(run);cursor=run['endBeatIndex']
    if cursor<len(beats):partition.append({'startBeatIndex':cursor,'endBeatIndex':len(beats),'beatsPerBar':None,'anchorBeatIndex':cursor,'beatUnit':None,'source':'unsupported','status':'candidate'})
    return partition

def analyze(signal,sr,beats,downbeats,meter=None):
    f=features(signal,sr);bs,ds=gate(beats,downbeats,f)
    removed=len(beats)-len(bs)
    bs,changes=pulse_repair(bs,f)
    meter_segments=meter_candidates(bs,ds,f,meter)
    return {'version':VERSION,'beats':bs,'downbeats':ds,'beatsPerBar':meter,
            'activity':{k:f[k] for k in ['activityStartSec','activityEndSec','thresholdRms']},
            'removedQuietBeats':removed,'pulseRepair':{'changes':changes,'pulseLevel':'not_a_note_value'},'meterSegments':meter_segments}

def from_file(path,beats,downbeats,meter=None):
    y,sr=sf.read(path,dtype='float32',always_2d=True)
    return analyze(y,sr,beats,downbeats,meter)
