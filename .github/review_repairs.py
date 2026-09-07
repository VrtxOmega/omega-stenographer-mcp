"""Assertion-checked, one-shot repair for the dedicated review branch."""
import json, os
from pathlib import Path

changed=[]
def save(name,text):
    Path(name).parent.mkdir(parents=True,exist_ok=True)
    Path(name).write_text(text,encoding='utf-8',newline='\n')
    changed.append(name)

# The workflow checks out the exact tested Brain source commit, not moving main.
for name in ('omega_runtime.py','veritas_bridge.py'):
    save(name,(Path('../brain-reviewed')/name).read_text(encoding='utf-8'))
p=Path('Dockerfile').read_text(encoding='utf-8')
old='COPY omega_stenographer_mcp_standalone.py .'
assert p.count(old)==1
p=p.replace(old,'COPY omega_stenographer_mcp_standalone.py omega_stenographer_mcp.py omega_runtime.py veritas_bridge.py codex_capture.py steno_client.py stdio_client.py ./')
p=p.replace('WORKDIR /app','WORKDIR /app\nRUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*')
save('Dockerfile',p)
save('tests/test_review_regressions.py','''import os,subprocess,sys,tempfile,unittest
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
''')
save('docs/REVIEW_FOLLOWUP_2026-09-07.md','''# September 7 review follow-up

The Docker image now includes the server, compatibility entry point, shared runtime, bridge, capture helper and clients it imports or exposes. CI imports the installed distribution outside the source checkout and tests the non-root Docker runtime.

Event-type and source filters run in SQL before LIMIT, so a later unrelated event cannot hide a terminal shutdown. The public embedding dimension is 512; requesting a legacy 128-dimensional representation fails explicitly instead of silently returning an incompatible vector. The shared runtime and bridge match the reviewed Brain implementation.

Source identities include tracked data and nonignored new source files; generated Git-ignored output is not source. These changes preserve task scoping and do not create an OS sandbox or verify the operator's live backup. Tests use synthetic temporary data only.
''')
Path(os.environ['RUNNER_TEMP'],'review-files.json').write_text(json.dumps(changed),encoding='utf-8')
