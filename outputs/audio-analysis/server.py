"""Loopback-only project server. Standard library HTTP + queued local analysis.

Audio is analyzed locally; optional Qwen sends text evidence only. Separate
annotations preserve the original model output and allow revision checks.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import mimetypes
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from engine import analyze, Cancelled, VERSION

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "audio-analysis" / "data"
DATA.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 30 * 1024 * 1024
JOBS = {}
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1)
PROJECT_ID = re.compile(r"^[0-9a-f]{20}$")


def write_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    os.replace(tmp,path)


def project_path(project_id):
    if not PROJECT_ID.fullmatch(project_id):
        raise ValueError("项目 ID 无效")
    return DATA / project_id / "analysis.json"


def load_project(project_id):
    return json.loads(project_path(project_id).read_text(encoding="utf-8"))


def validate_annotation(annotation, duration):
    if not isinstance(annotation,dict):
        raise ValueError("校正内容必须为对象")
    def numeric(x):
        return type(x) in (int,float) and math.isfinite(x)
    for field in ["beats","downbeats"]:
        values = annotation.get(field)
        if not isinstance(values,list) or len(values)>10000 or any(not numeric(v) or not 0<=v<duration for v in values):
            raise ValueError("拍点时间无效")
        if any(a>=b for a,b in zip(values,values[1:])):
            raise ValueError("拍点必须严格按时间排列")
    beats=annotation["beats"]
    if any(not any(abs(d-b)<.05 for b in beats) for d in annotation["downbeats"]):
        raise ValueError("强拍必须对应一个拍点")
    segments=annotation.get("segments")
    if not isinstance(segments,list) or not 1<=len(segments)<=200:
        raise ValueError("段落数量无效")
    last=0
    for segment in segments:
        if not isinstance(segment,dict):
            raise ValueError("段落格式无效")
        a,b=segment.get("startSec"),segment.get("endSec")
        if not numeric(a) or not numeric(b) or abs(a-last)>.001 or b<=a or b>duration+.001:
            raise ValueError("段落必须连续覆盖音频，且结束时间大于开始时间")
        label=segment.get("label")
        if not isinstance(label,str) or not 1<=len(label.strip())<=80:
            raise ValueError("段落名称应为 1–80 个字符")
        if segment.get("status") not in ("candidate","user_corrected","confirmed"):
            raise ValueError("段落状态无效")
        last=b
    if abs(last-duration)>.001:
        raise ValueError("段落未覆盖音频结尾")
    if annotation.get("status") not in ("candidate","user_corrected","confirmed"):
        raise ValueError("校正状态无效")
    meter=annotation.get("beatsPerBar")
    if meter is not None and (type(meter) is not int or meter not in range(2,8)):
        raise ValueError("每小节拍数无效")
    anchor=annotation.get('barAnchorIndex')
    if anchor is not None and (type(anchor) is not int or not 0<=anchor<len(beats)):
        raise ValueError('小节首拍索引无效')
    clean={"beats":beats,"downbeats":annotation["downbeats"],"segments":segments,
           "beatsPerBar":meter,"status":annotation["status"]}
    grouping=annotation.get('meterSegments',[])
    if not isinstance(grouping,list) or len(grouping)>1000:raise ValueError('拍数分段无效')
    cursor=0;parts=[]
    for s in grouping:
        if not isinstance(s,dict):raise ValueError('拍数分段无效')
        a,b,m,k=s.get('startBeatIndex'),s.get('endBeatIndex'),s.get('beatsPerBar'),s.get('anchorBeatIndex')
        if any(type(v) is not int for v in [a,b,k]) or a!=cursor or not a<b<=len(beats) or not a<=k<b:
            raise ValueError('拍数分段必须连续覆盖拍点，首拍需在分段内')
        if m is not None and (type(m) is not int or m not in range(2,8)):raise ValueError('分段拍数无效')
        if s.get('beatUnit') is not None:raise ValueError('当前版本不推断拍号分母')
        parts.append({key:s.get(key) for key in ['startBeatIndex','endBeatIndex','beatsPerBar','anchorBeatIndex']}|{'beatUnit':None,'source':'saved_grouping','status':'candidate'})
        cursor=b
    if parts and cursor!=len(beats):raise ValueError('拍数分段未覆盖拍点结尾')
    clean['meterSegments']=parts
    if annotation.get('activityEndSec') is not None:
        end=annotation['activityEndSec']
        if not numeric(end) or not 0<=end<=duration or (beats and end<=beats[-1]):raise ValueError('有效声音结尾无效')
        clean['activityEndSec']=end
    if 'rhythmConfirmed' in annotation:
        if type(annotation['rhythmConfirmed']) is not bool:raise ValueError('节奏确认状态无效')
        if annotation['rhythmConfirmed'] and ((meter is None and not any(s['beatsPerBar'] for s in parts)) or len(beats)<2):raise ValueError('节奏信息不足，不能锁定')
        clean['rhythmConfirmed']=annotation['rhythmConfirmed']
    if parts:
        clean['downbeats']=[t for s in parts if s['beatsPerBar'] for i,t in enumerate(beats) if s['startBeatIndex']<=i<s['endBeatIndex'] and (i-s['anchorBeatIndex'])%s['beatsPerBar']==0]
    elif anchor is not None:
        clean['barAnchorIndex']=anchor
        clean['downbeats']=[t for i,t in enumerate(beats) if meter and (i-anchor)%meter==0]
    return clean


def run_job(job_id,path,name):
    with LOCK: job=JOBS[job_id]
    def progress(stage,message):
        with LOCK: job.update(stage=stage,message=message)
    try:
        if job["cancel"].is_set(): raise Cancelled()
        result=analyze(path,name,progress,job["cancel"])
        with LOCK:
            if job["cancel"].is_set(): raise Cancelled()
            if (path.parent/'analysis.json').exists():
                previous=json.loads((path.parent/'analysis.json').read_text(encoding='utf8'))
                result['annotation']=copy.deepcopy(previous.get('annotation'))
                result['revision']=previous['revision']+1
                result['preservedAnnotationFrom']=previous.get('engineVersion')
            write_json(path.parent/"analysis.json",result)
            job.update(status="complete",projectId=result["id"],message="分析完成，可以回听校正。")
    except Cancelled:
        with LOCK: job.update(status="cancelled",message="分析已取消；不会覆盖已保存结果。")
    except Exception as exc:
        with LOCK: job.update(status="failed",message=str(exc)[:500])


def chord_path(pid):
    return project_path(pid).with_name('chords.json')


def run_chord_job(job_id,pid):
    from chords import analyze_chords
    with LOCK:job=JOBS[job_id]
    def progress(stage,message):
        with LOCK:job.update(stage=stage,message=message)
    try:
        project=load_project(pid)
        path=(ROOT/project['audioUrl'].lstrip('/')).resolve()
        if not path.is_relative_to(DATA):raise ValueError('音频路径无效')
        result=analyze_chords(path,pid,progress,job['cancel'])
        with LOCK:
            if job['cancel'].is_set():raise Cancelled()
            # Separate persistence: never write to analysis.json.
            if chord_path(pid).exists():
                previous=json.loads(chord_path(pid).read_text(encoding='utf8'))
                write_json(chord_path(pid).with_name('chords-before-'+uuid.uuid4().hex[:8]+'.json'),previous)
                result['annotation']=copy.deepcopy(previous.get('annotation'))
                result['revision']=previous['revision']+1
                result['preservedAnnotationFrom']=previous.get('engineVersion')
            write_json(chord_path(pid),result)
            job.update(status='complete',projectId=pid,message='和弦候选已生成，可以循环回听。')
    except Cancelled:
        with LOCK:job.update(status='cancelled',message='和弦分析已取消，原有结果保留。')
    except Exception as exc:
        with LOCK:job.update(status='failed',message=str(exc)[:500])


class Handler(BaseHTTPRequestHandler):
    server_version="LowEndLab/0.7.0"

    def log_message(self,fmt,*args):
        print(fmt % args,flush=True)

    def host_ok(self):
        return self.headers.get("Host","") in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}")

    def json(self,code,value):
        data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        self.wfile.write(data)

    def mutation_allowed(self):
        origin=self.headers.get("Origin")
        return self.host_ok() and self.headers.get("X-Requested-With")=="LowEndLab" and (
            origin is None or origin in (f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"))

    def read_body(self,limit):
        length=int(self.headers.get("Content-Length","0"))
        if not 0<length<=limit:
            raise ValueError("请求为空或超过大小限制")
        self.connection.settimeout(30)
        data=self.rfile.read(length)
        if len(data)!=length:
            raise ValueError("上传中断，请重试")
        return data

    def do_GET(self):
        if not self.host_ok(): return self.json(403,{"error":"只接受本机访问"})
        route=urlsplit(self.path).path
        try:
            if route=="/api/health":
                from chords import VERSION as chord_version
                return self.json(200,{"ok":True,"appVersion":"0.7.0","engineVersion":VERSION,"chordEngineVersion":chord_version,"localAudioAnalysis":True,"optionalCloudTextQA":True})
            if route=="/api/coach/status":
                from qwen_coach import public_status
                return self.json(200,public_status())
            if route=="/api/projects":
                projects=[]
                for p in sorted(DATA.glob("*/analysis.json"),key=lambda p:p.stat().st_mtime,reverse=True):
                    try:
                        item=json.loads(p.read_text(encoding="utf-8"))
                        projects.append({k:item[k] for k in ("id","name","durationSec","bpm","revision")})
                    except (ValueError,KeyError,OSError): continue
                return self.json(200,{"projects":projects})
            if re.fullmatch(r'/api/projects/[0-9a-f]{20}/chords',route):
                pid=route.split('/')[3]
                load_project(pid)
                if not chord_path(pid).exists():return self.json(200,{'available':False})
                return self.json(200,{'available':True,**json.loads(chord_path(pid).read_text(encoding='utf8'))})
            if route.startswith("/api/projects/"):
                return self.json(200,load_project(route.rsplit("/",1)[1]))
            if route.startswith("/api/jobs/"):
                with LOCK:
                    job=JOBS.get(route.rsplit("/",1)[1])
                    if not job: return self.json(404,{"error":"任务不存在，服务可能已重启；可从已保存项目恢复。"})
                    return self.json(200,{k:v for k,v in job.items() if k!="cancel"})
            self.serve_file(route)
        except (ValueError,FileNotFoundError): self.json(404,{"error":"文件或项目不存在"})
        except (BrokenPipeError,ConnectionResetError): pass

    def do_POST(self):
        if not self.mutation_allowed(): return self.json(403,{"error":"请求来源无效"})
        route=urlsplit(self.path).path
        try:
            if re.fullmatch(r'/api/projects/[0-9a-f]{20}/rhythm/review',route):
                from rhythm import review
                body=json.loads(self.read_body(2*1024*1024));pid=route.split('/')[3]
                project=load_project(pid)
                if body.get('revision')!=project['revision']:
                    return self.json(409,{'error':'节奏版本已变化，请重新载入。'})
                annotation=validate_annotation(body.get('annotation'),project['durationSec'])
                audio_path=ROOT/project['audioUrl'].lstrip('/')
                result=review(audio_path,annotation,project['durationSec'],body.get('mode','repair'))
                return self.json(200,result)
            if route=='/api/coach/ask':
                from qwen_coach import ask,CoachError
                try:
                    body=json.loads(self.read_body(16384))
                    def read_chords(pid):
                        with LOCK:return json.loads(chord_path(pid).read_text(encoding='utf8'))
                    return self.json(200,ask(body,load_project,read_chords))
                except CoachError as exc:return self.json(exc.status,{'error':str(exc)})
            if re.fullmatch(r'/api/projects/[0-9a-f]{20}/chords/analyze',route):
                from chords import VERSION as CHORD_VERSION
                pid=route.split('/')[3];project=load_project(pid)
                with LOCK:
                    if chord_path(pid).exists():
                        result=json.loads(chord_path(pid).read_text(encoding='utf8'))
                        if result.get('engineVersion')==CHORD_VERSION and result.get('audioSha256')==project['sha256']:
                            return self.json(200,{'cached':True,'projectId':pid})
                    existing=next((i for i,j in JOBS.items() if j.get('kind')=='chords' and j.get('assetId')==pid and j['status']=='running'),None)
                    if existing:return self.json(202,{'jobId':existing})
                    if sum(j['status']=='running' for j in JOBS.values())>=2:return self.json(429,{'error':'已有两个任务，请稍候。'})
                    jid=uuid.uuid4().hex
                    JOBS[jid]={'status':'running','kind':'chords','stage':'queued','message':'等待和弦分析','assetId':pid,'cancel':threading.Event()}
                    POOL.submit(run_chord_job,jid,pid)
                return self.json(202,{'jobId':jid})
            if route=="/api/analyze":
                name=unquote(self.headers.get("X-Audio-Name","audio.wav"))
                name=Path(name.replace("\\","/")).name[:180]
                suffix=Path(name).suffix.lower()
                if suffix not in (".mp3",".wav",".flac",".ogg"):
                    return self.json(400,{"error":"支持 MP3、WAV、FLAC、OGG"})
                with LOCK:
                    if sum(j["status"]=="running" for j in JOBS.values())>=2:
                        return self.json(429,{"error":"已有两个任务，请等待或取消后重试。"})
                data=self.read_body(MAX_UPLOAD)
                digest=hashlib.sha256(data).hexdigest();pid=digest[:20]
                folder=DATA/pid;folder.mkdir(exist_ok=True)
                with LOCK:
                    if (folder/"analysis.json").exists():
                        existing_result=load_project(pid)
                        if existing_result.get("engineVersion")==VERSION and existing_result.get("taskStatus",{}).get("beats")!="failed":
                            return self.json(200,{"cached":True,"projectId":pid})
                        # Keep prior model output and annotations before a version refresh.
                        backup=folder/f"analysis-before-{uuid.uuid4().hex[:8]}.json"
                        write_json(backup,existing_result)
                    existing=next((i for i,j in JOBS.items() if j.get("kind","audio")=="audio" and j.get("assetId")==pid and j["status"]=="running"),None)
                    if existing:return self.json(202,{"jobId":existing})
                    path=folder/("audio"+suffix);path.write_bytes(data)
                    job_id=uuid.uuid4().hex
                    JOBS[job_id]={"status":"running","stage":"queued","message":"等待分析","assetId":pid,"cancel":threading.Event()}
                    POOL.submit(run_job,job_id,path,name)
                return self.json(202,{"jobId":job_id})
            if re.fullmatch(r"/api/jobs/[0-9a-f]+/cancel",route):
                with LOCK:
                    job=JOBS.get(route.split("/")[3])
                    if not job:return self.json(404,{"error":"任务不存在"})
                    job["cancel"].set()
                    if job["status"]=="running":job["message"]="已请求取消，将在当前计算步骤结束后停止。"
                return self.json(200,{"ok":True})
            return self.json(404,{"error":"未知接口"})
        except (ValueError,TimeoutError) as exc:self.json(400,{"error":str(exc)})
        except FileNotFoundError:self.json(404,{"error":"项目不存在"})

    def do_PATCH(self):
        if not self.mutation_allowed():return self.json(403,{"error":"请求来源无效"})
        route=urlsplit(self.path).path
        if re.fullmatch(r'/api/projects/[0-9a-f]{20}/chords',route):
            try:
                from chords import validate_annotation as validate_chords
                body=json.loads(self.read_body(2*1024*1024));pid=route.split('/')[3]
                if not isinstance(body,dict):raise ValueError('请求应为对象')
                with LOCK:
                    project=load_project(pid)
                    result=json.loads(chord_path(pid).read_text(encoding='utf8'))
                    if type(body.get('revision')) is not int or body['revision']!=result['revision']:
                        return self.json(409,{'error':'和弦版本已更新，请重新载入和弦后编辑。'})
                    rhythm_revision=(body.get('annotation') or {}).get('rhythmRevision')
                    if rhythm_revision is not None and (type(rhythm_revision) is not int or rhythm_revision!=project['revision'] or not (project.get('annotation') or {}).get('rhythmConfirmed')):
                        return self.json(409,{'error':'按拍候选的节奏版本已变化或未锁定，请先重新核对节奏与和弦。'})
                    result['annotation']=validate_chords(body.get('annotation'),project['durationSec'])
                    if rhythm_revision is not None:result['annotation']['rhythmRevision']=rhythm_revision
                    result['revision']+=1;write_json(chord_path(pid),result)
                return self.json(200,{'available':True,**result})
            except (ValueError,KeyError,TypeError) as exc:return self.json(400,{'error':str(exc)})
            except FileNotFoundError:return self.json(404,{'error':'请先完成和弦分析'})
        if not re.fullmatch(r"/api/projects/[0-9a-f]{20}",route):return self.json(404,{"error":"未知项目"})
        try:
            body=json.loads(self.read_body(2*1024*1024))
            pid=route.rsplit("/",1)[1]
            with LOCK:
                result=load_project(pid)
                if body.get("revision")!=result["revision"]:
                    return self.json(409,{"error":"该项目已在另一页面更新，请重新载入后再编辑。"})
                result["annotation"]=validate_annotation(body.get("annotation"),result["durationSec"])
                result["revision"]+=1
                write_json(project_path(pid),result)
            self.json(200,result)
        except (ValueError,KeyError,TypeError) as exc:self.json(400,{"error":str(exc)})
        except FileNotFoundError:self.json(404,{"error":"项目不存在"})

    def serve_file(self,route):
        path=(ROOT/unquote(route).lstrip("/")).resolve() if route!="/" else ROOT/"index.html"
        if not path.is_relative_to(ROOT) or not path.is_file():raise FileNotFoundError()
        if path.suffix.lower() in (".py",".pyc",".ckpt",".pt",".pth",".cmd",".ps1",".env"):
            return self.json(403,{"error":"此资源不通过 HTTP 提供"})
        size=path.stat().st_size;start,end=0,size-1
        requested=self.headers.get("Range")
        code=200
        if requested:
            m=re.fullmatch(r"bytes=(\d+)-(\d*)",requested)
            if not m or int(m[1])>=size:
                self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
            start=int(m[1]);end=min(int(m[2]) if m[2] else end,size-1)
            if end<start:
                self.send_response(416);self.end_headers();return
            code=206
        self.send_response(code)
        self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(end-start+1));self.send_header("Accept-Ranges","bytes")
        self.send_header("Cache-Control","no-cache");self.send_header("X-Content-Type-Options","nosniff")
        if code==206:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start);remaining=end-start+1
            while remaining>0:
                chunk=f.read(min(65536,remaining))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"LOW END LAB ready at http://127.0.0.1:{args.port}/#analysis",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)
