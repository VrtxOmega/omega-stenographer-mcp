import os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ReviewRegressions(unittest.TestCase):
    def test_event_filtering_and_embedding_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            code="""
import veritas_bridge as b
b.emit_event('CLAEG_TERMINAL_SHUTDOWN',{},source='wanted',task_id='alpha')
for _ in range(5):b.emit_event('NOISE',{},source='other',task_id='alpha')
assert len(b.get_recent_terminal_shutdowns(1,task_id='alpha'))==1
assert len(b.read_events(1,source='wanted',task_id='alpha'))==1
assert b.read_events(1,task_id='beta')==[]
assert b.TFIDF_DIM==len(b.tfidf_embed('example'))==512
assert b.tokenize('Example token')==b.runtime.tokens('Example token')
try:b.tfidf_embed('example',dim=128)
except ValueError:pass
else:raise AssertionError('Legacy dimension silently accepted')
"""
            result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=dict(os.environ,VERITAS_SHARED_DIR=temp+'/shared',OMEGA_STENOGRAPHER_DIR=temp+'/steno'),capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
