import unittest,tempfile,os,sys,asyncio,json,gc
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();ROOT=Path(TEMP.name)
os.environ.update(OMEGA_STENOGRAPHER_DIR=str(ROOT/'steno'),VERITAS_SHARED_DIR=str(ROOT/'shared'),OMEGA_BRAIN_DATA_DIR=str(ROOT/'brain'),OMEGA_CODEX_SESSIONS=str(ROOT/'sessions'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import omega_stenographer_mcp as steno
import codex_capture as capture
def call(name,args):return asyncio.run(steno.call_tool(name,args))
class Contracts(unittest.TestCase):
 def test_scope_required(self):
  with self.assertRaises(ValueError):call('stenographer_get_brief',{})
 def test_history_isolation(self):
  for sid in ('one','two'):call('stenographer_ingest_exchange',dict(role='user',content='needle memory '+sid,session_id=sid))
  r=json.loads(call('stenographer_query_history',dict(query='needle',session_id='one'))[0].text)
  self.assertTrue(r);self.assertTrue(all(x['session_id']=='one' for x in r))
 def test_capture_filters(self):
  def msg(role,text,phase=None):return {'type':'response_item','payload':{'type':'message','role':role,'phase':phase,'content':[{'type':'text','text':text}]}}
  self.assertIsNone(capture.visible(msg('assistant','reasoning','analysis')))
  self.assertEqual(capture.visible(msg('assistant','visible','final_answer')),('assistant','visible'))
  self.assertIsNone(capture.visible(msg('user','<environment_context>config')))
 def test_receipt_deduplication(self):
  args=dict(role='user',content='unique deduplicated',session_id='dedup',source_key='stable-key')
  call('stenographer_ingest_exchange',args);call('stenographer_ingest_exchange',args)
  self.assertEqual(len(json.loads(call('stenographer_query_history',dict(query='unique',session_id='dedup'))[0].text)),1)
 def test_milestone_scope(self):
  call('stenographer_ingest_exchange',dict(role='user',content='milestone fixture',session_id='owner'))
  r=json.loads(call('stenographer_query_history',dict(query='milestone',session_id='owner'))[0].text)
  with self.assertRaises(ValueError):call('stenographer_mark_milestone',dict(exchange_id=r[0]['id'],label='wrong',session_id='other'))
 def test_initialized_helper(self):
  from steno_client import StenographerClient
  with StenographerClient(session_id='client') as client:
   client.ingest('user','client retains searchablefixture')
   self.assertTrue(client.search('searchablefixture'))
 def test_resource_scope(self):self.assertIn('SCOPE_REQUIRED',asyncio.run(steno.read_resource('omega-stenographer://session/notes')))
def tearDownModule():gc.collect();TEMP.cleanup()
if __name__=='__main__':unittest.main(verbosity=2)
