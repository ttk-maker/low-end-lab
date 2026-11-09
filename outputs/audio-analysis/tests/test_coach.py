"""Offline contract tests; these do not claim a real Qwen response."""
import io,json,os,sys,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qwen_coach as q

class CoachTests(unittest.TestCase):
    def setUp(self):
        q._cache.clear();q._inflight.clear()
        self.config=patch.object(q,'config',return_value={'apiKey':'test-only-secret','baseUrl':'https://example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1','model':q.MODEL});self.config.start();self.addCleanup(self.config.stop)
    def project(self,pid):return {'sha256':'abc'}
    def chords(self,pid):return {'revision':2,'annotation':{'events':[{'id':'a','startSec':0,'endSec':4,'label':'G:maj','bassNote':'B','status':'confirmed'}]}}
    def request(self):return {'question':'这个斜线低音与根音有什么区别？','projectId':'a'*20,'eventId':'a','revision':2}
    def test_confirmed_context_and_cache(self):
        calls=[]
        def mock(c,payload):
            self.assertEqual(payload['temperature'],0.2)
            self.assertIn('尚不能自行判别',payload['messages'][0]['content'])
            calls.append(payload);data=json.loads(payload['messages'][1]['content'])
            self.assertFalse(data['audioIncluded']);self.assertEqual(data['context']['tones'][0]['name'],'G');self.assertEqual(data['context']['event']['bassNote'],'B')
            self.assertNotIn('test-only-secret',json.dumps(payload))
            return {'answer':'根音是 G，低音 B 是三音。[K11]','usage':{'total_tokens':100},'finishReason':'stop'}
        a=q.ask(self.request(),self.project,self.chords,mock);b=q.ask(self.request(),self.project,self.chords,mock)
        self.assertFalse(a['cached']);self.assertTrue(b['cached']);self.assertEqual(len(calls),1)
    def test_stale_unconfirmed_and_invented_context(self):
        body=self.request();body['revision']=1
        with self.assertRaises(q.CoachError):q.evidence(body,self.project,self.chords)
        body=self.request();body['eventId']='fake'
        with self.assertRaises(q.CoachError):q.evidence(body,self.project,self.chords)
        result=q.evidence({'question':'什么是小七和弦？','tones':['fake']},self.project,self.chords)
        self.assertIsNone(result['context']);self.assertNotIn('tones',result)
    def test_not_configured(self):
        with patch.object(q,'config',return_value={'apiKey':'','baseUrl':'','model':q.MODEL}):
            with self.assertRaises(q.CoachError) as e:q.ask({'question':'什么是小七和弦？'},self.project,self.chords)
            self.assertEqual(e.exception.status,503)
    def test_uncited_claim_warning(self):
        r=q.ask({'question':'什么是和弦？'},self.project,self.chords,lambda *a:{'answer':'[K999]','finishReason':'stop'})
        self.assertTrue(r['warnings']);self.assertEqual(q._cache,{})
    def test_sse_parser_and_no_reasoning_leak(self):
        content='data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'hidden-thought'}}]})+'\n\n'
        content+='data: '+json.dumps({'choices':[{'delta':{'content':'小七和弦'},'finish_reason':'stop'}]})+'\n\n'
        content+='data: '+json.dumps({'choices':[],'usage':{'total_tokens':25}})+'\n\ndata: [DONE]\n'
        class Opener:
            def open(self,*args,**kwargs):return io.BytesIO(content.encode())
        with patch('urllib.request.build_opener',return_value=Opener()):
            r=q.remote(q.config(),{'stream':True});self.assertEqual(r['answer'],'小七和弦');self.assertEqual(r['usage']['total_tokens'],25)
    def test_http_error_redacts_provider_body(self):
        class Opener:
            def open(self,*args,**kwargs):raise urllib.error.HTTPError('https://example',401,'test-only-secret',{},None)
        with patch('urllib.request.build_opener',return_value=Opener()):
            with self.assertRaises(q.CoachError) as e:q.remote(q.config(),{})
            self.assertNotIn('test-only-secret',str(e.exception))
    def test_tones(self):
        self.assertEqual([t['name'] for t in q.chord_tones('C#:minmaj7')],['C#','E','G#','B#'])

    def test_stale_rhythm_evidence_rejected(self):
        chords=self.chords('a');chords['annotation']['rhythmRevision']=2
        project={'sha256':'abc','revision':3,'annotation':{'rhythmConfirmed':True}}
        with self.assertRaises(q.CoachError) as e:q.evidence(self.request(),lambda _:project,lambda _:chords)
        self.assertEqual(e.exception.status,409)

    def test_duplicate_endpoint_rejected(self):
        with self.assertRaises(q.CoachError) as e:
            q.validate_config('test-only-secret','https://ws-example.cn-beijing.maas.aliyuncs.com.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',q.MODEL)
        self.assertIn('后缀重复',str(e.exception))
        self.assertNotIn('test-only-secret',str(e.exception))
        c=q.validate_config('test-only-secret','https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',q.MODEL)
        self.assertTrue(c['baseUrl'])

    def test_connection_errors_distinguished_and_redacted(self):
        cert=q.ssl.SSLCertVerificationError(1,'private-address-or-secret')
        cert.verify_code=62
        cases=[(cert,'域名不匹配',502),(q.socket.gaierror(-2,'private-address-or-secret'),'无法解析',502),
               (TimeoutError('private-address-or-secret'),'超时',504)]
        for reason,expected,status in cases:
            class Opener:
                def open(self,*args,**kwargs):raise urllib.error.URLError(reason)
            with patch('urllib.request.build_opener',return_value=Opener()):
                with self.assertRaises(q.CoachError) as e:q.remote(q.config(),{})
                self.assertIn(expected,str(e.exception))
                self.assertNotIn('private-address-or-secret',str(e.exception))
                self.assertEqual(e.exception.status,status)

if __name__=='__main__':unittest.main()
