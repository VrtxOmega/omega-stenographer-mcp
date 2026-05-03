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
import os, sys, re, json, sqlite3, hashlib, time, math
from datetime import datetime, timezone
from pathlib import Path
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource

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
    conn = sqlite3.connect(str(DB_PATH))
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

def tfidf_embed(text, dim=128):
    tokens = tokenize(text)
    if not tokens:
        return [0.0] * dim
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    vec = [0.0] * dim
    for t, freq in tf.items():
        h = abs(hash(t)) % dim
        vec[h] += freq / len(tokens)
    norm = math.sqrt(sum(v*v for v in vec))
    if norm > 0:
        vec = [v/norm for v in vec]
    return vec

def cosine_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(y*y for y in b))
    return dot/(na*nb) if na*nb > 0 else 0

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

def compress_unprocessed(conn, current_session_id: str = None):
    """
    Compress unprocessed exchanges into a brief fragment.

    Gap #12 fix: session-aware compression — only batches turns from the
    CURRENT session, preventing cross-session contamination in briefs.
    If current_session_id is None, falls back to all-session behaviour
    (legacy compatibility).
    """
    if current_session_id:
        rows = conn.execute(
            "SELECT id, role, content, decisions FROM exchanges "
            "WHERE compressed=0 AND session_id=? ORDER BY id",
            (current_session_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, role, content, decisions FROM exchanges "
            "WHERE compressed=0 ORDER BY id"
        ).fetchall()

    if len(rows) < STENO_TURN_LIMIT:
        return None

    turn_ids = [r[0] for r in rows]
    combined = " ".join(r[2] for r in rows)
    all_decisions = []
    for r in rows:
        if r[3]:
            all_decisions.extend(json.loads(r[3]) if isinstance(r[3], str) else r[3])

    tier = "A" if all_decisions else "B"
    summary = f"Batch {turn_ids[0]}-{turn_ids[-1]}"
    if current_session_id:
        summary += f" [{current_session_id[:16]}]"
    summary += ": "
    if all_decisions:
        summary += "Decisions: " + "; ".join(all_decisions[:3])
    else:
        summary += combined[:300] + ("..." if len(combined) > 300 else "")

    cur = conn.execute(
        "INSERT INTO briefs (summary, tier, source_turns, session_id) VALUES (?, ?, ?, ?)",
        (summary, tier, json.dumps(turn_ids), current_session_id)
    )
    brief_id = cur.lastrowid

    conn.execute(
        "INSERT INTO briefs_fts(rowid, summary) VALUES (?, ?)",
        (brief_id, summary)
    )
    conn.execute(
        f"UPDATE exchanges SET compressed=1 WHERE id IN ({','.join('?'*len(turn_ids))})",
        turn_ids
    )
    conn.commit()

    return {"brief_id": brief_id, "summary": summary,
            "turn_count": len(turn_ids), "tier": tier}

# ── MCP Server ─────────────────────────────────────────────
server = Server("omega-stenographer")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="stenographer_ingest_exchange",
             description=(
                 "Ingest a conversation turn. Call after every significant user or assistant message. "
                 "Automatically: extracts decisions/blockers via regex, runs NAFE failure-signature "
                 "scan (sets tier-A if NAFE flags detected), checks for cross-system CLAEG "
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
    
    if name == "stenographer_ingest_exchange":
        role       = arguments["role"]
        content    = arguments["content"]
        session_id = arguments.get("session_id", "default")
        trace_id   = arguments.get("trace_id", "")

        # ── Gap #4: propagate trace_id; generate if absent ──────
        if not trace_id and HAS_BRIDGE:
            trace_id = _bridge.get_or_create_trace()

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
            tier = "A"
            nafe_flags_json = json.dumps(nafe_result["flags"])
            for sig in nafe_result["signatures_detected"]:
                blockers.append(f"NAFE:{sig}")

        # ── Gap #6: check shared events for TERMINAL_SHUTDOWN ───
        shutdown_note = ""
        if HAS_BRIDGE:
            shutdowns = _bridge.get_recent_terminal_shutdowns(limit=1)
            if shutdowns:
                sd = shutdowns[0]
                # Check if we already ingested this shutdown
                already = conn.execute(
                    "SELECT id FROM exchanges WHERE content LIKE ? LIMIT 1",
                    (f"%CLAEG:TERMINAL_SHUTDOWN%{sd.get('timestamp','')[:16]}%",)
                ).fetchone()
                if not already:
                    sd_content = (f"CLAEG:TERMINAL_SHUTDOWN — Auto-detected from shared event bus. "
                                  f"Source: {sd.get('source','unknown')} | "
                                  f"Payload: {json.dumps(sd.get('payload',{}))[:200]} | "
                                  f"Timestamp: {sd.get('timestamp','')}")
                    sd_blockers = ["CLAEG:TERMINAL_SHUTDOWN"]
                    conn.execute(
                        "INSERT INTO exchanges "
                        "(role, content, decisions, blockers, tier, milestone, session_id, trace_id) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        ("assistant", sd_content, json.dumps([]),
                         json.dumps(sd_blockers), "A", "TERMINAL_SHUTDOWN",
                         session_id, trace_id)
                    )
                    sd_id = conn.lastrowid
                    conn.execute(
                        "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
                        (sd_id, sd_content[:4000], json.dumps([]), json.dumps(sd_blockers))
                    )
                    shutdown_note = " | ⚠ TERMINAL_SHUTDOWN auto-ingested from bridge"

        # ── Write the actual exchange ────────────────────────────
        conn.execute(
            "INSERT INTO exchanges "
            "(role, content, decisions, blockers, tier, session_id, trace_id, nafe_flags) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (role, content, json.dumps(decisions), json.dumps(blockers),
             tier, session_id, trace_id, nafe_flags_json)
        )
        ex_id = conn.lastrowid

        conn.execute(
            "INSERT INTO exchanges_fts(rowid, content, decisions, blockers) VALUES (?,?,?,?)",
            (ex_id, content[:4000], json.dumps(decisions), json.dumps(blockers))
        )
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

        return [TextContent(type="text", text=(
            f"Ingested [{role}] #{ex_id} ({len(content)} chars"
            f"{decision_str}{blocker_str}{nafe_str}{trace_str})"
            f"{compress_note}{shutdown_note}"
        ))]
    
    elif name == "stenographer_get_brief":
        # Build running notes
        recent = conn.execute(
            "SELECT id, role, content, decisions, blockers, milestone FROM exchanges WHERE compressed=0 ORDER BY id DESC LIMIT 20"
        ).fetchall()
        
        milestones = conn.execute(
            "SELECT id, milestone, decisions FROM exchanges WHERE milestone IS NOT NULL ORDER BY id DESC LIMIT 10"
        ).fetchall()
        
        briefs_recent = conn.execute(
            "SELECT id, summary, tier, created_at FROM briefs ORDER BY id DESC LIMIT 5"
        ).fetchall()
        
        notes = "# Running Session Notes\n\n"
        
        if milestones:
            notes += "## 🔖 Milestones\n"
            for m in milestones:
                decisions = json.loads(m[2]) if m[2] else []
                notes += f"- **{m[1]}** (ex #{m[0]}): {'; '.join(decisions[:2])}\n"
            notes += "\n"
        
        if briefs_recent:
            notes += "## 📦 Compressed Briefs\n"
            for b in briefs_recent:
                notes += f"- [tier-{b[2]}] {b[1][:200]}\n"
            notes += "\n"
        
        notes += "## 📝 Recent Exchanges\n"
        for ex in reversed(recent):
            decisions = json.loads(ex[3]) if ex[3] else []
            blockers = json.loads(ex[4]) if ex[4] else []
            flags = []
            if decisions: flags.append(f"💡 {len(decisions)} decisions")
            if blockers: flags.append(f"🚧 {len(blockers)} blockers")
            flag_str = f" ({'; '.join(flags)})" if flags else ""
            notes += f"### [{ex[0]}] {ex[1].upper()}{flag_str}\n{ex[2][:500]}\n\n"
        
        return [TextContent(type="text", text=notes)]
    
    elif name == "stenographer_compact_guard":
        query = arguments.get("query", "")
        
        # Get recent uncompressed exchanges
        recent = conn.execute(
            "SELECT content, decisions FROM exchanges WHERE compressed=0 ORDER BY id DESC LIMIT 10"
        ).fetchall()
        
        # Search briefs by similarity
        query_vec = tfidf_embed(query)
        briefs = conn.execute("SELECT id, summary, tier FROM briefs ORDER BY id DESC LIMIT 20").fetchall()
        
        ranked = []
        for b in briefs:
            bvec = tfidf_embed(b[1])
            sim = cosine_sim(query_vec, bvec)
            ranked.append((sim, b[0], b[1], b[2]))
        ranked.sort(reverse=True)
        
        result = "# Compaction Guard Briefing\n\n"
        result += f"Query: {query[:200]}\n\n"
        
        if recent:
            result += "## 🔴 Live (Uncompressed)\n"
            for r in recent[:5]:
                decisions = json.loads(r[1]) if r[1] else []
                dec_str = f" [Decisions: {'; '.join(decisions[:2])}]" if decisions else ""
                result += f"- {r[0][:200]}...{dec_str}\n"
            result += "\n"
        
        result += "## 📦 Compressed Briefs (Top-K)\n"
        for sim, bid, summary, tier in ranked[:STENO_TOP_K]:
            result += f"- [{tier}] {bid}: {summary[:250]}\n"

        # ── Gap #5: cross-system events from shared event bus ───
        if HAS_BRIDGE:
            recent_events = _bridge.read_events(limit=5)
            if recent_events:
                result += "\n## 🔗 Cross-System Events (Bridge)\n"
                for ev in recent_events:
                    etype = ev.get("event_type", "UNKNOWN")
                    src   = ev.get("source", "?")
                    ts    = ev.get("timestamp", "")[:16]
                    pay   = str(ev.get("payload", {}))[:120]
                    result += f"- [{ts}] {src}::{etype} — {pay}\n"

        return [TextContent(type="text", text=result)]
    
    elif name == "stenographer_mark_milestone":
        ex_id = arguments["exchange_id"]
        label = arguments["label"]
        conn.execute(
            "UPDATE exchanges SET milestone=?, tier='A' WHERE id=?",
            (label, ex_id)
        )
        conn.commit()
        return [TextContent(type="text", text=f"Milestone '{label}' set on exchange #{ex_id}")]
    
    elif name == "stenographer_query_history":
        query = arguments["query"]
        limit = arguments.get("limit", 10)
        try:
            rows = conn.execute(
                "SELECT content, decisions, id FROM exchanges_fts WHERE exchanges_fts MATCH ? LIMIT ?",
                (query, limit)
            ).fetchall()
        except:
            rows = []
        
        result = f"# Search: '{query}'\n\n"
        for r in rows:
            result += f"### [#{r[2]}] {r[0][:300]}\n"
            if r[1]:
                decisions = json.loads(r[1]) if isinstance(r[1], str) else r[1]
                result += f"Decisions: {'; '.join(decisions[:2])}\n"
            result += "\n"
        
        return [TextContent(type="text", text=result or "No results found.")]

@server.read_resource()
async def read_resource(uri: str):
    if uri == "omega-stenographer://session/notes":
        result = await call_tool("stenographer_get_brief", {})
        return [Resource(uri=uri, mimeType="text/markdown", text=result[0].text)]
    elif uri == "omega-stenographer://session/guard":
        result = await call_tool("stenographer_compact_guard", {"query": ""})
        return [Resource(uri=uri, mimeType="text/markdown", text=result[0].text)]
    return []

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options(
            notification_options=NotificationOptions()
        ))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
