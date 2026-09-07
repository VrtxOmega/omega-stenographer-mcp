"""Versioned local integrity, lexical retrieval and task-scoped coordination."""
import hashlib, hmac, json, math, os, re, secrets, sqlite3, time, uuid
from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing

EMBED_VERSION = 'hash-lexical-v2-512'
SHARED = Path(os.environ.get('VERITAS_SHARED_DIR', str(Path.home()/'.veritas-shared')))

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def connect(path):
    db=sqlite3.connect(str(path), timeout=30, isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA busy_timeout=30000')
    deadline=time.monotonic()+30
    while True:
        try:
            if db.execute('PRAGMA journal_mode').fetchone()[0]!='wal':db.execute('PRAGMA journal_mode=WAL')
            break
        except sqlite3.OperationalError as exc:
            if 'locked' not in str(exc).lower() or time.monotonic()>=deadline:db.close();raise
            time.sleep(0.05)
    return db

def tokens(text):
    return re.findall(r'\w+', text.casefold(), flags=re.UNICODE)[:4000]

def embed(text):
    vec=[0.0]*512
    for word in tokens(text):
        h=hashlib.sha256(word.encode()).digest()
        vec[int.from_bytes(h[:4],'big')%512]+=1.0 if h[4]&1 else -1.0
    norm=math.sqrt(sum(x*x for x in vec))
    return [x/norm for x in vec] if norm else vec

def cosine(a,b):
    if len(a)!=len(b):raise ValueError('Embedding dimension mismatch')
    na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
    return max(-1.0,min(1.0,sum(x*y for x,y in zip(a,b))/(na*nb))) if na and nb else 0.0

def ledger_init(db):
    db.execute('CREATE TABLE IF NOT EXISTS ledger_v2(id INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, event_json TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS integrity_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)')

def ledger_append(path, event_type, payload, task_id='system'):
    with closing(connect(path)) as db:
        ledger_init(db);db.execute('BEGIN IMMEDIATE')
        try:
            if verify_rows(db)['invalid_rows']:raise ValueError('Existing v2 ledger is invalid; append refused')
            if not db.execute('SELECT 1 FROM ledger_v2 LIMIT 1').fetchone():
                legacy=db.execute("SELECT name FROM sqlite_master WHERE name='ledger'").fetchone()
                digest=hashlib.sha256();count=0
                if legacy:
                    for row in db.execute('SELECT * FROM ledger ORDER BY id'):
                        digest.update((canonical(dict(row))+'\n').encode());count+=1
                append_row(db,'LEGACY_BOUNDARY',{'legacy_rows':count,'legacy_logical_sha256':digest.hexdigest(),'legacy_status':'preserved_unverified','format':'v2'},'system')
            value=append_row(db,event_type,payload,task_id)
            db.execute('COMMIT');return value
        except BaseException:
            db.execute('ROLLBACK');raise

def append_row(db,event_type,payload,task_id):
    row=db.execute('SELECT id,hash FROM ledger_v2 ORDER BY id DESC LIMIT 1').fetchone()
    seq=row['id']+1 if row else 1;prev=row['hash'] if row else 'GENESIS_V2'
    event={'version':2,'sequence':seq,'task_id':task_id,'event_type':event_type,'payload':payload,'timestamp':datetime.now(timezone.utc).isoformat()}
    raw=canonical(event);digest=hashlib.sha256((prev+'\n'+raw).encode()).hexdigest()
    db.execute('INSERT INTO ledger_v2 VALUES(?,?,?,?)',(seq,prev,raw,digest));return digest

def ledger_verify(path):
    with closing(connect(path)) as db:
        ledger_init(db);return verify_rows(db)

def verify_rows(db):
    prev='GENESIS_V2';count=0;errors=[]
    for r in db.execute('SELECT * FROM ledger_v2 ORDER BY id'):
        count+=1
        digest=hashlib.sha256((r['prev_hash']+'\n'+r['event_json']).encode()).hexdigest()
        try:
            event=json.loads(r['event_json'])
            structural=event.get('version')==2 and event.get('sequence')==r['id'] and canonical(event)==r['event_json']
        except (ValueError,TypeError):structural=False
        if not structural or r['id']!=count or r['prev_hash']!=prev or digest!=r['hash']:errors.append(r['id'])
        prev=r['hash']
    return {'format':2,'rows':count,'valid':bool(count) and not errors,'invalid_rows':errors,'head':prev,'legacy_status':'preserved_unverified','guarantee':'local tamper-evident chain; no independent external anchor'}

def index_init(db):
    db.execute('CREATE TABLE IF NOT EXISTS fragment_index_v2(id INTEGER PRIMARY KEY, fragment_id TEXT UNIQUE, task_id TEXT NOT NULL DEFAULT \'legacy-global\', supersedes TEXT, metadata TEXT NOT NULL DEFAULT \'{}\')')
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fragment_fts_v2 USING fts5(content,source,tokenize='unicode61')")
    db.execute('CREATE TABLE IF NOT EXISTS runtime_migrations(name TEXT PRIMARY KEY)')
    db.execute('CREATE INDEX IF NOT EXISTS fragment_scope_v2 ON fragment_index_v2(task_id)')
    db.execute('CREATE INDEX IF NOT EXISTS fragment_supersedes_v2 ON fragment_index_v2(supersedes)')
    if not db.execute("SELECT 1 FROM runtime_migrations WHERE name='fragment-index-v2'").fetchone():
        db.execute('BEGIN IMMEDIATE')
        try:
            for r in db.execute('SELECT id,content,source FROM fragments'):
                cur=db.execute('INSERT OR IGNORE INTO fragment_index_v2(fragment_id) VALUES(?)',(r['id'],))
                if cur.rowcount:db.execute('INSERT INTO fragment_fts_v2(rowid,content,source) VALUES(?,?,?)',(cur.lastrowid,r['content'],r['source']))
            db.execute("INSERT OR IGNORE INTO runtime_migrations VALUES('fragment-index-v2')");db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise

def ingest(path,content,source='user',tier='B',task_id='global',supersedes=None,metadata=None):
    if not content.strip():raise ValueError('Empty fragment')
    if tier not in ('A','B','C','D'):raise ValueError('Invalid evidence tier')
    fid=hashlib.sha256((task_id+'\n'+source+'\n'+content).encode()).hexdigest()[:32]
    with closing(connect(path)) as db:
        index_init(db);db.execute('BEGIN IMMEDIATE')
        try:
            if supersedes and not db.execute('SELECT 1 FROM fragment_index_v2 WHERE fragment_id=? AND task_id=?',(supersedes,task_id)).fetchone():raise ValueError('Superseded fragment must exist in same task')
            db.execute('INSERT OR IGNORE INTO fragments(id,content,source,tier,embedding,ingested_at) VALUES(?,?,?,?,?,?)',(fid,content,source,tier,'[]',datetime.now(timezone.utc).isoformat()))
            meta=dict(metadata or {},embedding_version=EMBED_VERSION,dimension=512,evidence_tier_meaning='caller-provided, not independently verified')
            cur=db.execute('INSERT OR IGNORE INTO fragment_index_v2(fragment_id,task_id,supersedes,metadata) VALUES(?,?,?,?)',(fid,task_id,supersedes,canonical(meta)))
            if cur.rowcount:db.execute('INSERT INTO fragment_fts_v2(rowid,content,source) VALUES(?,?,?)',(cur.lastrowid,content,source))
            db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
    return fid

def search(path,query,top_k=5,task_id=None,cross_task=False):
    terms=tokens(query)[:20];top_k=max(1,min(int(top_k),50))
    if not task_id and not cross_task:raise ValueError('task_id required; use cross_task=true for explicit global search')
    if not terms:return {'fragments':[],'query':query,'score_kind':'lexical_similarity_not_confidence'}
    match=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
    with closing(connect(path)) as db:
        index_init(db)
        scope='' if cross_task else " AND i.task_id IN (?, 'global')"
        args=[match]+([] if cross_task else [task_id])
        rows=db.execute('SELECT f.*,i.task_id,i.metadata FROM fragment_fts_v2 ft JOIN fragment_index_v2 i ON i.id=ft.rowid JOIN fragments f ON f.id=i.fragment_id WHERE fragment_fts_v2 MATCH ?'+scope+' AND NOT EXISTS(SELECT 1 FROM fragment_index_v2 newer WHERE newer.supersedes=i.fragment_id) ORDER BY bm25(fragment_fts_v2) LIMIT 256',args).fetchall()
    q=embed(query);result=[]
    for r in rows:
        score=cosine(q,embed(r['content']))
        if score<=0:continue
        result.append({'id':r['id'],'content':r['content'][:2000],'has_more':len(r['content'])>2000,'source':r['source'],'tier':r['tier'],'task_id':r['task_id'],'metadata':json.loads(r['metadata']),'score':round(score,4),'score_kind':'lexical_similarity_not_confidence'})
    result.sort(key=lambda r:r['score'],reverse=True)
    return {'query':query,'fragments':result[:top_k],'candidates_scored':len(rows),'embedding_version':EMBED_VERSION,'cross_task':cross_task,'veritas_score':None,'score_kind':'lexical_similarity_not_confidence'}

def bus():
    SHARED.mkdir(parents=True,exist_ok=True)
    db=connect(SHARED/'coordination.sqlite')
    db.executescript('CREATE TABLE IF NOT EXISTS traces(task_id TEXT PRIMARY KEY,trace_json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,event_type TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS receipts(consumer TEXT NOT NULL,event_id TEXT NOT NULL,PRIMARY KEY(consumer,event_id));')
    return db

def trace(task_id):
    if not task_id:raise ValueError('task_id required')
    with closing(bus()) as db:
        raw=canonical({'trace_id':'VT-'+uuid.uuid4().hex,'task_id':task_id,'claeg_state':'STABLE_CONTINUATION'})
        db.execute('INSERT OR IGNORE INTO traces VALUES(?,?)',(task_id,raw))
        return json.loads(db.execute('SELECT trace_json FROM traces WHERE task_id=?',(task_id,)).fetchone()[0])

def event(task_id,event_type,payload,event_id=None):
    if not task_id:raise ValueError('task_id required')
    eid=event_id or uuid.uuid4().hex
    with closing(bus()) as db:db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',(eid,task_id,event_type,canonical(payload),datetime.now(timezone.utc).isoformat()))
    return eid

def pending(consumer,task_id=None):
    with closing(bus()) as db:
        sql='SELECT * FROM events e WHERE NOT EXISTS(SELECT 1 FROM receipts r WHERE r.event_id=e.id AND r.consumer=?)';args=[consumer]
        if task_id:sql+=' AND task_id=?';args.append(task_id)
        return [dict(r) for r in db.execute(sql+' ORDER BY created_at,id LIMIT 100',args)]

def acknowledge(consumer,event_id):
    with closing(bus()) as db:db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?)',(consumer,event_id))

def approval(tool,args,task_id):
    """Issue a locally authenticated, short-lived receipt from operator policy."""
    policy_path=SHARED/'operator-policy.json'
    if not policy_path.exists():raise ValueError('Operator policy not configured')
    raw=policy_path.read_bytes();policy=json.loads(raw)
    repo=str(Path(args.get('repoPath','')).resolve()).replace('\\','/')
    allowed=[str(Path(p).resolve()).replace('\\','/') for p in policy.get('witness_roots',[])]
    pathkey=lambda p:p.casefold() if os.name=='nt' else p
    if tool!='sswp_witness' or not task_id or pathkey(repo) not in [pathkey(p) for p in allowed]:raise ValueError('Action is outside operator policy')
    keypath=SHARED/'approval.key'
    if not keypath.exists():raise ValueError('Approval signing key unavailable')
    if set(args)!={'repoPath'}:raise ValueError('Only repoPath is supported for a witness receipt')
    payload={'version':1,'tool':tool,'args_sha256':hashlib.sha256(canonical(args).encode()).hexdigest(),'source_sha256':source_identity(repo),'task_id':task_id,'policy_sha256':hashlib.sha256(raw).hexdigest(),'expires':int(time.time())+120,'nonce':secrets.token_hex(16)}
    return {'payload':payload,'mac':hmac.new(keypath.read_bytes(),canonical(payload).encode(),hashlib.sha256).hexdigest()}

def source_identity(root):
    """Bind source bytes; installed dependencies and data remain host-trusted."""
    ignored={'.git','node_modules','.venv','data','__pycache__','.sswp.json'}
    rows=[]
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in ignored)
        for name in dirs+files:
            path=Path(folder)/name
            if name in ignored:continue
            if path.is_symlink():raise ValueError('Source symlinks require an explicit packaged source snapshot')
            if path.is_file():
                rows.append((path.relative_to(root).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest()))
    digest=hashlib.sha256()
    for name,sha in sorted(rows):digest.update((name+'\0'+sha+'\n').encode())
    return digest.hexdigest()
