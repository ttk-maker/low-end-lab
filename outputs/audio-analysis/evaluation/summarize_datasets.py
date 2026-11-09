"""Summarize completed diagnostic runs without touching any model or test split."""
import collections,json,platform,shutil,sys
from pathlib import Path
import numpy as np
from dataset_io import DATA,REPORT,WORKSPACE,save,digest

def main():
    summaries={}
    for path in REPORT.glob('*-diagnostic-report.json'):
        report=json.loads(path.read_text('utf8'));rows=report['rows'];complete=[r for r in rows if r['status']=='complete']
        entry={'selected':len(report['selectionIds']),'completed':len(complete),'failed':len(rows)-len(complete),'rowsWritten':len(rows),'runComplete':report.get('complete',False)}
        if report['task']=='rhythm':
            for key in ['rawBeat','processedBeat','rawDownbeat','groupedDownbeat']:
                values=[r[key] for r in complete if r.get(key)]
                entry[key]={'macroF1At70ms':float(np.mean([v['f1At70ms'] for v in values])) if values else None,
                            'macroCMLt':float(np.mean([v['CMLt'] for v in values])) if values else None,'items':len(values)}
        else:
            for key in ['raw','stableOracleGrid','stablePredictedGrid','rawAgainstInferred']:
                values=[r[key] for r in complete if r.get(key)];entry[key]={}
                for metric in ['root','triads','sevenths','tetrads']:
                    denom=sum(v[metric]['scoredSeconds'] for v in values)
                    entry[key][metric]={'durationWeightedAccuracy':sum((v[metric]['accuracy'] or 0)*v[metric]['scoredSeconds'] for v in values)/denom if denom else None,'scoredSeconds':denom}
                denom=sum(v['annotatedSeconds'] for v in values)
                entry[key]['durationWeightedCoverage']=sum(v['predictionCoverage']*v['annotatedSeconds'] for v in values)/denom if denom else None
        summaries[path.stem]=entry
    root=WORKSPACE/'outputs/audio-analysis'
    code=['engine.py','rhythm-grid.js','chords.py','harmony-structure.js','models/small0.ckpt','models/btc_model_large_voca.pt']
    provenance={name:digest(root/name) for name in code}
    evaluation_hashes={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}
    preservation_snapshot=WORKSPACE/'work/v07/before-hashes.json'
    before=json.loads(preservation_snapshot.read_text('utf8')) if preservation_snapshot.exists() else {}
    preserved={path:digest(WORKSPACE/path)==sha for path,sha in before.items()}
    imports={n:json.loads((REPORT/(n+'-import.json')).read_text('utf8')) for n in ['gtzan','guitarset','pop909']}
    renders=list((DATA/'pop909/rendered').glob('*.render.json'))
    save(REPORT/'summary.json',{'imports':imports,'diagnosticRuns':summaries,'renderedPOP909Count':len(renders),
        'frozenTestEvaluated':bool(list(REPORT.glob('*-frozen_test-report.json'))),'trainingPerformed':False,
        'productionProjectPreserved':preserved,'preservationSnapshotAvailable':preservation_snapshot.exists(),'codeAndModelSha256':provenance,
        'evaluationCodeSha256':evaluation_hashes,'python':platform.python_version(),'disk':{'datasetBytes':sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file()),'freeBytes':shutil.disk_usage(DATA).free}})
    print(json.dumps(summaries,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
