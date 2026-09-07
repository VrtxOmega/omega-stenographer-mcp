"""Initialized helper with explicit task/session scope."""
from pathlib import Path
from stdio_client import StdioClient
class StenographerClient(StdioClient):
 def __init__(self,server_path=None,session_id=None):
  self.session_id=session_id
  super().__init__(server_path or Path(__file__).parent/'omega_stenographer_mcp_standalone.py')
 def _scope(self,session_id=None):
  sid=session_id or self.session_id
  if not sid:raise ValueError('session_id is required')
  return sid
 def ingest(self,role,content,session_id=None):return self.call('stenographer_ingest_exchange',dict(role=role,content=content,session_id=self._scope(session_id)))
 def get_brief(self,session_id=None):return self.call('stenographer_get_brief',dict(session_id=self._scope(session_id)))
 def compact_guard(self,query='',session_id=None):return self.call('stenographer_compact_guard',dict(query=query,session_id=self._scope(session_id)))
 def mark_milestone(self,exchange_id,label,session_id=None):return self.call('stenographer_mark_milestone',dict(exchange_id=exchange_id,label=label,session_id=self._scope(session_id)))
 def search(self,query,limit=10,session_id=None):return self.call('stenographer_query_history',dict(query=query,limit=limit,session_id=self._scope(session_id)))
