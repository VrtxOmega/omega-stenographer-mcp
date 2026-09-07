#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ── Venv auto-activation shim ──────────────────────────────────
# If running from system Python but mcp deps are in .venv,
# re-exec with the venv Python so imports resolve correctly.
import os as _os, sys as _sys
if not _sys.prefix != _sys.base_prefix:  # not already in a venv
    _venv_py = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".venv",
                             "Scripts" if _sys.platform == "win32" else "bin", "python")
    if _os.path.isfile(_venv_py):
        _os.execv(_venv_py, [_venv_py] + _sys.argv)
del _os, _sys
# ── End shim ───────────────────────────────────────────────────
"""Omega Stenographer MCP Server — Passive session observer for Omega Brain.
Ingests every turn, extracts decisions/blockers, builds running notes,
and returns compressed briefs when compaction threatens context loss.
"""
import os, sys, re, json, sqlite3, hashlib, time, math, asyncio
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

import anyio

import omega_runtime as runtime
from mcp import types
from mcp.server import Server, NotificationOptions
from mcp.shared.message import SessionMessage
from mcp.types import Tool, TextContent, Resource


@asynccontextmanager
async def stdio_server():
    """Line-delimited stdio transport that works reliably with piped stdin."""
    read_send, read_recv = anyio.create_memory_object_stream(0)
    write_send, write_recv = anyio.create_memory_object_stream(0)

    async def stdin_reader():
        async with read_send:
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if line == "":
                    break
                try:
                    message = types.JSONRPCMessage.model_validate_json(line)
                except Exception as exc:
                    await read_send.send(exc)
                    continue
                await read_send.send(SessionMessage(message))

    async def stdout_writer():
        async with write_recv:
            async for session_message in write_recv:
                payload = session_message.message.model_dump_json(
                    by_alias=True,
                    exclude_none=True,
                )
                print(payload, flush=True)

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)
        yield read_recv, write_send
        tg.cancel_scope.cancel()

# ── VERITAS Bridge (cross-system integration) ──────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent))
    import veritas_bridge as _bridge
    HAS_BRIDGE = True
except Exception:
    HAS_BRIDGE = False
    _bridge = None  # type: ignore

# ── Configuration ──────────────────────────────────────────
STENO_DIR = Path(os.environ.get("OMEGA_STENOGRAPHER_DIR", Path.home() / ".omega-stenographer"))
STENO_TURN_LIMIT = int(os.environ.get("STENO_TURN_LIMIT", "8"))
STENO_TOP_K = int(os.environ.get("STENO_TOP_K", "5"))

STENO_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STENO_DIR / "steno.db"

# ── Database ───────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS exchanges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        decisions TEXT,
        blockers TEXT,
        compressed INTEGER DEFAULT 0,
        tier TEXT DEFAULT 'B',
        milestone TEXT,
        session_id TEXT,
        trace_id TEXT,
        nafe_flags TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS exchanges_fts USING fts5(
        content, decisions, blockers, tokenize='porter unicode61'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS briefs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        summary TEXT NOT NULL,
        tier TEXT DEFAULT 'B',
        source_turns TEXT,
        session_id TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS briefs_fts USING fts5(
        summary, tokenize='porter unicode61'
    )""")
    conn.commit()
    # ── Schema migrations (idempotent) ──────────────────────────
    for migration in [
        "ALTER TABLE exchanges ADD COLUMN trace_id TEXT",
        "ALTER TABLE exchanges ADD COLUMN nafe_flags TEXT",
        "ALTER TABLE briefs ADD COLUMN session_id TEXT",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass  # Column already exists — expected on existing DBs
    return conn

# ── TF-IDF Embedding ───────────────────────────────────────
def tokenize(text):
    return re.findall(r'[a-zA-Z]{3,}', text.lower())

def tfidf_embed(text,dim=512):
    return runtime.embed(text)

def cosine_sim(a,b):
    return runtime.cosine(a,b)

def normalize_fts_query(query, max_terms=12):
    """Build a forgiving FTS query for hyphenated paths, trace IDs, and tool names."""
    terms = []
    seen = set()
    for term in re.findall(r'[A-Za-z0-9_]{2,}', query):
        lowered = term.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return " OR ".join(terms)

# ── Core Logic ─────────────────────────────────────────────
def extract_decisions(text):
    """Extract decision-like statements"""
    patterns = [
        r'(?:decided|decision|chose|opted|settled on|went with)\s+(?:to\s+)?(.+?)(?:\.|;|$|\n)',
        r'(?:key\s+)?(?:finding|insight|conclusion):\s*(.+?)(?:\.|;|$|\n)',
        r'→\s*(.+?)(?:\.|;|$|\n)',
    ]
    decisions = []
    for pat in patterns:
        decisions.extend(re.findall(pat, text, re.IGNORECASE))
    return [d.strip() for d in decisions if len(d.strip()) > 10]

def extract_blockers(text):
    """Extract blocker/problem statements"""
    patterns = [
        r'(?:blocked|stuck|can\'t|cannot|unable to|failing|error|issue|bug|problem|crashed|timeout)\s*(?:on|with|because|due to)?\s*(.+?)(?:\.|;|$|\n)',
        r'(?:✗|❌|🚫)\s*(.+?)(?:\.|;|$|\n)',
    ]
    blockers = []
    for pat in patterns:
        blockers.extend(re.findall(pat, text, re.IGNORECASE))
    return [b.strip() for b in blockers if len(b.strip()) > 5]

def compress_unprocessed(conn,current_session_id=None):
    if not current_session_id:raise ValueError('session_id required for compression')
    rows=conn.execute('SELECT id,role,content,decisions,blockers FROM exchanges WHERE compressed=0 AND session_id=? ORDER BY id',(current_session_id,)).fetchall()
    if len(rows)<STENO_TURN_LIMIT:return None
    facts=[]
    for r in rows:
        text=r[2]
        facts.append({'exchange_id':r[0],'role':r[1],'decisions':json.loads(r[3] or '[]'),'blockers':json.loads(r[4] or '[]'),'context':text[:1000],'has_more':len(text)>1000,'signals':[m.group(0) for m in re.finditer(r'[^.\n]*(?:next|must|constraint|instead|correction|supersed|unresolved)[^.\n]*',text,re.I)][:12]})
    summary=json.dumps({'version':2,'session_id':current_session_id,'kind':'extracted context, not verified truth','sources':facts},ensure_ascii=False)
    ids=[r[0] for r in rows]
    cur=conn.execute('INSERT INTO briefs(summary,tier,source_turns,session_id) VALUES(?,?,?,?)',(summary,'B',json.dumps(ids),current_session_id))
    conn.execute('INSERT INTO briefs_fts(rowid,summary) VALUES(?,?)',(cur.lastrowid,summary))
    conn.executemany('UPDATE exchanges SET compressed=1 WHERE id=?',[(i,) for i in ids]);conn.commit()
    return {'brief_id':cur.lastrowid,'summary':summary,'turn_count':len(ids),'tier':'B'}

# ── MCP Server ─────────────────────────────────────────────
server = Server("omega-stenographer")

@server.list_tools()
async def list_tools():
    tools = [
        Tool(name="stenographer_ingest_exchange",
             description=(
                 "Ingest a conversation turn. Call after every significant user or assistant message. "
                 "Automatically: extracts decisions/blockers via regex, runs NAFE failure-signature "
                 "scan (heuristic flags do not establish truth), checks for cross-system CLAEG "
                 "TERMINAL_SHUTDOWN events, and compresses every STENO_TURN_LIMIT turns "
                 "into session-scoped tiered briefs. Pass trace_id from omega_preload_context "
                 "to enable cross-system correlation across Omega Brain, SSWP, and Stenographer."
             ),
             inputSchema={"type": "object", "properties": {
                 "role": {"type": "string", "enum": ["user", "assistant"]},
                 "content": {"type": "string"},
                 "session_id": {"type": "string",
                     "description": "Session identifier — must match across all turns in one session."},
                 "trace_id": {"type": "string",
                     "description": "VERITAS trace ID (VT-YYYYMMDD-xxxxxxxx) from omega_preload_context for cross-system correlation."},
             }, "required": ["role", "content"]}),
        Tool(name="stenographer_get_brief",
             description="Get the live running notes document.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="stenographer_compact_guard",
             description="Get compressed briefing + top-k relevant fragments. Call when context window pressure hits.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"},
             }}),
        Tool(name="stenographer_mark_milestone",
             description="Flag a critical decision for tier-A priority.",
             inputSchema={"type": "object", "properties": {
                 "exchange_id": {"type": "integer"},
                 "label": {"type": "string"},
             }, "required": ["exchange_id", "label"]}),
        Tool(name="stenographer_query_history",
             description="FTS5 keyword search over all ingested exchanges.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string"},
                 "limit": {"type": "integer", "default": 10},
             }, "required": ["query"]}),
    ]

    for tool in tools:
        tool.inputSchema['properties']['session_id']={'type':'string','minLength':1}
        if tool.name!='stenographer_query_history':tool.inputSchema.setdefault('required',[]).append('session_id')
        if tool.name=='stenographer_query_history':tool.inputSchema['properties']['cross_session']={'type':'boolean','default':False}
        tool.description=tool.description.replace('tier-A','priority').replace('top-k relevant fragments','task-scoped relevant fragments')
    tools.append(Tool(name='stenographer_capture_status',description='Report automatic capture progress and delivery errors.',inputSchema={'type':'object','properties':{}}))
    return tools

@server.list_resources()
async def list_resources():
    return [
        Resource(uri="omega-stenographer://session/notes",
                 name="Running Notes",
                 description="Live running notes document from the current session",
                 mimeType="text/markdown"),
        Resource(uri="omega-stenographer://session/guard",
                 name="Compaction Guard",
                 description="Auto-compressed briefing + relevant RAG fragments",
                 mimeType="text/markdown"),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    conn = get_db()
    try:
    
        if name == "stenographer_ingest_exchange":
            role       = arguments["role"]
            if role not in ("user","assistant","system"):raise ValueError("Invalid role")
            content    = arguments["content"]
            session_id = arguments.get("session_id")
            if not session_id:raise ValueError("session_id is required")
            trace_id   = arguments.get("trace_id", "")
            # The local transcript observer supplies a stable source key. Commit
            # its receipt in the same transaction as the exchange and FTS row.
            source_key = arguments.get("source_key")
            if source_key:
                conn.execute("CREATE TABLE IF NOT EXISTS capture_receipts (source_key TEXT PRIMARY KEY, captured_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                conn.execute("BEGIN IMMEDIATE")
                inserted = conn.execute("INSERT OR IGNORE INTO capture_receipts(source_key) VALUES (?)", (source_key,))
                if not inserted.rowcount:
                    conn.rollback()
                    return [TextContent(type="text", text="Already captured source exchange")]

            # ── Gap #4: propagate trace_id; generate if absent ──────
            if not trace_id and HAS_BRIDGE:
                trace_id = _bridge.get_or_create_trace(session_id)

            # ── Gap #9: NAFE scan ────────────────────────────────────
            nafe_result = {"clean": True, "flags": [], "signatures_detected": []}
            if HAS_BRIDGE:
                nafe_result = _bridge.nafe_scan(content)
            else:
                # Minimal local NAFE fallback (no bridge)
                nafe_keywords = ["in the spirit of", "outweighs the rule",
                                 "trust me", "they probably mean", "moral obligation"]
                nafe_hits = [kw for kw in nafe_keywords if kw in content.lower()]
                if nafe_hits:
                    nafe_result = {"clean": False,
                                   "flags": [{"signature": "NARRATIVE_RESCUE", "matches": nafe_hits}],
                                   "signatures_detected": ["NARRATIVE_RESCUE"]}

            decisions = extract_decisions(content)
            blockers  = extract_blockers(content)

            # NAFE flags → promote to tier-A + extend blockers
            tier = "B"
            nafe_flags_json = None
            if not nafe_result["clean"]:
                tier = "B"
                nafe_flags_json = json.dumps(nafe_result["flags"])
                for sig in nafe_result["signatures_detected"]:
                    blockers.append(f"NAFE:{sig}")

            # ── Gap #6: check shared events for TERMINAL_SHUTDOWN ───
            shutdown_note = ""
            if HAS_BRIDGE:
                shutdowns = _bridge.get_recent_terminal_shutdowns(limit=1,task_id=session_id)
                if shutdowns:
                    sd = shutdowns[0]
                    # Check if we already ingested this shutdown
                    already = conn.execute(
                        "SELECT id FROM exchanges WHERE session_id=? AND content LIKE ? LIMIT 1",
                        (session_id,f"%CLAEG:TERMINAL_SHUTDOWN%{sd.get('timestamp','')[:16]}%")
                    ).fetchone()
                    if not already:
                        sd_content = (f"CLAEG:TERMINAL_SHUTDOWN — Auto-detected from shared event bus. "
                                      f"Source: {sd.get('source','unknown')} | "
                                      f"Payload: {json.dumps(sd.get('payload',{}))[:200]} | "
                                      f"Timestamp: {sd.get('timestamp','')}")
                        sd_blockers = ["CLAEG:TERMINAL_SHUTDOWN"]
                        sd_cur = conn.execute(
                            "INSERT INTO exchanges "
                            "(role, content, decisions, blockers, tier, milestone, session_id, trace_id) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            ("assistant", sd_content, json.dumps([]),
                             json.dumps(sd_blockers), "B", "TERMINAL_SHUTDOWN",
                             session_id, trace_id)
                        )
                        sd_id = sd_cur.lastrowid
                        conn.execute(
                            "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
                            (sd_id, sd_content, json.dumps([]), json.dumps(sd_blockers))
                        )
                        shutdown_note = " | ⚠ TERMINAL_SHUTDOWN auto-ingested from bridge"

            # ── Write the actual exchange ────────────────────────────
            ex_cur = conn.execute(
                "INSERT INTO exchanges "
                "(role, content, decisions, blockers, tier, session_id, trace_id, nafe_flags) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (role, content, json.dumps(decisions), json.dumps(blockers),
                 tier, session_id, trace_id, nafe_flags_json)
            )
            ex_id = ex_cur.lastrowid

            conn.execute(
                "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
                (ex_id, content, json.dumps(decisions), json.dumps(blockers))
            )
            conn.execute('CREATE TABLE IF NOT EXISTS capture_outbox(id TEXT PRIMARY KEY,task_id TEXT,payload TEXT,delivered INTEGER DEFAULT 0)')
            conn.execute('INSERT OR IGNORE INTO capture_outbox(id,task_id,payload) VALUES(?,?,?)',(f'steno:{ex_id}',session_id,json.dumps({'exchange_id':ex_id,'role':role,'content':content,'decisions':decisions,'blockers':blockers})))
            conn.commit()

            # ── Gap #12: session-aware compression ──────────────────
            unprocessed = conn.execute(
                "SELECT COUNT(*) FROM exchanges WHERE compressed=0 AND session_id=?",
                (session_id,)
            ).fetchone()[0]
            compress_note = ""
            if unprocessed >= STENO_TURN_LIMIT:
                brief = compress_unprocessed(conn, current_session_id=session_id)
                if brief:
                    compress_note = (f" | Compressed {brief['turn_count']} turns "
                                     f"→ brief {brief['brief_id']} (tier-{brief['tier']})")

            decision_str = f"; decisions: {len(decisions)}" if decisions else ""
            blocker_str  = f"; blockers: {len(blockers)}" if blockers else ""
            nafe_str     = f"; ⚠ NAFE:{','.join(nafe_result['signatures_detected'])}" \
                           if not nafe_result["clean"] else ""
            trace_str    = f"; trace:{trace_id[:16]}" if trace_id else ""

            response = [TextContent(type="text", text=(
                f"Ingested [{role}] #{ex_id} ({len(content)} chars"
                f"{decision_str}{blocker_str}{nafe_str}{trace_str})"
                f"{compress_note}{shutdown_note}"
            ))]
            return response
    
        elif name in ('stenographer_get_brief','stenographer_compact_guard'):
            sid=arguments.get('session_id')
            if not sid:raise ValueError('session_id required; global context must be requested explicitly through history search')
            recent=conn.execute('SELECT id,role,content,decisions,blockers,milestone FROM exchanges WHERE session_id=? AND compressed=0 ORDER BY id DESC LIMIT 20',(sid,)).fetchall()
            query=arguments.get('query','')
            terms=runtime.tokens(query)[:20]
            if terms:
                match=' OR '.join('"'+t+'"' for t in terms)
                briefs=conn.execute('SELECT b.id,b.summary,b.source_turns FROM briefs b JOIN briefs_fts f ON f.rowid=b.id WHERE briefs_fts MATCH ? AND b.session_id=? ORDER BY bm25(briefs_fts) LIMIT 20',(match,sid)).fetchall()
            else:
                briefs=conn.execute('SELECT id,summary,source_turns FROM briefs WHERE session_id=? ORDER BY id DESC LIMIT 10',(sid,)).fetchall()
            milestones=conn.execute('SELECT id,milestone,content FROM exchanges WHERE session_id=? AND milestone IS NOT NULL ORDER BY id DESC LIMIT 50',(sid,)).fetchall()
            return [TextContent(type='text',text=json.dumps({'session_id':sid,'milestones':[dict(r) for r in milestones],'recent':[dict(r) for r in recent],'briefs':[dict(r) for r in briefs],'provenance':'Source exchanges retained in full; extraction is heuristic'},ensure_ascii=False))]

        elif name == "stenographer_mark_milestone":
            ex_id = arguments["exchange_id"]
            label = arguments["label"]
            sid=arguments.get('session_id')
            if not sid:raise ValueError('session_id required')
            changed=conn.execute('UPDATE exchanges SET milestone=? WHERE id=? AND session_id=?',(label,ex_id,sid))
            if not changed.rowcount:raise ValueError('Exchange does not exist in the specified session')
            conn.commit()
            response = [TextContent(type="text", text=f"Milestone '{label}' set on exchange #{ex_id}")]
            return response
    
        elif name == 'stenographer_query_history':
            sid=arguments.get('session_id');cross=arguments.get('cross_session',False)
            if not sid and not cross:raise ValueError('session_id required or explicit cross_session=true')
            terms=runtime.tokens(arguments.get('query',''))[:20]
            if not terms:return [TextContent(type='text',text='[]')]
            match=' AND '.join('"'+t+'"' for t in terms)
            scope='' if cross else ' AND e.session_id=?'
            params=[match]+([] if cross else [sid])+[max(1,min(arguments.get('limit',10),50))]
            rows=conn.execute('SELECT e.id,e.session_id,e.role,e.content,e.decisions,e.blockers FROM exchanges e JOIN exchanges_fts f ON e.id=f.rowid WHERE exchanges_fts MATCH ?'+scope+' ORDER BY bm25(exchanges_fts) LIMIT ?',params).fetchall()
            return [TextContent(type='text',text=json.dumps([dict(r) for r in rows],ensure_ascii=False))]
        elif name=='stenographer_capture_status':
            path=STENO_DIR/'capture-state.json';status=json.loads(path.read_text()) if path.exists() else {'last_error':'capture never ran'}
            status.pop('files',None)
            status['outbox_pending']=conn.execute('SELECT COUNT(*) FROM capture_outbox WHERE delivered=0').fetchone()[0] if conn.execute("SELECT 1 FROM sqlite_master WHERE name='capture_outbox'").fetchone() else 0
            return [TextContent(type='text',text=json.dumps(status))]
        else:raise ValueError('Unknown tool')

    finally:
        conn.close()
@server.read_resource()
async def read_resource(uri):
    from urllib.parse import urlparse,parse_qs
    parsed=urlparse(str(uri));sid=parse_qs(parsed.query).get('session_id',[None])[0]
    if not sid:return json.dumps({'status':'SCOPE_REQUIRED','instruction':'Use the notes or guard tool with session_id.'})
    tool='stenographer_compact_guard' if parsed.path.endswith('/guard') else 'stenographer_get_brief'
    return (await call_tool(tool,{'session_id':sid}))[0].text

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
