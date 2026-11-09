import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhythm_pipeline import analyze,pulse_repair
from server import validate_annotation


class EvidenceTests(unittest.TestCase):
    def test_silent_stereo_and_cancelled_phase(self):
        sr=8000;y=np.zeros((sr*10,2));t=np.arange(sr*4)/sr
        y[sr*2:sr*6,0]=.1*np.sin(2*np.pi*100*t);y[:,1]=-y[:,0]
        r=analyze(y,sr,list(np.arange(0,10,.5)),[0,2,4,6,8],4)
        self.assertEqual(r['beats'],list(np.arange(2,6,.5)))
        self.assertEqual(r['removedQuietBeats'],12)
        self.assertEqual(analyze(np.zeros_like(y),sr,[1,2],[1],4)['beats'],[])

    def test_variable_tempo_unchanged(self):
        bs=np.r_[.3,.3+np.cumsum(np.linspace(.54,.43,420))]
        f={'broad':np.zeros(12000),'times':np.arange(12000)*.02,'hopSec':.02}
        actual,changes=pulse_repair(bs,f)
        np.testing.assert_array_equal(actual,bs);self.assertEqual(changes,[])

    def test_sparse_gap_requires_acoustic_evidence(self):
        truth=np.arange(1,100,.5);beats=np.delete(truth,[30,60]);times=np.arange(0,102,.02)
        flux=np.zeros(len(times));flux[np.rint(truth/.02).astype(int)]=1
        actual,changes=pulse_repair(beats,{'broad':flux,'times':times,'hopSec':.02})
        np.testing.assert_allclose(actual,truth,atol=.011);self.assertEqual(len(changes),2)
        actual,changes=pulse_repair(beats,{'broad':flux*0,'times':times,'hopSec':.02})
        np.testing.assert_array_equal(actual,beats);self.assertEqual(changes,[])

    def test_segment_validation_and_roundtrip(self):
        a={'beats':np.arange(0,14,.5).tolist(),'downbeats':[0,2,4,6,8,9.5,11,12.5],
           'beatsPerBar':None,'rhythmConfirmed':True,'status':'candidate',
           'segments':[{'startSec':0,'endSec':14,'label':'片段','status':'candidate'}],
           'meterSegments':[{'startBeatIndex':0,'endBeatIndex':16,'beatsPerBar':4,'anchorBeatIndex':0},
                            {'startBeatIndex':16,'endBeatIndex':28,'beatsPerBar':3,'anchorBeatIndex':16}]}
        r=validate_annotation(a,14)
        self.assertEqual(r['downbeats'],a['downbeats']);self.assertEqual(len(r['meterSegments']),2)
        a['meterSegments'][1]['startBeatIndex']=17
        with self.assertRaises(ValueError):validate_annotation(a,14)

if __name__=='__main__':unittest.main()
