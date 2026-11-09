"""Real local audio analysis. Neural beats + explicit acoustic novelty baseline.

No language model, chord recognition, or semantic verse/chorus classification.
All timestamps refer to the original decoded audio, in seconds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import scipy.signal
import scipy.ndimage
import soundfile as sf
import soxr

VERSION = "0.4.0"
ROOT = Path(__file__).resolve().parent
MAX_SECONDS = 600
_tracker = None
_model_lock = threading.Lock()


class Cancelled(Exception):
    pass


def model_path():
    configured = os.environ.get("LOWEND_BEAT_MODEL")
    path = Path(configured) if configured else ROOT / "models" / "small0.ckpt"
    if not path.is_file():
        raise RuntimeError("缺少 Beat This! small0 权重；请运行安装脚本，或设置 LOWEND_BEAT_MODEL。")
    return path


def beat_tracker():
    global _tracker
    with _model_lock:
        if _tracker is None:
            import torch
            from beat_this.inference import Audio2Beats
            torch.set_num_threads(min(4, os.cpu_count() or 2))
            _tracker = Audio2Beats(checkpoint_path=str(model_path()), device="cpu", dbn=False)
    return _tracker


def rounded(values):
    return [round(float(v), 5) for v in values]


def waveform(y, bins=1400):
    edges = np.linspace(0, len(y), min(bins, len(y)) + 1, dtype=int)
    return [round(float(np.max(np.abs(y[a:b]))), 5) for a, b in zip(edges[:-1], edges[1:])]


def acoustic_sections(y, sr, duration, downbeats):
    """Compare neighboring 2s log-frequency spectra and energy at 0.25s steps.

    Peak prominence is a relative acoustic-change score, NOT confidence.
    No forced number of sections and no inferred functional labels.
    """
    nfft, hop = 2048, 512
    freqs, times, z = scipy.signal.stft(y, sr, nperseg=nfft, noverlap=nfft-hop,
                                       boundary="zeros", padded=True)
    power = np.abs(z) ** 2
    bands = np.geomspace(35, min(10000, sr/2-1), 33)
    features = []
    for lo, hi in zip(bands[:-1], bands[1:]):
        ix = (freqs >= lo) & (freqs < hi)
        features.append(np.log1p(10000 * power[ix].mean(axis=0)) if ix.any() else np.zeros(len(times)))
    feature = np.asarray(features)
    std = np.maximum(feature.std(axis=1, keepdims=True), .05)
    feature = (feature - feature.mean(axis=1, keepdims=True)) / std
    probe_times = np.arange(0, duration, .25)
    scores = np.zeros(len(probe_times))
    for i, t in enumerate(probe_times):
        if t < 2 or t > duration-2:
            continue
        left = feature[:, (times >= t-2) & (times < t)]
        right = feature[:, (times >= t) & (times < t+2)]
        if left.size and right.size:
            scores[i] = np.sqrt(np.mean((left.mean(axis=1)-right.mean(axis=1))**2))
    scores = scipy.ndimage.gaussian_filter1d(scores, 1)
    norm = scores / max(float(scores.max()), 1e-9)
    peaks, props = scipy.signal.find_peaks(norm, distance=16, prominence=.14, height=.24)
    candidates = []
    for p, prominence in zip(peaks, props["prominences"]):
        t = float(probe_times[p])
        # Keep the measured change time; attach nearby downbeat only as context.
        nearest = min(downbeats, key=lambda d: abs(d-t)) if len(downbeats) else None
        if 3 <= t <= duration-3:
            candidates.append({"timeSec": round(t, 4), "noveltyScore": round(float(norm[p]), 4),
                               "prominence": round(float(prominence), 4),
                               "nearbyDownbeatSec": round(float(nearest), 4) if nearest is not None and abs(nearest-t)<1 else None})
    boundaries = [0] + [x["timeSec"] for x in candidates] + [round(duration, 5)]
    segments = [{"id": f"section-{i+1}", "startSec": a, "endSec": b,
                 "label": f"段落 {i+1}", "status": "candidate", "source": "spectral-novelty-v1"}
                for i, (a, b) in enumerate(zip(boundaries[:-1], boundaries[1:]))]
    return segments, candidates, {"times": rounded(probe_times), "values": rounded(norm)}


def analyze(path, name=None, progress=None, cancelled=None):
    started = time.monotonic()
    progress = progress or (lambda stage, message: None)
    cancelled = cancelled or threading.Event()

    def stage(key, message):
        if cancelled.is_set():
            raise Cancelled("分析已取消")
        progress(key, message)

    path = Path(path)
    stage("decoding", "正在解码音频")
    try:
        info = sf.info(str(path))
    except Exception as exc:
        raise ValueError("无法解码此音频，请使用有效的 MP3、WAV 或 FLAC 文件。") from exc
    duration = info.frames / info.samplerate
    if not 4 <= duration <= MAX_SECONDS or info.channels > 8 or info.samplerate > 192000:
        raise ValueError("本阶段支持 4 秒至 10 分钟、最多 8 声道、采样率不超过 192 kHz 的音频。")
    signal, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = signal.mean(axis=1)
    if not np.isfinite(mono).all():
        raise ValueError("音频含无效采样值。")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    duration = len(mono)/sr
    peak = float(np.max(np.abs(mono)))
    wave = waveform(mono)
    y = soxr.resample(mono, sr, 22050).astype(np.float32) if sr != 22050 else mono
    warnings = []
    if peak < 1e-5:
        beats, downbeats = np.array([]), np.array([])
        warnings.append("音频接近静音，未生成拍点。")
        beat_source = "silence-rejection"
        weight_sha = None
    else:
        stage("beats", "Beat This! 正在检测拍点和强拍候选")
        try:
            tracker = beat_tracker()
            beats, downbeats = tracker(y, 22050)
            beats = np.asarray(beats)
            beats = np.unique(beats[(beats >= 0) & (beats < duration)])
            downbeats = np.asarray(downbeats)
            downbeats = np.unique(downbeats[(downbeats >= 0) & (downbeats < duration)])
            beat_source = "Beat This! small0 (minimal postprocessor, CPU)"
            weight_sha = hashlib.sha256(model_path().read_bytes()).hexdigest()
        except Exception as exc:
            beats, downbeats = np.array([]), np.array([])
            beat_source, weight_sha = "failed", None
            warnings.append("节拍分析失败，已保留波形与段落分析；可手动建立网格。原因："+str(exc)[:180])
    stage("sections", "正在寻找音色与能量变化形成的段落边界")
    segments, boundaries, novelty = acoustic_sections(y, 22050, duration, downbeats) if peak >= 1e-5 else (
        [{"id":"section-1","startSec":0,"endSec":round(duration,5),"label":"未分段","status":"candidate","source":"silence-rejection"}], [], {"times":[],"values":[]})
    intervals = np.diff(beats)
    bpm = round(float(60 / np.median(intervals)), 2) if len(intervals) else None
    variation = float(np.std(intervals)/np.mean(intervals)) if len(intervals) else None
    if len(beats) < 4:
        warnings.append("可靠的拍点不足；可以手动设置速度与首拍，不应把当前结果当作完整节拍网格。")
    if variation is not None and variation > .12:
        warnings.append("拍间距变化较大，可能存在变速、漏拍或倍速/半速歧义，请先回听。")
    if len(beats) and duration-beats[-1]>2:
        warnings.append(f"{beats[-1]:.2f} 秒之后未检出拍点，可能是尾音或漏检；没有自动补齐。")
    if len(beats) and beats[0]>2:
        warnings.append(f"首个拍点在 {beats[0]:.2f} 秒；之前的音频未自动外推拍点。")
    meter = None
    counts = []
    for a, b in zip(downbeats[:-1], downbeats[1:]):
        counts.append(int(np.sum((beats >= a-.04) & (beats < b-.04))))
    if len(counts) >= 3:
        values, cnt = np.unique(counts, return_counts=True)
        best = int(values[np.argmax(cnt)])
        if best in (2,3,4,5,6,7) and max(cnt)/len(counts) >= .7:
            meter = best
    from rhythm_pipeline import analyze as refine_rhythm
    neural_beats,neural_downbeats=rounded(beats),rounded(downbeats)
    stage('rhythm_evidence','正在核验静音、稀疏漏拍与局部拍数证据')
    refined=refine_rhythm(signal,sr,neural_beats,neural_downbeats,meter)
    beats=np.asarray(refined['beats']);downbeats=np.asarray(refined['downbeats'])
    intervals=np.diff(beats)
    bpm=round(float(60/np.median(intervals)),2) if len(intervals) else None
    variation=float(np.std(intervals)/np.mean(intervals)) if len(intervals) else None
    if refined['meterSegments']:
        groups={s['beatsPerBar'] for s in refined['meterSegments']}
        meter=next(iter(groups)) if len(groups)==1 else None
    warnings.append("段落仅为声学变化候选；局部拍数是分组证据，不代表已识别完整拍号。未确定区间不会自动指定音高。")
    result = {
        "schemaVersion": 1, "engineVersion": VERSION, "id": digest[:20], "sha256": digest,
        "name": name or path.name, "durationSec": round(duration,5), "sampleRate": sr,
        "channels": int(signal.shape[1]), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "revision": 0, "audioUrl": f"/audio-analysis/data/{digest[:20]}/audio{path.suffix.lower()}",
        "waveform": wave, "beats": rounded(beats), "downbeats": rounded(downbeats),
        "neuralRawBeats":neural_beats,"neuralRawDownbeats":neural_downbeats,
        "rhythmEvidence":refined,"meterSegments":refined['meterSegments'],
        "activityEndSec":refined['activity']['activityEndSec'],
        "bpm": bpm, "bpmAlternatives": [round(bpm/2,2),bpm,round(bpm*2,2)] if bpm else [],
        "beatsPerBarCandidate": meter, "intervalVariation": round(variation,4) if variation is not None else None,
        "segments": segments, "boundaryCandidates": boundaries, "novelty": novelty,
        "status": "candidate", "warnings": warnings, "confidence": None,
        "taskStatus": {"beats":"failed" if beat_source=="failed" else "complete",
                       "sections":"complete"},
        "methods": {"beats":beat_source, "beatWeightsSha256":weight_sha,
                    "sections":"spectral-novelty-v1: 32 log-frequency bands; 2s left/right windows; 0.25s hop; peak filtering",
                    "semanticLabels":False, "externalAudioUpload":False},
        "analysisSeconds": round(time.monotonic()-started,2), "annotation": None,
    }
    stage("complete", "分析完成，等待回听与校正")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = analyze(args.audio, progress=lambda s,m: print(s,m,flush=True))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ["durationSec","bpm","beatsPerBarCandidate","analysisSeconds"]}),flush=True)
