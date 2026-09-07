"""Observe completed visible Codex messages; never read tools or reasoning into Steno."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
if os.name=='nt':
    import msvcrt
else:
    import fcntl
import omega_stenographer_mcp as steno
import omega_runtime as runtime
from contextlib import closing

STATE = steno.STENO_DIR / 'capture-state.json'
ROOT = Path(os.environ.get('OMEGA_CODEX_SESSIONS', str(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'sessions')))
SINCE = os.environ.get('OMEGA_CAPTURE_SINCE', '2026-09-07')

def visible(record):
    p = record.get('payload', {})
    if record.get('type') != 'response_item' or p.get('type') != 'message':
        return None
    if p.get('role') not in ('user', 'assistant'):
        return None
    phase = p.get('channel') or p.get('phase')
    if p.get('role') == 'assistant' and phase not in ('final', 'final_answer', 'commentary'):
        return None
    chunks = p.get('content', [])
    content = '\n'.join(c.get('text', '') for c in chunks if c.get('type') in ('text', 'input_text', 'output_text'))
    # Environment/config messages are not user-authored conversation.
    if content.lstrip().startswith(('<environment_context>', '<permissions instructions>', '<recommended_plugins>', '# AGENTS.md instructions')):
        return None
    return (p['role'], content) if content.strip() else None

async def scan(state):
    cursors = state.setdefault('files', {})
    # SQLite is the recovery authority; the JSON page is only a health/cache file.
    # This prevents a newer JSON offset from skipping exchanges in an older DB snapshot.
    with closing(steno.get_db()) as db:
        db.execute('CREATE TABLE IF NOT EXISTS capture_cursors(path TEXT PRIMARY KEY,offset INTEGER NOT NULL)')
        persisted=dict(db.execute('SELECT path,offset FROM capture_cursors').fetchall())
    added = 0
    for path in ROOT.rglob('*.jsonl'):
        key = str(path)
        # Old imported sessions stay available in their original archive.
        if path.name[8:18] < SINCE and key not in cursors and key not in persisted:
            cursors[key] = path.stat().st_size
            with closing(steno.get_db()) as db:
                db.execute('INSERT OR REPLACE INTO capture_cursors VALUES(?,?)',(key,cursors[key]));db.commit()
            continue
        offset = persisted.get(key,cursors.get(key,0))
        if path.stat().st_size < offset:
            offset = 0
        sid = path.stem[-36:]
        with path.open('rb') as stream:
            stream.seek(offset)
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw or not raw.endswith(b'\n'):
                    break
                try:
                    record = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise ValueError(f'Invalid complete transcript record: {path.name}:{start}')
                message = visible(record)
                if message:
                    role, content = message
                    source_key = hashlib.sha256((sid + ':' + str(start) + ':').encode() + raw).hexdigest()
                    await steno.call_tool('stenographer_ingest_exchange', dict(role=role, content=content, session_id=sid, source_key=source_key))
                    added += 1
                cursors[key] = stream.tell()
            if cursors.get(key,offset)!=persisted.get(key):
                with closing(steno.get_db()) as db:
                    db.execute('INSERT OR REPLACE INTO capture_cursors VALUES(?,?)',(key,cursors.get(key,offset)));db.commit()
    state.update(last_success=datetime.now(timezone.utc).isoformat(), last_error=None, last_scanned_messages=added)
    await deliver_events(state)
    return added

async def deliver_events(state):
    with closing(steno.get_db()) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='capture_outbox'").fetchone():
            for row in db.execute('SELECT * FROM capture_outbox WHERE delivered=0 ORDER BY rowid LIMIT 100').fetchall():
                runtime.event(row['task_id'],'STENO_EXCHANGE',json.loads(row['payload']),row['id'])
                db.execute('UPDATE capture_outbox SET delivered=1 WHERE id=?',(row['id'],));db.commit()
    brain=Path(os.environ.get('OMEGA_BRAIN_DATA_DIR',str(Path.home()/'.omega-brain')))/'omega_brain.db'
    if not brain.exists():
        state['delivery_status']='waiting for Brain database';return
    delivered=0
    for event in runtime.pending('brain-v2'):
        payload=json.loads(event['payload'])
        # Observations are not promoted to verified evidence by an automatic feed.
        runtime.ingest(brain,runtime.canonical({'event_type':event['event_type'],'source_event':event['id'],'payload':payload}),'event:'+event['id'],'C',event['task_id'])
        runtime.acknowledge('brain-v2',event['id']);delivered+=1
    state.update(delivery_status='running',last_delivered_events=delivered,pending_events=len(runtime.pending('brain-v2')))

def reconcile_delivery():
    """Repair independently timed DB snapshots by replaying missing event copies."""
    with closing(runtime.bus()) as bus:
        present={r[0] for r in bus.execute('SELECT id FROM events')}
        brain=Path(os.environ.get('OMEGA_BRAIN_DATA_DIR',str(Path.home()/'.omega-brain')))/'omega_brain.db'
        if brain.exists():
            with closing(runtime.connect(brain)) as db:
                sources={r[0][6:] for r in db.execute("SELECT source FROM fragments WHERE source LIKE 'event:%'")}
            for eid in present-sources:bus.execute("DELETE FROM receipts WHERE consumer='brain-v2' AND event_id=?",(eid,))
    with closing(steno.get_db()) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='capture_outbox'").fetchone():
            rows=db.execute('SELECT id FROM capture_outbox WHERE delivered=1').fetchall()
            db.executemany('UPDATE capture_outbox SET delivered=0 WHERE id=?',[(r[0],) for r in rows if r[0] not in present]);db.commit()

def save(state):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
    temporary.replace(STATE)

async def observe(once=False):
    # One observer across all Codex task processes. OS releases the lock on exit.
    lock = (steno.STENO_DIR / 'capture.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'0'); lock.flush()
    acquired = False
    try:
        while not acquired:
            try:
                lock.seek(0)
                if os.name=='nt':msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if once:return
                await asyncio.sleep(5)
        state = json.loads(STATE.read_text()) if STATE.exists() else {'files': {}}
        reconcile_delivery()
        while True:
            try:
                await scan(state)
            except Exception as exc:
                state['last_error'] = f'{type(exc).__name__}: {exc}'
            save(state)
            if once:return
            await asyncio.sleep(5)
    finally:
        if acquired:
            lock.seek(0)
            if os.name=='nt':msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
        lock.close()

async def main():
    worker = asyncio.create_task(observe())
    try:
        await steno.main()
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

if __name__ == '__main__':
    import sys
    asyncio.run(observe(once='--once' in sys.argv) if '--once' in sys.argv or '--watch' in sys.argv else main())
