"""BTC large-vocabulary inference, separate from the existing beat project."""
from __future__ import annotations
import hashlib
import json
import math
import threading
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import soxr
from scipy.ndimage import uniform_filter1d

ROOT = Path(__file__).resolve().parent
VERSION = 'btc-170-v3'
ROOTS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
QUALITIES = ['min','maj','dim','aug','min6','maj6','min7','minmaj7','maj7','7','dim7','hdim7','sus2','sus4']
LABELS = [f'{r}:{q}' for r in ROOTS for q in QUALITIES]+['X','N']
_model = None
_normalization = None
_lock = threading.Lock()

def model():
    global _model, _normalization
    with _lock:
        if _model is None:
            import torch
            from vendor.btc.btc_model import BTC_model
            path = ROOT/'models/btc_model_large_voca.pt'
            provenance = json.loads((ROOT/'vendor/btc/provenance.json').read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest()!=provenance['weightsSha256']:
                raise ValueError('和弦模型权重校验失败')
            # Explicitly permit the NumPy scalar types used by this pinned official checkpoint.
            with torch.serialization.safe_globals([(np._core.multiarray.scalar, 'numpy.core.multiarray.scalar'), np.dtype,
                                                  np.dtypes.Float64DType, np.dtypes.Float32DType]):
                checkpoint = torch.load(path,map_location='cpu',weights_only=True)
            config = dict(feature_size=144,timestep=108,num_chords=170,hidden_size=128,
                          num_layers=8,num_heads=4,total_key_depth=128,total_value_depth=128,
                          filter_size=128,input_dropout=.2,layer_dropout=.2,attention_dropout=.2,
                          relu_dropout=.2,probs_out=True)
            network = BTC_model(config)
            network.load_state_dict(checkpoint['model'],strict=True)
            network.eval()
            torch.set_num_threads(4)
            _normalization=(float(checkpoint['mean']),float(checkpoint['std']))
            _model=network
    return _model,_normalization

def decode_path(probabilities, change_cost=1.2):
    """Potts transition cost: permits fast changes when acoustic evidence wins."""
    logp=np.log(np.maximum(probabilities,1e-8))
    score=logp[0].copy();back=np.zeros(logp.shape,dtype=np.int16)
    for i in range(1,len(logp)):
        best=int(np.argmax(score));switch=score[best]-change_cost
        stay=score>=switch
        back[i]=np.where(stay,np.arange(len(score)),best)
        score=np.maximum(score,switch)+logp[i]
    path=np.empty(len(logp),dtype=int);path[-1]=int(np.argmax(score))
    for i in range(len(path)-1,0,-1):path[i-1]=back[i,path[i]]
    return path


def analyze_chords(path, project_id, progress=None, cancelled=None):
    from engine import Cancelled
    progress=progress or (lambda *args:None)
    cancelled=cancelled or threading.Event()
    def stage(name,message):
        if cancelled.is_set():raise Cancelled()
        progress(name,message)
    started=time.monotonic();stage('chord_decode','正在准备重叠窗口和弦分析')
    signal,sr=sf.read(str(path),dtype='float32',always_2d=True)
    y=signal.mean(axis=1);duration=len(y)/sr
    if not 4<=duration<=600 or not np.isfinite(y).all():raise ValueError('音频长度或采样无效')
    if sr!=22050:y=soxr.resample(y,sr,22050)
    sr=22050;hop=2048;n=int(math.ceil(len(y)/hop));times=np.arange(n)*hop/sr
    energies=np.array([np.sqrt(np.mean(y[i*hop:min(len(y),(i+1)*hop)]**2)) for i in range(n)])
    peak=float(np.max(np.abs(y)));quiet=peak<1e-5
    feature_gain=min(32.,.25/max(peak,1e-8)) if 1e-5<=peak<.05 else 1.
    probabilities=np.zeros((n,170),dtype='float64')
    pitch_energy=np.zeros((n,12))
    if quiet:probabilities[:,169]=1
    else:
        import librosa
        import torch
        stage('chord_model','正在加载 BTC 并计算连续音频特征')
        network,(mean,std)=model()
        magnitude=np.abs(librosa.cqt(y*feature_gain,sr=sr,n_bins=144,bins_per_octave=24,hop_length=hop)[:,:n])
        feature=((np.log(magnitude+1e-6).T-mean)/std).astype('float32')
        counts=np.zeros(n);weights=np.maximum(.15,np.hanning(108))
        starts=list(range(0,max(1,n-108+1),54))
        if starts[-1]!=max(0,n-108):starts.append(max(0,n-108))
        for start in starts:
            stage('chord_inference',f'正在聚合 {start*hop/sr:.1f} 秒附近的和弦上下文')
            end=min(n,start+108);length=end-start;chunk=np.pad(feature[start:end],((0,108-length),(0,0)))
            with torch.inference_mode():
                hidden,_=network.self_attn_layers(torch.from_numpy(chunk).unsqueeze(0))
                logits=network.output_layer(hidden)[0,:length].numpy()
            probabilities[start:end]+=logits*weights[:length,None];counts[start:end]+=weights[:length]
        logits=probabilities/counts[:,None];logits-=logits.max(axis=1,keepdims=True)
        probabilities=np.exp(logits);probabilities/=probabilities.sum(axis=1,keepdims=True)
        stage('tonal_evidence','正在核验持续和弦音，降低 walking bass 经过音的影响')
        from tonal_evidence import from_cqt
        pitch_energy=from_cqt(magnitude)
    stage('chord_segments','正在整理连续和弦与静音区间')
    smooth=uniform_filter1d(probabilities,size=3,axis=0,mode='nearest')
    decoded=decode_path(smooth)
    # Conservative sustained low-energy gate. No song-specific end time.
    threshold=max(1e-5,float(np.percentile(energies,95))*.005)
    low=energies<threshold;silence=np.zeros(n,dtype=bool)
    start=0
    while start<n:
        end=start+1
        while end<n and low[end]==low[start]:end+=1
        if low[start] and (end-start)*hop/sr>=.45:silence[start:end]=True
        start=end
    raw=[];events=[]
    for i,t in enumerate(times):
        top=np.argsort(probabilities[i])[-3:][::-1]
        rank=np.argsort(smooth[i])[-2:][::-1];winner=int(decoded[i]);reason='sequence_decoder'
        score=float(smooth[i,winner]);alternative=float(np.max(np.delete(smooth[i],winner)))
        if silence[i]:winner=169;reason='sustained_low_energy'
        elif score<.35 or score-alternative<.08:winner=168;reason='uncertain'
        label=LABELS[winner];end=times[i+1] if i+1<n else duration
        raw.append({'timeSec':round(float(t),5),'label':LABELS[int(top[0])],
                    'top3':[{'label':LABELS[int(k)],'score':round(float(probabilities[i,k]),5)} for k in top],
                    'scores':[round(float(x),6) for x in probabilities[i]],'rms':round(float(energies[i]),7),
                    'pitchEnergy':[round(float(x),7) for x in pitch_energy[i]]})
        if events and events[-1]['label']==label and events[-1]['reason']==reason:events[-1]['endSec']=round(float(end),5)
        else:events.append({'id':f'chord-{len(events)+1}','startSec':round(float(t),5),'endSec':round(float(end),5),
                           'label':label,'bassNote':None,'status':'candidate','source':'BTC-ISMIR19',
                           'reason':reason,'confidence':None})
    stage('complete','重叠窗口和弦候选已生成')
    return {'schemaVersion':1,'engineVersion':VERSION,'projectId':project_id,
            'audioSha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'durationSec':round(duration,5),
            'revision':0,'events':events,'rawFrames':raw,'annotation':None,'analysisSeconds':round(time.monotonic()-started,2),
            'method':{'model':'BTC-ISMIR19 large vocabulary','classes':170,'device':'CPU',
                      'weightsSha256':json.loads((ROOT/'vendor/btc/provenance.json').read_text())['weightsSha256'],
                      'sampleRate':sr,'hopLength':hop,'windowFrames':108,'strideFrames':54,'aggregation':'center-weighted logits',
                      'featureGain':feature_gain,'smoothingFrames':3,'transitionCost':1.2,'unknownThreshold':.35,'marginThreshold':.08,
                      'silenceRmsThreshold':threshold,'silenceMinimumSeconds':.45,'labelOrder':LABELS,
                      'scoreMeaning':'uncalibrated softmax, not accuracy','externalAudioUpload':False},
            'tonalEvidence':{'version':'harmonic-pitch-evidence-v1','method':'nonnegative harmonic CQT fit; MIDI 36-84; below MIDI48 weight 0.25','trained':False,'changesRawBTCProbabilities':False},
            'warnings':['和弦为机器候选；没有自动识别实际低音、转位或调性。',
                        '重叠推理与连续性解码未改变模型权重。分数未校准，未知区间允许保留。',
                        '低能量门限可能影响安静段落；请对照原音频回听。']}


def validate_annotation(value,duration):
    if not isinstance(value,dict) or not isinstance(value.get('events'),list):raise ValueError('和弦校正格式无效')
    events=value['events']
    if not 1<=len(events)<=10000:raise ValueError('和弦区间数量无效')
    last=0;ids=set();clean=[]
    import re
    for e in events:
        if not isinstance(e,dict):raise ValueError('和弦事件格式无效')
        a,b=e.get('startSec'),e.get('endSec')
        if any(type(v) not in (float,int) or not math.isfinite(v) for v in (a,b)):raise ValueError('和弦时间无效')
        if abs(a-last)>.001 or b<=a or b>duration+.001:raise ValueError('和弦区间必须连续覆盖音频')
        label=e.get('label','')
        if label not in ('N','X'):
            m=re.fullmatch(r'([A-G](?:#|b)?):(.+)',label)
            if not m or m[2] not in QUALITIES:raise ValueError('不支持的和弦标签')
        bass=e.get('bassNote')
        if bass is not None and (not isinstance(bass,str) or not re.fullmatch(r'[A-G](?:#|b)?',bass)):raise ValueError('低音音名无效')
        if label in ('N','X') and bass is not None:raise ValueError('未知和弦不附加斜线低音')
        if e.get('status') not in ('candidate','user_corrected','confirmed'):raise ValueError('和弦确认状态无效')
        eid=e.get('id')
        if not isinstance(eid,str) or not 1<=len(eid)<=80 or eid in ids:raise ValueError('和弦事件 ID 无效')
        ids.add(eid);last=b
        clean.append({k:e.get(k) for k in ['id','startSec','endSec','label','bassNote','status']}|{'source':'user_annotation'})
    if abs(last-duration)>.001:raise ValueError('和弦区间未覆盖结尾')
    return {'events':clean}
