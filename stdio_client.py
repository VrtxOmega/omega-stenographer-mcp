"""Small, bounded, initialized stdio MCP client for the bundled helpers."""
import subprocess,sys,json,queue,threading,os
from collections import deque
class StdioClient:
 def __init__(self,script,timeout=60):
  self.timeout=timeout;self.number=0;self.lock=threading.Lock();self.q=queue.Queue();self.errors=deque(maxlen=100)
  self.process=subprocess.Popen([sys.executable,str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  def read():
   for line in self.process.stdout:
    try:self.q.put(json.loads(line))
    except ValueError:self.q.put({'error':'Non-JSON server output'})
  threading.Thread(target=read,daemon=True).start()
  def read_errors():
   for line in self.process.stderr:self.errors.append(line)
  threading.Thread(target=read_errors,daemon=True).start()
  self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'omega-helper','version':'2'}})
  self.process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');self.process.stdin.flush()
 def request(self,method,params):
  import time
  with self.lock:
   self.number+=1;self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.number,'method':method,'params':params})+'\n');self.process.stdin.flush();deadline=time.monotonic()+self.timeout
   while True:
    if time.monotonic()>=deadline:raise TimeoutError('MCP request timed out')
    response=self.q.get(timeout=max(.01,deadline-time.monotonic()))
    if response.get('id')!=self.number:continue
    if response.get('error'):raise RuntimeError(response['error'])
    return response['result']
 def call(self,tool,args):
  result=self.request('tools/call',{'name':tool,'arguments':args})
  if result.get('isError'):raise RuntimeError(result.get('content'))
  content=result.get('content',[]);text=content[0].get('text','') if content else ''
  try:return json.loads(text)
  except ValueError:return {'text':text}
 def close(self):
  if self.process.poll() is None:
   self.process.stdin.close()
   try:self.process.wait(3)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
  for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
