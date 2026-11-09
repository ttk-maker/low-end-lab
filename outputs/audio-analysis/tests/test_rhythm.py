import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhythm import propose

class RhythmTests(unittest.TestCase):
    def test_four_minutes_missing_beat_repaired_from_audio(self):
        truth=np.arange(.2,240,.5);detected=np.delete(truth,[129,301])
        r=propose(detected,truth[::4],4,240,truth,np.ones(len(truth)))
        np.testing.assert_allclose(r['beats'],truth,atol=1e-5)
        self.assertEqual(len(r['changes']),2)
        self.assertFalse(r['unresolved'])
        np.testing.assert_allclose(r['downbeats'],truth[::4])
    def test_gap_without_audio_not_filled(self):
        truth=np.arange(.2,240,.5);detected=np.delete(truth,129)
        r=propose(detected,truth[::4],4,240,detected,np.ones(len(detected)))
        self.assertEqual(len(r['beats']),len(detected));self.assertEqual(len(r['unresolved']),1)
    def test_steady_fit_avoids_rounded_bpm_accumulation(self):
        rng=np.random.default_rng(22);truth=.2+np.arange(520)*60/130.7
        measured=truth+rng.normal(0,.006,len(truth))
        r=propose(measured,measured[::4],4,240,truth,np.ones(len(truth)),'steady')
        self.assertLess(abs(r['beats'][-1]-truth[-1]),.005)
        self.assertLess(abs(r['fit']['bpm']-130.7),.01)
    def test_variable_tempo_preserved_and_steady_rejected(self):
        truth=np.r_[.2,.2+np.cumsum(np.linspace(.55,.42,420))]
        r=propose(truth,truth[::3],3,240,truth,np.ones(len(truth)))
        np.testing.assert_allclose(r['beats'],truth,atol=1e-5)
        with self.assertRaises(ValueError):propose(truth,truth[::3],3,240,truth,np.ones(len(truth)),'steady')
    def test_pickup_and_no_tail_extrapolation(self):
        truth=np.arange(.2,18,.5)
        r=propose(truth,truth[2::4],4,24,truth,np.ones(len(truth)),anchor_index=2)
        self.assertEqual(r['barAnchorIndex'],2)
        self.assertLess(r['beats'][-1],18)
        np.testing.assert_allclose(r['downbeats'],truth[2::4])

if __name__=='__main__':unittest.main()
