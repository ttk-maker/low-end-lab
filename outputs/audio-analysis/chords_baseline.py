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
VERSION = 'btc-170-v1'
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

def analyze_chords(path, project_id, progress=None, cancelled=None):
    from engine import Cancelled
    progress=progress or (lambda *args:None)
    cancelled=cancelled or threading.Event()
    def stage(name,message):
        if cancelled.is_set():raise Cancelled()
        progress(name,message)
    started=time.monotonic()
    stage('chord_decode','正在读取音频，准备和弦特征')
    signal,sr=sf.read(str(path),dtype='float32',always_2d=True)
    y=signal.mean(axis=1)
    duration=len(y)/sr
    if not 4<=duration<=600 or not np.isfinite(y).all():raise ValueError('音频长度或采样无效')
    if sr!=22050:y=soxr.resample(y,sr,22050)
    sr=22050;hop=2048
    times=[];posteriors=[];energies=[]
    silence=float(np.max(np.abs(y)))<1e-5
    if not silence:
        import librosa
        import torch
        stage('chord_model','正在加载 BTC 170 类和弦模型')
        network,(mean,std)=model()
        for start in range(0,len(y),sr*10):
            stage('chord_inference',f'正在识别 {start/sr:.0f} 秒附近的和弦')
            chunk=y[start:start+sr*10]
            # Preserve the author's 10-second CQT windows; use actual hop timestamps,
            # not 10/108, to avoid accumulated drift. Pad short tails for CQT only.
            cqt=librosa.cqt(np.pad(chunk,(0,max(0,4096-len(chunk)))),sr=sr,
                            n_bins=144,bins_per_octave=24,hop_length=hop)
            n=min(108,int(math.ceil(len(chunk)/hop)))
            feature=((np.log(np.abs(cqt[:,:n])+1e-6).T-mean)/std).astype('float32')
            feature=np.pad(feature,((0,108-n),(0,0)))
            with torch.inference_mode():
                hidden,_=network.self_attn_layers(torch.from_numpy(feature).unsqueeze(0))
                probabilities=torch.softmax(network.output_layer(hidden),dim=-1)[0,:n].numpy()
            for i in range(n):
                a=i*hop;b=min(len(chunk),a+hop)
                times.append((start+a)/sr)
                energies.append(float(np.sqrt(np.mean(chunk[a:b]**2))))
            posteriors.extend(probabilities)
    else:
        times=list(np.arange(0,duration,hop/sr));energies=[0.]*len(times)
        posteriors=np.zeros((len(times),170));posteriors[:,169]=1
    stage('chord_segments','正在整理和弦候选与未知区间')
    probs=np.asarray(posteriors)
    smooth=uniform_filter1d(probs,size=3,axis=0,mode='nearest')
    threshold=max(1e-5,max(energies,default=0)*.001)
    raw=[];events=[]
    for i,t in enumerate(times):
        top=np.argsort(probs[i])[-3:][::-1]
        ranking=np.argsort(smooth[i])[-2:][::-1]
        winner=int(ranking[0]);score=float(smooth[i,winner]);margin=score-float(smooth[i,ranking[1]])
        reason='model'
        if energies[i]<threshold:winner=169;reason='silence_gate'
        elif score<.35 or margin<.08:winner=168;reason='uncertain'
        label=LABELS[winner]
        end=times[i+1] if i+1<len(times) else duration
        raw.append({'timeSec':round(t,5),'label':LABELS[int(top[0])],
                    'top3':[{'label':LABELS[int(k)],'score':round(float(probs[i,k]),5)}for k in top],
                    'rms':round(energies[i],7)})
        if events and events[-1]['label']==label and events[-1]['reason']==reason:
            events[-1]['endSec']=round(end,5)
        else:
            events.append({'id':f'chord-{len(events)+1}','startSec':round(t,5),'endSec':round(end,5),
                           'label':label,'bassNote':None,'status':'candidate','source':'BTC-ISMIR19',
                           'reason':reason,'confidence':None})
    stage('complete','和弦候选已生成，等待回听校正')
    return {'schemaVersion':1,'engineVersion':VERSION,'projectId':project_id,
            'audioSha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'durationSec':round(duration,5),'revision':0,'events':events,'rawFrames':raw,
            'annotation':None,'analysisSeconds':round(time.monotonic()-started,2),
            'method':{'model':'BTC-ISMIR19 large vocabulary','classes':170,'device':'CPU',
                      'weightsSha256':json.loads((ROOT/'vendor/btc/provenance.json').read_text())['weightsSha256'],
                      'sampleRate':sr,'hopLength':hop,'chunkSeconds':10,'smoothingFrames':3,
                      'unknownThreshold':.35,'marginThreshold':.08,'silenceRmsThreshold':threshold,
                      'scoreMeaning':'uncalibrated softmax, not accuracy','externalAudioUpload':False},
            'warnings':['和弦为机器候选；没有自动识别实际低音、转位或调性。',
                        'N 为无和弦候选；X 为未知。静音门限仅用于拒绝低能量片段。',
                        '短片段、复杂混音与持续音可能产生错误或频繁换和弦，请循环回听。']}

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
