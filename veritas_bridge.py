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

def get_trace() -> dict:
    """Read current trace state from shared file. Returns {} if not found."""
    if TRACE_FILE.exists():
        try:
            return json.loads(TRACE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def set_trace(trace_id: str, claeg_state: str = "STABLE_CONTINUATION",
              extra: dict = None) -> dict:
    """Write trace state to shared file. Returns the written record."""
    record = {
        "trace_id": trace_id,
        "claeg_state": claeg_state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }
    TRACE_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record

def get_or_create_trace() -> str:
    """Return existing trace ID or generate + persist a new one."""
    t = get_trace()
    if t.get("trace_id"):
        return t["trace_id"]
    tid = generate_trace_id()
    set_trace(tid)
    return tid

def update_claeg_state(claeg_state: str) -> dict:
    """Update only the CLAEG state in the current trace record."""
    t = get_trace()
    tid = t.get("trace_id") or generate_trace_id()
    return set_trace(tid, claeg_state=claeg_state, extra={
        k: v for k, v in t.items()
        if k not in ("trace_id", "claeg_state", "updated_at")
    })

# ══════════════════════════════════════════════════════════════════════════════
# CROSS-SYSTEM EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

def emit_event(event_type: str, payload: dict, source: str = "unknown") -> None:
    """Append a structured event to the shared JSONL event bus. Non-fatal on error."""
    try:
        entry = {
            "trace_id": get_or_create_trace(),
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass  # Event bus failure is always non-fatal

def read_events(limit: int = 20, event_type: str = None,
                since_trace_id: str = None) -> list:
    """
    Read recent events from the shared event bus, newest first.
    Optionally filter by event_type.
    """
    if not EVENTS_FILE.exists():
        return []
    try:
        lines = EVENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        return []
    events = []
    for line in reversed(lines):
        try:
            e = json.loads(line)
            if event_type and e.get("event_type") != event_type:
                continue
            events.append(e)
            if len(events) >= limit:
                break
        except Exception:
            pass
    return events

def get_recent_terminal_shutdowns(limit: int = 3) -> list:
    """Return recent CLAEG_TERMINAL_SHUTDOWN events for Stenographer to ingest."""
    return read_events(limit=limit, event_type="CLAEG_TERMINAL_SHUTDOWN")

# ══════════════════════════════════════════════════════════════════════════════
# SSWP REGISTRY READER  (read-only)
# ══════════════════════════════════════════════════════════════════════════════

def read_sswp_health(limit: int = 5) -> dict:
    """
    Read SSWP fleet health from the registry SQLite.
    Returns a summary dict compatible with omega_write_handoff and omega_ecosystem_status.
    """
    if not SSWP_DB_PATH.exists():
        return {"available": False, "reason": f"SSWP registry not found at {SSWP_DB_PATH}"}
    try:
        conn = sqlite3.connect(str(SSWP_DB_PATH))
        conn.row_factory = sqlite3.Row
        # Use the v_node_health view
        total = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        rows  = conn.execute("""
            SELECT name, overall_status, adversarial_risk, risk_score, run_at
            FROM attestations a
            JOIN nodes n USING(node_id)
            ORDER BY run_at DESC LIMIT 200
        """).fetchall()

        passing    = sum(1 for r in rows if r["overall_status"] == "PASS")
        failing    = sum(1 for r in rows if r["overall_status"] in ("FAIL", "PARTIAL"))
        at_risk    = [dict(r) for r in rows
                      if r["adversarial_risk"] and float(r["adversarial_risk"]) > 0.1]
        last_run   = rows[0]["run_at"] if rows else None
        pass_rate  = f"{(passing / len(rows) * 100):.1f}%" if rows else "N/A"

        top_risk = sorted(at_risk, key=lambda x: float(x.get("adversarial_risk") or 0),
                          reverse=True)[:limit]
        # Sanitize for JSON
        top_risk_clean = [{
            "name": r["name"],
            "status": r["overall_status"],
            "adversarial_risk_pct": f"{float(r['adversarial_risk'] or 0)*100:.1f}%",
            "risk_score_pct": f"{float(r['risk_score'] or 0)*100:.1f}%",
            "last_run": r["run_at"],
        } for r in top_risk]

        conn.close()
        return {
            "available": True,
            "nodes_total": total,
            "attested_count": len(rows),
            "passing": passing,
            "failing": failing,
            "pass_rate": pass_rate,
            "at_risk_count": len(at_risk),
            "last_witness": last_run,
            "top_risk_nodes": top_risk_clean,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
# STENOGRAPHER BRIEF READER  (read-only)
# ══════════════════════════════════════════════════════════════════════════════

def read_steno_brief(limit: int = 5, session_id: str = None) -> dict:
    """
    Read recent Stenographer briefs and milestones from steno.db.
    Returns a dict compatible with omega_preload_context.
    """
    if not STENO_DB_PATH.exists():
        return {"available": False, "reason": f"Stenographer DB not found at {STENO_DB_PATH}"}
    try:
        conn = sqlite3.connect(str(STENO_DB_PATH))
        conn.row_factory = sqlite3.Row

        # Tier-A briefs first, then recent
        briefs = conn.execute("""
            SELECT id, summary, tier, created_at FROM briefs
            ORDER BY CASE tier WHEN 'A' THEN 0 ELSE 1 END, id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        # Recent milestones
        milestones = conn.execute("""
            SELECT id, milestone, decisions, created_at FROM exchanges
            WHERE milestone IS NOT NULL ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()

        # Uncompressed count
        uncompressed = conn.execute(
            "SELECT COUNT(*) FROM exchanges WHERE compressed=0"
        ).fetchone()[0]

        conn.close()

        return {
            "available": True,
            "recent_briefs": [{
                "id": b["id"], "summary": b["summary"][:250],
                "tier": b["tier"], "created_at": b["created_at"],
            } for b in briefs],
            "milestones": [{
                "id": m["id"],
                "label": m["milestone"],
                "decisions": (json.loads(m["decisions"])
                              if isinstance(m["decisions"], str) else m["decisions"] or []),
                "at": m["created_at"],
            } for m in milestones],
            "uncompressed_turns": uncompressed,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}

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

def tfidf_embed(text: str, dim: int = TFIDF_DIM) -> list:
    tokens = tokenize(text)
    if not tokens:
        return [0.0] * dim
    tf: dict = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    vec = [0.0] * dim
    for t, freq in tf.items():
        vec[abs(hash(t)) % dim] += freq / len(tokens)
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm > 0 else vec

def cosine_sim(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(x * y for x, y in zip(a[:n], b[:n]))
    na  = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb  = math.sqrt(sum(y * y for y in b[:n])) or 1.0
    return max(-1.0, min(1.0, dot / (na * nb)))

# ══════════════════════════════════════════════════════════════════════════════
# ECOSYSTEM STATUS SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def ecosystem_summary() -> dict:
    """
    Return a unified status summary of all three MCP systems.
    Used by omega_ecosystem_status tool in Omega Brain.
    """
    trace = get_trace()
    sswp  = read_sswp_health(limit=3)
    steno = read_steno_brief(limit=3)
    recent_events = read_events(limit=10)

    return {
        "shared_trace": {
            "trace_id": trace.get("trace_id", "UNSET"),
            "claeg_state": trace.get("claeg_state", "UNKNOWN"),
            "last_updated": trace.get("updated_at", "never"),
        },
        "sswp": sswp,
        "stenographer": steno,
        "recent_events": [{
            "event_type": e.get("event_type"),
            "source": e.get("source"),
            "timestamp": e.get("timestamp"),
            "summary": str(e.get("payload", {}))[:120],
        } for e in recent_events],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
