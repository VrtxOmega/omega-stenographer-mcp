#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
veritas_bridge.py — Cross-system integration bridge for the VERITAS Sovereign MCP Ecosystem.
v1.0.0 — Cohesion Layer

Provides shared utilities for Omega Brain MCP, SSWP MCP, and Omega Stenographer MCP:

  TRACE MANAGEMENT
    generate_trace_id()       → VT-{date}-{uuid8} session correlation ID
    get_trace()               → Read current trace state from shared file
    set_trace()               → Write trace state (trace_id, CLAEG state)
    get_or_create_trace()     → Get existing or generate new trace ID

  CROSS-SYSTEM EVENT BUS
    emit_event()              → Append entry to ~/.veritas-shared/events.jsonl
    read_events()             → Read recent events (filterable by type)

  CROSS-DB READERS (read-only, no write access to sibling DBs)
    read_sswp_health()        → Fleet health from SSWP SQLite registry
    read_steno_brief()        → Recent briefs & milestones from Stenographer DB

  NAFE DETECTION (shared with Stenographer since it cannot import veritas_build_gates)
    nafe_scan()               → Scan text for NAFE failure signatures

  EMBEDDING (shared TF-IDF — keeps dim/tokenizer in sync across servers)
    tokenize()
    tfidf_embed()

Shared directory: ~/.veritas-shared/  (override: VERITAS_SHARED_DIR env var)
  trace.json        — Current trace ID + CLAEG state
  events.jsonl      — Append-only cross-system event log (one JSON object per line)
"""

import json
import sys

import omega_runtime as runtime
from contextlib import closing
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Shared directory ───────────────────────────────────────────────────────────
SHARED_DIR = Path(os.environ.get("VERITAS_SHARED_DIR", str(Path.home() / ".veritas-shared")))
SHARED_DIR.mkdir(parents=True, exist_ok=True)

TRACE_FILE  = SHARED_DIR / "trace.json"
EVENTS_FILE = SHARED_DIR / "events.jsonl"

# ── Known DB paths (configurable via env) ────────────────────────────────────
SSWP_DB_PATH  = Path(os.environ.get("SSWP_DB",
    str(Path.home() / ".sswp_registry.sqlite")))
STENO_DB_PATH = Path(os.environ.get("OMEGA_STENOGRAPHER_DIR",
    str(Path.home() / ".omega-stenographer"))) / "steno.db"

# ══════════════════════════════════════════════════════════════════════════════
# TRACE ID MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def generate_trace_id() -> str:
    """Generate a new VT-{YYYYMMDD}-{uuid8} correlation ID."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:8]
    return f"VT-{date_str}-{uid}"

def get_trace(task_id=None):
    return runtime.trace(task_id) if task_id else {}

def set_trace(trace_id,claeg_state='STABLE_CONTINUATION',extra=None,task_id=None):
    task_id=task_id or (extra or {}).get('task_id')
    if not task_id:raise ValueError('task_id required for trace mutation')
    value=dict(extra or {},trace_id=trace_id,claeg_state=claeg_state,task_id=task_id,updated_at=datetime.now(timezone.utc).isoformat())
    with closing(runtime.bus()) as db:db.execute('INSERT OR REPLACE INTO traces VALUES(?,?)',(task_id,runtime.canonical(value)))
    return value

def get_or_create_trace(task_id=None):
    return runtime.trace(task_id)['trace_id'] if task_id else ''

def update_claeg_state(claeg_state,task_id=None):
    if not task_id: return {'updated':False,'reason':'task_id required'}
    t=runtime.trace(task_id)
    return set_trace(t['trace_id'],claeg_state,task_id=task_id)

# ══════════════════════════════════════════════════════════════════════════════
# CROSS-SYSTEM EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

def emit_event(event_type,payload,source='unknown',task_id=None):
    return runtime.event(task_id or payload.get('task_id') or 'system',event_type,dict(payload,source=source))

def read_events(limit=20,event_type=None,source=None,task_id=None):
    if not task_id:return []
    with closing(runtime.bus()) as db:
        rows=db.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at DESC LIMIT ?',(task_id,max(1,min(limit,100)))).fetchall()
    result=[]
    for r in rows:
        payload=json.loads(r['payload'])
        if event_type and r['event_type']!=event_type:continue
        if source and payload.get('source')!=source:continue
        result.append(dict(r,payload=payload,timestamp=r['created_at']))
    return result

def get_recent_terminal_shutdowns(limit=3,task_id=None):
    return read_events(limit,'CLAEG_TERMINAL_SHUTDOWN',task_id=task_id)

# ══════════════════════════════════════════════════════════════════════════════
# SSWP REGISTRY READER  (read-only)
# ══════════════════════════════════════════════════════════════════════════════

def read_sswp_health(limit=5):
    if not SSWP_DB_PATH.exists():return {'available':False}
    with closing(sqlite3.connect(SSWP_DB_PATH.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute('WITH ranked AS (SELECT a.*,ROW_NUMBER() OVER(PARTITION BY node_id ORDER BY run_at DESC,attestation_id DESC) rn FROM attestations a) SELECT n.name,n.repo_path,r.overall_status,r.run_at,r.adversarial_risk FROM nodes n LEFT JOIN ranked r ON r.node_id=n.node_id AND r.rn=1').fetchall()
        history=db.execute('SELECT COUNT(*) FROM attestations').fetchone()[0]
    result=[dict(r,local_path_exists=Path(r['repo_path']).exists(),evidence_scope='historical; verify freshness before reuse') for r in rows]
    return {'available':True,'nodes_total':len(rows),'history_runs':history,'latest_per_node':True,'passing_nodes':sum(r['overall_status']=='PASS' for r in rows),'nodes':result[:limit]}

# ══════════════════════════════════════════════════════════════════════════════
# STENOGRAPHER BRIEF READER  (read-only)
# ══════════════════════════════════════════════════════════════════════════════

def read_steno_brief(limit=5,session_id=None,task_id=None):
    scope=task_id or session_id
    if not STENO_DB_PATH.exists():return {'available':False}
    with closing(sqlite3.connect(STENO_DB_PATH.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        if not scope:return {'available':True,'scope_required':True,'exchanges':db.execute('SELECT COUNT(*) FROM exchanges').fetchone()[0]}
        rows=db.execute('SELECT id,summary,tier,created_at,source_turns FROM briefs WHERE session_id=? ORDER BY id DESC LIMIT ?',(scope,limit)).fetchall()
        uncompressed=db.execute('SELECT COUNT(*) FROM exchanges WHERE session_id=? AND compressed=0',(scope,)).fetchone()[0]
    return {'available':True,'task_id':scope,'recent_briefs':[dict(r) for r in rows],'uncompressed_turns':uncompressed}

# ══════════════════════════════════════════════════════════════════════════════
# NAFE FAILURE SIGNATURE SCANNER
# Shared implementation — Stenographer imports this since it cannot import
# veritas_build_gates (different venv). Omega Brain uses its own CLAEG.check_narrative_injection.
# ══════════════════════════════════════════════════════════════════════════════

NAFE_PATTERNS: dict = {
    "NARRATIVE_RESCUE": [
        r'\b(?:actually|truly|really|essentially|fundamentally|ultimately)\b.{0,60}'
        r'\b(?:good|right|safe|fine|okay|valid|acceptable|permissible)\b',
        r'\b(?:in the spirit of|in the interest of|for the greater good|'
        r'in the context of|given the circumstances)\b',
        r'\b(?:context suggests|context implies|context shows|context indicates)\b',
    ],
    "MORAL_OVERRIDE": [
        r'\b(?:ethically|morally|ought to|should really|have a duty|'
        r'higher purpose|moral imperative|ethical obligation)\b',
        r'\b(?:the right thing to do|what\'s right|moral obligation|ethical imperative)\b',
        r'\b(?:outweighs the|overrides the|supersedes the)\b.{0,40}'
        r'\b(?:rule|constraint|gate|policy|requirement|protocol|procedure)\b',
    ],
    "AUTHORITY_DRIFT": [
        r'\b(?:the user said|user wants|user asked|user requested|human said|'
        r'operator confirmed)\b.{0,50}\b(?:so we should|so we can|therefore we|thus we)\b',
        r'\b(?:trust me|I know|I\'m sure|I\'m certain|I guarantee|I assure)\b',
        r'\b(?:senior|expert|authority|official|management|leadership)\b.{0,40}'
        r'\b(?:says|confirms|approves|authorizes|has approved)\b',
    ],
    "INTENT_INFERENCE": [
        r'\b(?:they probably mean|they likely want|they obviously|'
        r'clearly they|must mean|they must want)\b',
        r'\b(?:implied|implicit|obviously intended|surely means|can infer|'
        r'safe to assume|reasonable to assume)\b',
        r'\b(?:reading between the lines|spirit of the request|'
        r'what they really mean|intent is clearly)\b',
    ],
}

def nafe_scan(text: str) -> dict:
    """
    Scan text for NAFE (Narrative Alignment Failure Engine) failure signatures.
    Returns: {clean, flags, flag_count, signatures_detected}
    """
    if not text:
        return {"clean": True, "flags": [], "flag_count": 0, "signatures_detected": []}

    flags = []
    text_lower = text.lower()
    for signature, patterns in NAFE_PATTERNS.items():
        for pat in patterns:
            try:
                matches = re.findall(pat, text_lower, re.IGNORECASE)
            except re.error:
                continue
            if matches:
                flags.append({
                    "signature": signature,
                    "matches": [str(m)[:100] for m in matches[:2]],
                })
                break  # one flag per signature type is sufficient

    return {
        "clean": len(flags) == 0,
        "flags": flags,
        "flag_count": len(flags),
        "signatures_detected": list({f["signature"] for f in flags}),
    }

# ══════════════════════════════════════════════════════════════════════════════
# SHARED TF-IDF EMBEDDING
# Single canonical implementation — both Python servers import from here
# so dim/tokenizer never drift between Omega Brain fallback and Stenographer.
# ══════════════════════════════════════════════════════════════════════════════

TFIDF_DIM = 128  # single source of truth for embedding dimension

def tokenize(text: str) -> list:
    return re.findall(r'[a-zA-Z]{3,}', text.lower())

def tfidf_embed(text,dim=512):
    return runtime.embed(text)

def cosine_sim(a,b):
    return runtime.cosine(a,b)

# ══════════════════════════════════════════════════════════════════════════════
# ECOSYSTEM STATUS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def ecosystem_summary(task_id=None):
    capture_path=STENO_DB_PATH.parent/'capture-state.json'
    capture=json.loads(capture_path.read_text()) if capture_path.exists() else {'last_error':'capture has not run'}
    capture.pop('files',None)
    return {'shared_trace':get_trace(task_id),'sswp':read_sswp_health(),'stenographer':read_steno_brief(task_id=task_id),'capture':capture,'pending_brain_events':len(runtime.pending('brain-v2')),'recent_events':read_events(task_id=task_id),'generated_at':datetime.now(timezone.utc).isoformat()}
