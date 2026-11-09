"""Conservative, reviewable rhythm repair. Never overwrites neural timestamps."""
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import find_peaks

VERSION='rhythm-review-v1'

def onsets(path):
    audio,sr=sf.read(str(path),dtype='float32',always_2d=True)
    # Channel power avoids cancellation when stereo channels have opposite phase.
    power=np.mean(audio.astype('float64')**2,axis=1)
    hop=max(1,round(sr*.01));power=np.pad(power,(0,(-len(power))%hop))
    rms=np.sqrt(power.reshape(-1,hop).mean(axis=1))
    flux=np.maximum(0,np.diff(rms,prepend=0))
    if not len(flux) or flux.max()<1e-6:return np.array([]),np.array([])
    peaks,_=find_peaks(np.r_[0,flux,0],distance=8,prominence=max(1e-6,float(np.percentile(flux,90))*.35))
    peaks=peaks-1;peaks=peaks[(peaks>=0)&(peaks<len(flux))]
    return peaks*hop/sr,flux[peaks]

def propose(beats,downbeats,meter,duration,onset_times,onset_strength,mode='repair',anchor_index=None):
    if mode not in ('repair','steady'):raise ValueError('不支持的节奏校正方式')
    bs=np.asarray(beats,dtype=float)
    if len(bs)<8:raise ValueError('至少需要 8 个检测拍点，才能检查连续节奏。')
    if np.any(np.diff(bs)<=0) or bs[0]<0 or bs[-1]>=duration:raise ValueError('拍点时间无效')
    times=np.asarray(onset_times);strength=np.asarray(onset_strength)
    anchor_time=bs[anchor_index] if anchor_index is not None else (downbeats[0] if len(downbeats) else bs[0])
    changes=[];repaired=[]
    gaps=np.diff(bs)
    for i,t in enumerate(bs):
        repaired.append(float(t))
        if i==len(bs)-1:continue
        local=np.r_[gaps[max(0,i-8):i],gaps[i+1:i+9]]
        period=float(np.median(local)) if len(local) else float(np.median(gaps))
        ratio=gaps[i]/period;count=int(round(ratio))
        if count not in (2,3) or abs(ratio-count)>.12:continue
        hits=[]
        for n in range(1,count):
            predicted=t+gaps[i]*n/count
            idx=np.flatnonzero(np.abs(times-predicted)<=min(.075,period*.15))
            neighborhood=strength[(times>=t-4*period)&(times<=bs[i+1]+4*period)]
            floor=max(1e-6,float(np.percentile(neighborhood,50))*.35) if len(neighborhood) else 1e-6
            idx=idx[strength[idx]>=floor]
            if not len(idx):hits=[];break
            hit=int(idx[np.argmin(np.abs(times[idx]-predicted))]);hits.append(float(times[hit]))
        if hits:
            repaired.extend(hits)
            changes.extend({'kind':'insert','timeSec':round(x,5),'reason':'local_interval_and_audio_onset'} for x in hits)
    # Remove a likely double detection only when the middle event has much weaker onset evidence.
    def salience(t):
        candidates=strength[np.abs(times-t)<=.06]
        return float(candidates.max()) if len(candidates) else 0.
    cleaned=[];removed=[]
    for i,t in enumerate(repaired):
        if 0<i<len(repaired)-1:
            local=np.diff(repaired[max(0,i-8):min(len(repaired),i+9)])
            period=float(np.median(local));a=t-repaired[i-1];b=repaired[i+1]-t
            if min(a,b)<period*.55 and abs((a+b)/period-1)<.12 and salience(t)<.3*min(salience(repaired[i-1]),salience(repaired[i+1])):
                removed.append(t);continue
        cleaned.append(t)
    changes.extend({'kind':'remove','timeSec':round(t,5),'reason':'weak_extra_onset'} for t in removed)
    fitted=None
    if mode=='steady':
        y=np.asarray(cleaned);x=np.arange(len(y));keep=np.ones(len(y),dtype=bool)
        for _ in range(4):
            slope,intercept=np.polyfit(x[keep],y[keep],1)
            residual=y-(intercept+slope*x)
            mad=float(np.median(np.abs(residual-np.median(residual))))
            keep=np.abs(residual)<=max(.035,3*mad)
            if keep.sum()<8:raise ValueError('固定速度证据不足；请保留逐拍时间。')
        residual=y-(intercept+slope*x)
        p95=float(np.percentile(np.abs(residual),95))
        if not .2<=slope<=3 or p95>min(.07,slope*.15):
            raise ValueError('全曲不符合稳定速度网格，可能有变速、漏拍或多拍；请使用逐拍校正，不强行拉直。')
        fitted={'bpm':float(60/slope),'p95ResidualMs':round(p95*1000,2),'lastResidualMs':round(float(residual[-1])*1000,2)}
        cleaned=[float(intercept+slope*i) for i in range(len(y))]
        # Keep indices stable at the file boundary, rather than dropping beat zero.
        if cleaned[0]<0:cleaned[0]=0.
        cleaned=[x for x in cleaned if x<duration]
    nearest=min(range(len(cleaned)),key=lambda i:abs(cleaned[i]-anchor_time))
    if anchor_index is None and meter:
        votes=[0]*meter
        for d in downbeats:
            k=min(range(len(cleaned)),key=lambda i:abs(cleaned[i]-d))
            if abs(cleaned[k]-d)<.1:votes[k%meter]+=1
        nearest=int(np.argmax(votes))
    downs=[t for i,t in enumerate(cleaned) if meter and (i-nearest)%meter==0]
    intervals=np.diff(cleaned);unresolved=[]
    for i,gap in enumerate(intervals):
        neighbors=np.r_[intervals[max(0,i-8):i],intervals[i+1:i+9]]
        local=float(np.median(neighbors)) if len(neighbors) else float(gap)
        if gap>local*1.5 or gap<local*.55:unresolved.append({'startSec':round(cleaned[i],5),'endSec':round(cleaned[i+1],5)})
    return {'version':VERSION,'mode':mode,'beats':[round(t,5) for t in cleaned],
            'downbeats':[round(t,5) for t in downs],'barAnchorIndex':nearest,'changes':changes,
            'unresolved':unresolved,'fit':fitted,'extendsBeyondDetectedRange':False,
            'warning':'候选修复仍需回听。每小节拍数与首拍需人工确认；自由速度、变拍号及复合拍子不自动推断。'}

def review(path,annotation,duration,mode):
    if mode=='evidence':
        from rhythm_pipeline import from_file
        r=from_file(path,annotation['beats'],annotation['downbeats'],annotation.get('beatsPerBar'))
        r['changes']=r['pulseRepair']['changes']
        r['unresolved']=[];r['fit']=None;r['activityEndSec']=r['activity']['activityEndSec']
        r['barAnchorIndex']=None
        return r
    if annotation.get('meterSegments'):
        raise ValueError('当前为分段拍数，请使用“声学复核”；全曲拟合会丢失分段，不自动执行。')
    times,strength=onsets(Path(path))
    return propose(annotation['beats'],annotation['downbeats'],annotation.get('beatsPerBar'),duration,
                   times,strength,mode,annotation.get('barAnchorIndex'))
