"""Source hashing must not inherit or stall an active MCP stdio stream."""
import os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import omega_runtime as runtime
from stdio_client import StdioClient
ROOT = Path(__file__).resolve().parents[1]
class StdioSourceTests(unittest.TestCase):
    def test_git_input_is_explicitly_disconnected(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('subprocess.run', wraps=subprocess.run) as run:
                runtime.source_identity(temp)
            self.assertTrue(run.call_args_list)
            self.assertTrue(all(c.kwargs.get('stdin') == subprocess.DEVNULL for c in run.call_args_list))
    def test_hashing_over_a_live_stdio_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'source'; source.mkdir()
            subprocess.run(['git','init',str(source)], stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=10)
            (source/'input.txt').write_text('source input', encoding='utf-8')
            script = base/'source_server.py'
            lines = ['import sys', 'sys.path.insert(0, '+repr(str(ROOT))+')',
                     'from mcp.server.fastmcp import FastMCP', 'import omega_runtime as runtime',
                     "app=FastMCP('source-regression')", '@app.tool()',
                     'def snapshot(root: str) -> dict:', '    return {"sha256":runtime.source_identity(root)}',
                     "app.run(transport='stdio')"]
            script.write_text(chr(10).join(lines)+chr(10), encoding='utf-8')
            with patch.dict(os.environ, {'VERITAS_SHARED_DIR':str(base/'shared'), 'PYTHONUTF8':'1'}):
                with StdioClient(script, timeout=15) as client:
                    first = client.call('snapshot', {'root':str(source)})
                    self.assertEqual(first['sha256'], runtime.source_identity(source))
                    self.assertEqual(client.call('snapshot', {'root':str(source)}), first)
