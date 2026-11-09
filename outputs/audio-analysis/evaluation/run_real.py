"""Score reviewed, independent real-song labels, skip pending annotations."""
import argparse
import hashlib
import json
from pathlib import Path
from run import score,baseline,analyze_chords,validate_annotation
import soundfile as sf

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default=str(Path(__file__).with_name('real_manifest.json')));parser.add_argument('--output',required=True)
    args=parser.parse_args();manifest=Path(args.manifest).resolve();data=json.loads(manifest.read_text(encoding='utf8'))
    rows=[];pending=[];seen=set()
    for item in data['items']:
        if not item.get('reviewed'):pending.append(item['id']);continue
        if not item.get('reviewer') or not item.get('rights'):raise ValueError('已审核素材必须注明审核者与使用依据')
        path=(manifest.parent/item['audio']).resolve();digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:raise ValueError('评测集中存在重复音频，不能重复计分')
        seen.add(digest);info=sf.info(path);duration=info.frames/info.samplerate
        events=[dict(e,id=f'ref-{i}',bassNote=None,status='confirmed') for i,e in enumerate(item['reference'])]
        validate_annotation({'events':events},duration)
        ref=[(e['startSec'],e['endSec'],e['label'])for e in events]
        if any(e['label']=='X' for e in events):raise ValueError('当前整段计分模式不接受未审核 X，请完善标签或暂设 reviewed=false')
        row={'id':item['id'],'sha256':digest,'reviewer':item['reviewer']}
        for version,fn in [('v1',baseline),('v2',analyze_chords)]:row[version]=score(ref,fn(path,item['id'])['events'])
        rows.append(row)
    result={'kind':'human-reviewed real-song evaluation','scoredSongs':len(rows),'pendingIds':pending,'rows':rows,
            'status':'evaluated' if rows else 'awaiting_independent_annotations'}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
