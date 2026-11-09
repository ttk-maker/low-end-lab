import tempfile,unittest
from pathlib import Path
import mido
from dataset_io import target
from pop909_adapter import tempo_map,references,normalize_marker
from render_pop909 import strip_reference
from run_datasets import chord_scores
from import_datasets import validate_beats,split_for

class Adapters(unittest.TestCase):
    def test_tempo_change_nondefault_ppq(self):
        midi=mido.MidiFile(ticks_per_beat=960);midi.tracks.append(mido.MidiTrack([
            mido.MetaMessage('set_tempo',tempo=500000),mido.MetaMessage('set_tempo',tempo=1000000,time=1920)]))
        convert=tempo_map(midi)
        self.assertEqual(convert(960),.5);self.assertEqual(convert(2880),2.)

    def test_strip_preserves_note_timing_and_removes_answers(self):
        midi=mido.MidiFile();score=mido.MidiTrack([mido.MetaMessage('track_name',name='PIANO'),
            mido.MetaMessage('marker',text='C:M',time=120),mido.Message('note_on',note=60,time=120),mido.Message('note_off',note=60,time=480)])
        midi.tracks=[score,mido.MidiTrack([mido.MetaMessage('track_name',name='CHORDS'),mido.Message('note_on',note=48)])]
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.mid';b=Path(tmp)/'b.mid';midi.save(a);strip_reference(a,b);clean=mido.MidiFile(b)
            self.assertEqual(len(clean.tracks),1);self.assertFalse(any(m.type=='marker' for m in clean.tracks[0]))
            self.assertEqual(next(m.time for m in clean.tracks[0] if m.type=='note_on'),240)

    def test_missing_prediction_is_error_not_excluded(self):
        score=chord_scores([{'startSec':2,'endSec':4,'label':'C:maj'}],[])
        self.assertEqual(score['root']['accuracy'],0);self.assertEqual(score['root']['scoredSeconds'],2)

    def test_unknown_reference_and_gaps_not_silence(self):
        score=chord_scores([{'startSec':1,'endSec':2,'label':'C:maj'},{'startSec':3,'endSec':4,'label':'X'}],
                           [{'startSec':0,'endSec':5,'label':'C:maj'}])
        self.assertEqual(score['annotatedSeconds'],1);self.assertEqual(score['unknownReferenceSeconds'],1)
        self.assertEqual(score['root']['accuracy'],1)

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):target(Path.cwd(),'../outside')

    def test_reference_validation_and_inversions(self):
        self.assertIn('implausibly_close_reference_beats',validate_beats([0,.02],[1,2],1))
        self.assertEqual(normalize_marker('A#:m7/C#'),'A#:min7/b3')
        self.assertEqual(normalize_marker('B:/o7/D'),'B:hdim7/b3')
        self.assertEqual(normalize_marker('B:/o7'),'B:hdim7')
        self.assertEqual(split_for('same-composition'),split_for('same-composition'))

    def test_compound_meter(self):
        midi=mido.MidiFile(ticks_per_beat=960)
        midi.tracks=[mido.MidiTrack([mido.MetaMessage('time_signature',numerator=6,denominator=8),
                    mido.MetaMessage('set_tempo',tempo=1000000),mido.MetaMessage('marker',text='C:M')]),
                    mido.MidiTrack([mido.MetaMessage('track_name',name='CHORDS'),mido.Message('note_on',note=60),mido.Message('note_off',note=60,time=5760)])]
        ref,duration=references(midi)
        self.assertEqual(ref['beats'],[0.,1.5,3.,4.5]);self.assertEqual(ref['downbeats'],[0.,3.])
        self.assertEqual(ref['grid']['beatsPerBar'],2)

if __name__=='__main__':unittest.main()
