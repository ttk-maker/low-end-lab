"""Pinned, resumable downloads and safe bounded extraction for evaluation only."""
import hashlib,json,time,zipfile,tarfile,shutil
from pathlib import Path
import requests

WORKSPACE=Path(__file__).resolve().parents[3]
DATA=WORKSPACE/'work/evaluation-datasets'
REPORT=WORKSPACE/'outputs/audio-analysis/evaluation/dataset-import-2026-11-09'

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');temp.replace(path)

def digest(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def download(url,path,expected=None,size=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    algorithm,want=expected.split(':',1) if expected else ('sha256',None)
    if path.exists() and (not size or path.stat().st_size==size) and (not want or digest(path,algorithm)==want):return path
    part=path.with_suffix(path.suffix+'.part');last=0
    for attempt in range(5):
        offset=part.stat().st_size if part.exists() else 0
        if size and offset==size:break
        try:
            with requests.get(url,headers={'Range':f'bytes={offset}-'} if offset else {},stream=True,timeout=(20,60)) as r:
                r.raise_for_status()
                if offset and r.status_code==206:
                    if not r.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('Invalid resumed range')
                    mode='ab'
                else:offset=0;mode='wb'
                length=int(r.headers.get('Content-Length',0));total=offset+length
                if shutil.disk_usage(path.parent).free<max(0,total-offset)+512*1024**2:raise OSError('Insufficient disk space for this download')
                with part.open(mode) as f:
                    for chunk in r.iter_content(1024*1024):
                        if not chunk:continue
                        f.write(chunk);offset+=len(chunk)
                        if time.monotonic()-last>15:
                            print(f'download {path.name}: {offset/1e6:.1f}/{(size or total)/1e6:.1f} MB',flush=True);last=time.monotonic()
                if total and offset!=total:raise IOError('Incomplete download')
            break
        except (requests.RequestException,IOError) as e:
            print(f'retry {path.name}: {type(e).__name__}',flush=True)
            if attempt==4:raise
            time.sleep(min(2**attempt,8))
    if size and part.stat().st_size!=size:raise ValueError('Downloaded size mismatch')
    got=digest(part,algorithm)
    if want and got!=want:raise ValueError('Downloaded checksum mismatch; partial file retained for inspection')
    part.replace(path)
    save(path.with_suffix(path.suffix+'.receipt.json'),{'url':url,'bytes':path.stat().st_size,'sha256':digest(path),'upstreamChecksum':expected})
    return path

def target(root,name):
    root=Path(root).resolve();p=(root/name).resolve()
    if not p.is_relative_to(root):raise ValueError('Archive path escapes destination')
    return p

def extract_zip(archive,root,accept=lambda name:True):
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if member.is_dir() or not accept(member.filename):continue
            if (member.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive symlink not allowed')
            p=target(root,member.filename);p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists() and p.stat().st_size==member.file_size:continue
            with z.open(member) as src,p.open('wb') as dst:shutil.copyfileobj(src,dst)

def extract_tar(archive,root,accept=lambda name:True):
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            if not member.isfile() or not accept(member.name):continue
            p=target(root,member.name);p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists() and p.stat().st_size==member.size:continue
            with tar.extractfile(member) as src,p.open('wb') as dst:shutil.copyfileobj(src,dst)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('path');p.add_argument('--checksum');p.add_argument('--size',type=int);a=p.parse_args()
    download(a.url,a.path,a.checksum,a.size)
