"""Reused synthetic regression; supplied grid, not new holdout accuracy."""
import argparse,json,subprocess
from pathlib import Path
from run import score
from chords import analyze_chords

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',required=True);parser.add_argument('--report',required=True);parser.add_argument('--cached-results');args=parser.parse_args()
    work=Path(args.work_dir);work.mkdir(parents=True,exist_ok=True);root=Path(__file__).parent
    manifest=json.loads((root/'fixtures/manifest.json').read_text());rows=[]
    for item in manifest:
        result=json.loads((Path(args.cached_results)/(item['id']+'-v2.json')).read_text()) if args.cached_results else analyze_chords(root/'fixtures'/item['audio'],item['id'])
        beats=[i*.5 for i in range(int(result['durationSec']*2+.999)) if i*.5<result['durationSec']]
        grid={'beats':beats,'downbeats':beats[::4],'beatsPerBar':4}
        inp=work/(item['id']+'-input.json');out=work/(item['id']+'-stable.json')
        inp.write_text(json.dumps({'result':result,'grid':grid}),encoding='utf8')
        subprocess.run(['node',str(root/'stable_chords.cjs'),str(inp),str(out)],check=True)
        ref=[(e['startSec'],e['endSec'],e['label']) for e in item['reference']]
        rows.append({'id':item['id'],'raw':score(ref,result['events']),'stable':score(ref,json.loads(out.read_text())['events'])})
    summary={}
    for version in ['raw','stable']:
        scores=[r[version] for r in rows]
        summary[version]={'weightedAccuracy':sum(s['correctSeconds'] for s in scores)/sum(s['durationSec'] for s in scores),
                          'musicAccuracy':sum(s['musicCorrectSeconds'] for s in scores)/sum(s['musicSeconds'] for s in scores),
                          'segments':sum(s['segments'] for s in scores)}
    Path(args.report).write_text(json.dumps({'kind':'reused frozen synthetic chord fixtures; assumed 120 BPM grid, not end-to-end rhythm accuracy or a new holdout','rows':rows,'summary':summary},indent=2),encoding='utf8')
    print(json.dumps(summary))

if __name__=='__main__':main()
