import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
from run import score

class MetricTests(unittest.TestCase):
    def test_duration_weighted_not_frame_count(self):
        result=score([(0,1,'C:maj'),(1,4,'G:maj')],[{'startSec':0,'endSec':4,'label':'C:maj'}])
        self.assertEqual(result['weightedAccuracy'],.25)
    def test_unknown_coverage(self):
        result=score([(0,4,'C:maj')],[{'startSec':0,'endSec':2,'label':'C:maj'},{'startSec':2,'endSec':4,'label':'X'}])
        self.assertEqual(result['weightedAccuracy'],.5);self.assertEqual(result['coverage'],.5);self.assertEqual(result['selectiveAccuracy'],1)
    def test_silence_separate_and_boundaries_one_to_one(self):
        result=score([(0,2,'C:maj'),(2,4,'N')],[{'startSec':0,'endSec':1.9,'label':'C:maj'},{'startSec':1.9,'endSec':2.1,'label':'X'},{'startSec':2.1,'endSec':4,'label':'N'}])
        self.assertAlmostEqual(result['silenceCorrectSeconds'],1.9);self.assertEqual(result['boundaryPrecision'],.5);self.assertEqual(result['boundaryRecall'],1)

if __name__=='__main__':unittest.main()
