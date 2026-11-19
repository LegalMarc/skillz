#!/usr/bin/env python3
"""Private SQLite run/action history. Does not read or control Mail."""
import argparse
import datetime as dt
import re
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing, contextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from review import normalize_snapshot, read_json, require

from config import STATE_ROOT
ROOT = STATE_ROOT


@contextmanager
def connect(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    connection=sqlite3.connect(path)
    path.chmod(0o600)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('''
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, as_of TEXT NOT NULL,
 review_path TEXT NOT NULL, reviewed_at TEXT, snapshot_json TEXT NOT NULL, as_of_utc TEXT
);
CREATE TABLE IF NOT EXISTS actions (
 run_id TEXT NOT NULL REFERENCES runs(run_id), item TEXT NOT NULL,
 event_json TEXT NOT NULL, PRIMARY KEY(run_id,item)
);
CREATE TABLE IF NOT EXISTS exports (
 operation TEXT NOT NULL DEFAULT 'apply', sha256 TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(run_id),
 received_at TEXT NOT NULL, outcome_json TEXT NOT NULL,
 PRIMARY KEY(operation,sha256)
);
CREATE TABLE IF NOT EXISTS item_counters (
 run_id TEXT PRIMARY KEY, next_number INTEGER NOT NULL CHECK(next_number > 0)
);
CREATE TABLE IF NOT EXISTS item_registry (
 run_id TEXT NOT NULL, item TEXT NOT NULL, identity_key TEXT NOT NULL,
 allocated_at TEXT NOT NULL, tombstoned_at TEXT,
 PRIMARY KEY(run_id,item), UNIQUE(run_id,identity_key)
);
CREATE TABLE IF NOT EXISTS item_aliases (
 run_id TEXT NOT NULL, item TEXT NOT NULL, identity_key TEXT NOT NULL,
 PRIMARY KEY(run_id,identity_key), FOREIGN KEY(run_id,item) REFERENCES item_registry(run_id,item)
);
CREATE TABLE IF NOT EXISTS assessments (
 run_id TEXT NOT NULL, identity_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 assessed_at TEXT NOT NULL, rules_digest TEXT NOT NULL, content_digest TEXT NOT NULL,
 thread_digest TEXT NOT NULL, deadline TEXT, evidence_json TEXT NOT NULL,
 result_json TEXT NOT NULL, invalidated_at TEXT, invalidation_reason TEXT, correction_version TEXT NOT NULL DEFAULT '0',
 PRIMARY KEY(run_id,identity_key,fingerprint)
);
CREATE TABLE IF NOT EXISTS followups (
 task_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, item TEXT NOT NULL,
 account TEXT NOT NULL, message_id TEXT NOT NULL, current_id INTEGER NOT NULL, summary TEXT NOT NULL,
 next_action TEXT NOT NULL, status TEXT NOT NULL, deadline TEXT,
 waiting_on TEXT, evidence_refs_json TEXT NOT NULL, result_link TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 result_confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
 run_id TEXT NOT NULL, item TEXT NOT NULL, account TEXT NOT NULL, message_id TEXT NOT NULL,
 current_id INTEGER NOT NULL, original_summary TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(run_id,item,created_at)
);
''')
    export_columns={row[1] for row in connection.execute('PRAGMA table_info(exports)')}
    if 'operation' not in export_columns:
        connection.execute('ALTER TABLE exports RENAME TO exports_legacy')
        connection.execute('''CREATE TABLE exports (
            operation TEXT NOT NULL, sha256 TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(run_id),
            received_at TEXT NOT NULL, outcome_json TEXT NOT NULL,
            PRIMARY KEY(operation,sha256)
        )''')
        for digest,run_id,received_at,outcome_json in connection.execute('SELECT sha256,run_id,received_at,outcome_json FROM exports_legacy').fetchall():
            operation=_legacy_export_operation(digest,outcome_json)
            connection.execute('INSERT INTO exports(operation,sha256,run_id,received_at,outcome_json) VALUES(?,?,?,?,?)',
                (operation,digest,run_id,received_at,outcome_json))
        connection.execute('DROP TABLE exports_legacy')
    run_columns={row[1] for row in connection.execute('PRAGMA table_info(runs)')}
    if 'as_of_utc' not in run_columns:connection.execute('ALTER TABLE runs ADD COLUMN as_of_utc TEXT')
    for run_id,as_of in connection.execute('SELECT run_id,as_of FROM runs WHERE as_of_utc IS NULL').fetchall():
        connection.execute('UPDATE runs SET as_of_utc=? WHERE run_id=?',(_parse_aware(as_of).isoformat(timespec='microseconds'),run_id))
    connection.execute('CREATE INDEX IF NOT EXISTS runs_as_of_utc ON runs(as_of_utc DESC)')
    assessment_columns={row[1] for row in connection.execute('PRAGMA table_info(assessments)')}
    if 'correction_version' not in assessment_columns:
        connection.execute("ALTER TABLE assessments ADD COLUMN correction_version TEXT NOT NULL DEFAULT '0'")
    followup_columns={row[1] for row in connection.execute('PRAGMA table_info(followups)')}
    if 'current_id' not in followup_columns:
        connection.execute('ALTER TABLE followups ADD COLUMN current_id INTEGER')
        for task_id,run_id,item,account,message_id in connection.execute('SELECT task_id,run_id,item,account,message_id FROM followups WHERE current_id IS NULL').fetchall():
            saved=connection.execute('SELECT snapshot_json FROM runs WHERE run_id=?',(run_id,)).fetchone()
            if saved:
                snapshot=json.loads(saved[0])
                matches=[r['current_id'] for r in snapshot.get('records',[]) if r.get('item')==item and r.get('account')==account and r.get('message_id')==message_id]
                if len(matches)==1:connection.execute('UPDATE followups SET current_id=? WHERE task_id=?',(matches[0],task_id))
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback();raise
    finally:
        connection.close()


def review_path(value, root=ROOT):
    path=Path(value).resolve()
    require(path.is_relative_to(root.resolve()/'runs') and path.suffix=='.html', 'History review must stay within private run directory')
    return str(path)


def register(database, snapshot, path, actions=(), reviewed_at=None):
    snapshot=normalize_snapshot(snapshot);path=review_path(path)
    require(snapshot.get('refreshed_at'), 'History requires actual inventory time')
    rows={r['item']:r for r in snapshot['records']}
    payload=json.dumps(snapshot,sort_keys=True)
    with connect(database) as c:
        old=c.execute('SELECT snapshot_id,review_path FROM runs WHERE run_id=?',(snapshot['run_id'],)).fetchone()
        require(old is None or old==(snapshot['snapshot_id'],path), 'Run is immutable: use a new run ID for a changed snapshot')
        c.execute('INSERT OR IGNORE INTO runs(run_id,snapshot_id,as_of,review_path,reviewed_at,snapshot_json,as_of_utc) VALUES(?,?,?,?,?,?,?)',
            (snapshot['run_id'],snapshot['snapshot_id'],snapshot['refreshed_at'],path,reviewed_at,payload,_parse_aware(snapshot['refreshed_at']).isoformat(timespec='microseconds')))
        # Import legacy item numbers once and keep the high-water mark even when later snapshots omit rows.
        max_number=0
        for record in snapshot['records']:
            match=__import__('re').fullmatch(r'M(\d+)',record['item'])
            if not match:continue
            max_number=max(max_number,int(match[1]))
            identity=_identity_key({'account':record['account'],'message_id':record['message_id'],'current_id':record['current_id']})
            exists=c.execute('SELECT 1 FROM item_registry WHERE run_id=? AND item=?',(snapshot['run_id'],record['item'])).fetchone()
            if not exists:
                c.execute('INSERT INTO item_registry VALUES(?,?,?,?,NULL)',(snapshot['run_id'],record['item'],identity,dt.datetime.now(dt.timezone.utc).isoformat()))
            alias=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(snapshot['run_id'],identity)).fetchone()
            require(alias is None or alias[0]==record['item'],'Exact copy identity belongs to another item')
            c.execute('INSERT OR IGNORE INTO item_aliases VALUES(?,?,?)',(snapshot['run_id'],record['item'],identity))
        if max_number:c.execute('INSERT INTO item_counters VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET next_number=MAX(next_number,excluded.next_number)',(snapshot['run_id'],max_number+1))
        if reviewed_at:c.execute('UPDATE runs SET reviewed_at=COALESCE(reviewed_at,?) WHERE run_id=?',(reviewed_at,snapshot['run_id']))
        for action in actions:
            require(action['item'] in rows and action.get('status') in ('verified-moved','verified-retained','verified-completed'), 'History accepts verified actions only')
            r=rows[action['item']]
            require(action.get('destination') == r['observed_mailbox'] and action.get('old_mailbox') in ('INBOX','Archive','Junk','Trash'), 'Action differs from verified snapshot outcome')
            require(action.get('account') == r['account'] and action.get('message_id') == r['message_id'], 'Action identity differs from snapshot')
            require(type(action.get('old_id')) is int and action['old_id'] > 0 and type(action.get('new_id')) is int and action['new_id'] == r['current_id'], 'Action numeric ID differs from verified snapshot')
            require(isinstance(action.get('reason'),str) and len(action['reason'])<=4000, 'Invalid history reason')
            stamp=dt.datetime.fromisoformat(action['at'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'Action time needs timezone')
            event={k:action[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','new_id','reason','status')}
            for key in ('attempt_id','lineage_source_attempt_id','receipt_new_id'):
                if key in action:event[key]=action[key]
            event.update(subject=r['subject'],to_display=r['to_display'],received=r['received'],at=action['at'])
            text=json.dumps(event,sort_keys=True)
            existing=c.execute('SELECT event_json FROM actions WHERE run_id=? AND item=?',(snapshot['run_id'],r['item'])).fetchone()
            require(existing is None or existing[0]==text,'Conflicting action history')
            c.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?)',(snapshot['run_id'],r['item'],text))


def acknowledge(database, run_id, at, export_digest=None, outcome=None, *, operation='apply'):
    stamp=dt.datetime.fromisoformat(at.replace('Z','+00:00'));require(stamp.tzinfo is not None,'Review acknowledgment needs timezone')
    require(operation in ('apply','refresh'),'Unknown export receipt operation')
    with connect(database) as c:
        require(c.execute('SELECT 1 FROM runs WHERE run_id=?',(run_id,)).fetchone(),'Unknown history run')
        c.execute('UPDATE runs SET reviewed_at=COALESCE(reviewed_at,?) WHERE run_id=?',(at,run_id))
        if export_digest:
            require(len(export_digest)==64 and all(x in '0123456789abcdef' for x in export_digest),'Invalid export digest')
            require(not c.execute("SELECT 1 FROM exports WHERE operation='legacy-unknown' AND sha256=?",(export_digest,)).fetchone(),
                'Legacy export metadata is ambiguous; refusing to acknowledge this digest')
            payload=json.dumps(outcome or {},sort_keys=True)
            existing=c.execute('SELECT run_id,outcome_json FROM exports WHERE operation=? AND sha256=?',(operation,export_digest)).fetchone()
            require(existing is None or existing==(run_id,payload),'Export digest was already acknowledged with a different run or outcome')
            c.execute('INSERT OR IGNORE INTO exports VALUES(?,?,?,?,?)',(operation,export_digest,run_id,at,payload))


def get_registered_snapshot(database,run_id):
    """Return the immutable source snapshot for an already registered run, if present."""
    if not Path(database).exists():return None
    with connect(database):pass
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        row=c.execute('SELECT snapshot_json FROM runs WHERE run_id=?',(run_id,)).fetchone()
    return normalize_snapshot(json.loads(row[0])) if row else None


def get_export_receipt(database,export_digest,*,operation='apply'):
    """Return a previously recorded review-export outcome for cross-run deduplication."""
    require(operation in ('apply','refresh'),'Unknown export receipt operation')
    if not Path(database).exists():return None
    with connect(database):pass
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        require(not c.execute("SELECT 1 FROM exports WHERE operation='legacy-unknown' AND sha256=?",(export_digest,)).fetchone(),
            'Legacy export metadata is ambiguous; refusing to classify this digest')
        row=c.execute('SELECT run_id,received_at,outcome_json FROM exports WHERE operation=? AND sha256=?',(operation,export_digest)).fetchone()
    return {'run_id':row[0],'received_at':row[1],'outcome':json.loads(row[2])} if row else None


def _legacy_export_operation(digest,outcome_json):
    """Classify only old receipt shapes whose operation is explicit in their payload."""
    try:outcome=json.loads(outcome_json)
    except (TypeError,ValueError):return 'legacy-unknown'
    if not isinstance(outcome,dict):return 'legacy-unknown'
    if outcome.get('status')=='read-only-refresh-complete':
        required=('source_snapshot_id','refreshed_snapshot_id','snapshot','pending_review_bundle')
        if (outcome.get('bundle_sha256')==digest and outcome.get('mail_changed') is False
            and all(isinstance(outcome.get(key),str) and outcome[key] for key in required)
            and isinstance(outcome.get('item_outcomes'),list)):
            return 'refresh'
        return 'legacy-unknown'
    # Successful old run_pipeline receipts have no top-level status. These
    # fields are present together only after the post-action snapshot was
    # verified and its review was published.
    if (not outcome.get('status') and isinstance(outcome.get('run_id'),str) and outcome.get('run_id')
        and isinstance(outcome.get('snapshot_id'),str) and outcome.get('snapshot_id')
        and isinstance(outcome.get('verified_snapshot_id'),str) and outcome.get('verified_snapshot_id')
        and type(outcome.get('verified_actions')) is int and isinstance(outcome.get('review'),str) and outcome.get('review')):
        return 'apply'
    return 'legacy-unknown'


def export_history(database,limit=100,since=None,until=None,timezone_name=None):
    require(type(limit) is int and 1<=limit<=1000,'History window must be 1..1000 runs')
    if not Path(database).exists():return []
    with connect(database):pass
    has_date_only_bound=any(isinstance(bound,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',bound) for bound in (since,until))
    if timezone_name is None and has_date_only_bound:
        from config import CONFIG, CONFIG_TIMEZONE_EXPLICIT
        require(CONFIG_TIMEZONE_EXPLICIT,'Date-only history bounds require an explicit IANA timezone when the configuration is legacy')
        timezone_name=CONFIG.get('timezone')
    elif timezone_name is None:
        # No date-only conversion depends on a zone here. UTC is only an inert
        # parser context for offset-bearing timestamps, never a local-time guess.
        timezone_name='UTC'
    require(isinstance(timezone_name,str) and timezone_name,'History bounds require a valid IANA timezone')
    try:zone=ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:require(False,'Unknown history timezone')
    lower=_history_bound(since,upper=False,zone=zone) if since else None
    upper=_history_bound(until,upper=True,zone=zone) if until else None
    c=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        result=[]
        query='SELECT run_id,as_of,review_path,reviewed_at,snapshot_json FROM runs';clauses=[];params=[]
        if lower is not None:clauses.append('as_of_utc >= ?');params.append(lower.isoformat(timespec='microseconds'))
        if upper is not None:clauses.append('as_of_utc <= ?');params.append(upper.isoformat(timespec='microseconds'))
        if clauses:query+=' WHERE '+' AND '.join(clauses)
        query+=' ORDER BY as_of_utc DESC LIMIT ?';params.append(limit)
        for run_id,as_of,path,reviewed,snapshot_json in c.execute(query,params).fetchall():
            snapshot=normalize_snapshot(json.loads(snapshot_json))
            tasks=[]
            task_rows=c.execute('SELECT task_id,run_id,item,account,message_id,current_id,summary,next_action,status,deadline,waiting_on,evidence_refs_json,result_link,created_at,updated_at,result_confirmed_at FROM followups WHERE run_id=? ORDER BY deadline,updated_at',(run_id,)).fetchall()
            for row in task_rows:
                tasks.append(dict(zip(['task_id','run_id','item','account','message_id','current_id','summary','next_action','status','deadline','waiting_on','evidence_refs','result_link','created_at','updated_at','result_confirmed_at'],row))|{'evidence_refs':json.loads(row[11])})
            assessments=[]
            assessment_rows=c.execute('SELECT identity_key,assessed_at,rules_digest,content_digest,thread_digest,deadline,evidence_json,result_json,invalidated_at,invalidation_reason,correction_version FROM assessments WHERE run_id=? ORDER BY assessed_at DESC LIMIT 500',(run_id,)).fetchall()
            for row in assessment_rows:
                ident=json.loads(row[0]); item=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,row[0])).fetchone()
                assessments.append({'item':item[0] if item else None,**ident,'assessed_at':row[1],'rules_digest':row[2],'content_digest':row[3],'thread_digest':row[4],'deadline':row[5],'evidence':json.loads(row[6]),'result':json.loads(row[7]),'invalidated_at':row[8],'invalidation_reason':row[9],'correction_version':row[10]})
            action_rows=c.execute('SELECT event_json FROM actions WHERE run_id=? ORDER BY item',(run_id,)).fetchall()
            result.append({'run_id':run_id,'at':as_of,'reviewed_at':reviewed,'review_url':Path(review_path(path)).as_uri(),'counts':{folder:sum(r['observed_mailbox']==folder for r in snapshot['records']) for folder in ('INBOX','Archive','Junk','Trash')},'actions':[json.loads(row[0]) for row in action_rows],'tasks':tasks,'assessments':assessments})
        return result
    finally:c.close()


def _identity_key(identity):
    require(isinstance(identity,dict) and set(identity)=={'account','message_id','current_id'},'Exact copy identity required')
    require(isinstance(identity['account'],str) and identity['account'] and isinstance(identity['message_id'],str) and identity['message_id'] and type(identity['current_id']) is int and identity['current_id']>0,'Invalid exact copy identity')
    return json.dumps(identity,sort_keys=True,separators=(',',':'))


def _parse_aware(value):
    try:parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError):require(False,'History timestamps must be ISO date-times')
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,'History timestamps must include an offset')
    return parsed.astimezone(dt.timezone.utc)


def _history_bound(value,*,upper,zone):
    require(isinstance(value,str),'History bounds must be strings')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        try:day=dt.date.fromisoformat(value)
        except ValueError:require(False,'Invalid history date bound')
        if upper:
            next_day=day+dt.timedelta(days=1)
            return dt.datetime.combine(next_day,dt.time.min,zone).astimezone(dt.timezone.utc)-dt.timedelta(microseconds=1)
        return dt.datetime.combine(day,dt.time.min,zone).astimezone(dt.timezone.utc)
    return _parse_aware(value)


def allocate_item_id(database, run_id, identity, preferred=None, at=None):
    """Allocate a stable per-run item number; removed items remain reserved forever."""
    key=_identity_key(identity); stamp=at or dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(database) as c:
        found=c.execute('SELECT item FROM item_registry WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        if found is None:found=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        if found:return found[0]
        if preferred is not None:
            require(isinstance(preferred,str) and __import__('re').fullmatch(r'M\d{1,9}',preferred),'Invalid preferred item number')
            require(c.execute('SELECT 1 FROM item_registry WHERE run_id=? AND item=?',(run_id,preferred)).fetchone() is None,'Item number is already reserved')
            number=int(preferred[1:])
        else:
            row=c.execute('SELECT next_number FROM item_counters WHERE run_id=?',(run_id,)).fetchone()
            number=row[0] if row else 1
            while c.execute('SELECT 1 FROM item_registry WHERE run_id=? AND item=?',(run_id,f'M{number:03d}')).fetchone():number+=1
        item=f'M{number:03d}'
        c.execute('INSERT INTO item_registry VALUES(?,?,?,?,NULL)',(run_id,item,key,stamp))
        c.execute('INSERT OR IGNORE INTO item_aliases VALUES(?,?,?)',(run_id,item,key))
        c.execute('INSERT INTO item_counters VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET next_number=MAX(next_number,excluded.next_number)',(run_id,number+1))
        return item


def reserve_snapshot_items(database,snapshot,at=None):
    """Import legacy numbers and advance the counter without registering a run snapshot."""
    stamp=at or dt.datetime.now(dt.timezone.utc).isoformat();snapshot=normalize_snapshot(snapshot);highest=0
    with connect(database) as c:
        for record in snapshot['records']:
            match=__import__('re').fullmatch(r'M(\d+)',record['item'])
            if not match:continue
            highest=max(highest,int(match[1]));key=_identity_key({'account':record['account'],'message_id':record['message_id'],'current_id':record['current_id']})
            occupied=c.execute('SELECT identity_key FROM item_registry WHERE run_id=? AND item=?',(snapshot['run_id'],record['item'])).fetchone()
            if occupied is None:c.execute('INSERT INTO item_registry VALUES(?,?,?,?,NULL)',(snapshot['run_id'],record['item'],key,stamp))
            alias=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(snapshot['run_id'],key)).fetchone()
            require(alias is None or alias[0]==record['item'],'Exact copy identity belongs to another item')
            c.execute('INSERT OR IGNORE INTO item_aliases VALUES(?,?,?)',(snapshot['run_id'],record['item'],key))
        if highest:c.execute('INSERT INTO item_counters VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET next_number=MAX(next_number,excluded.next_number)',(snapshot['run_id'],highest+1))


def alias_item_identity(database,run_id,item,identity,at=None):
    """Associate a verified moved copy's new Mail numeric ID with its existing item."""
    key=_identity_key(identity)
    with connect(database) as c:
        require(c.execute('SELECT 1 FROM item_registry WHERE run_id=? AND item=?',(run_id,item)).fetchone(),'Unknown item')
        prior=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        require(prior is None or prior[0]==item,'Exact copy identity already belongs to another item')
        c.execute('INSERT OR IGNORE INTO item_aliases VALUES(?,?,?)',(run_id,item,key))


def tombstone_item(database,run_id,item,at=None):
    stamp=at or dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(database) as c:
        require(c.execute('UPDATE item_registry SET tombstoned_at=COALESCE(tombstoned_at,?) WHERE run_id=? AND item=?',(stamp,run_id,item)).rowcount==1,'Unknown registered item')


def record_assessment(database,run_id,identity,*,fingerprint,assessed_at,rules_digest,content_digest,thread_digest,correction_version='0',deadline=None,evidence,result):
    key=_identity_key(identity)
    for value in (fingerprint,rules_digest,content_digest,thread_digest):require(isinstance(value,str) and value,'Assessment digests required')
    stamp=dt.datetime.fromisoformat(assessed_at.replace('Z','+00:00'));require(stamp.tzinfo is not None,'Assessment time needs timezone')
    require(isinstance(evidence,list) and all(isinstance(x,dict) for x in evidence) and isinstance(result,dict),'Structured assessment required')
    with connect(database) as c:
        c.execute('''INSERT INTO assessments(run_id,identity_key,fingerprint,assessed_at,rules_digest,content_digest,thread_digest,deadline,evidence_json,result_json,invalidated_at,invalidation_reason,correction_version)
          VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL,?)
          ON CONFLICT(run_id,identity_key,fingerprint) DO UPDATE SET assessed_at=excluded.assessed_at,
          rules_digest=excluded.rules_digest,content_digest=excluded.content_digest,thread_digest=excluded.thread_digest,
          deadline=excluded.deadline,evidence_json=excluded.evidence_json,result_json=excluded.result_json,invalidated_at=NULL,invalidation_reason=NULL,correction_version=excluded.correction_version''',
          (run_id,key,fingerprint,assessed_at,rules_digest,content_digest,thread_digest,deadline,json.dumps(evidence,sort_keys=True),json.dumps(result,sort_keys=True),str(correction_version)))


def get_cached_assessment(database,run_id,identity,*,fingerprint,rules_digest,content_digest,thread_digest,now=None):
    if not Path(database).exists():return None
    with connect(database):pass
    key=_identity_key(identity);now=now or dt.datetime.now(dt.timezone.utc)
    if isinstance(now,str):now=dt.datetime.fromisoformat(now.replace('Z','+00:00'))
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        alias=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        aliases=[key]
        if alias:aliases=[r[0] for r in c.execute('SELECT identity_key FROM item_aliases WHERE run_id=? AND item=?',(run_id,alias[0])).fetchall()]
        marks=','.join('?' for _ in aliases)
        row=c.execute(f'''SELECT assessed_at,deadline,evidence_json,result_json FROM assessments WHERE run_id=? AND identity_key IN ({marks}) AND fingerprint=? AND rules_digest=? AND content_digest=? AND thread_digest=? AND invalidated_at IS NULL ORDER BY assessed_at DESC LIMIT 1''',(run_id,*aliases,fingerprint,rules_digest,content_digest,thread_digest)).fetchone()
    if not row:return None
    if row[1]:
        deadline=dt.datetime.fromisoformat(row[1].replace('Z','+00:00'))
        if deadline.tzinfo is None or deadline<=now:return None
    return {'assessed_at':row[0],'deadline':row[1],'evidence':json.loads(row[2]),'result':json.loads(row[3])}


def invalidate_assessments(database,run_id,identity,reason,at=None):
    key=_identity_key(identity);stamp=at or dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(database) as c:
        alias=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        aliases=[key]
        if alias:aliases=[r[0] for r in c.execute('SELECT identity_key FROM item_aliases WHERE run_id=? AND item=?',(run_id,alias[0])).fetchall()]
        marks=','.join('?' for _ in aliases)
        c.execute(f'UPDATE assessments SET invalidated_at=?,invalidation_reason=? WHERE run_id=? AND identity_key IN ({marks}) AND invalidated_at IS NULL',(stamp,reason,run_id,*aliases))


def assessment_cache_decision(database,run_id,identity,*,rules_digest,content_digest,thread_digest,correction_version='0',now=None):
    cached=get_cached_assessment(database,run_id,identity,fingerprint=__import__('hashlib').sha256(json.dumps([content_digest,rules_digest,thread_digest,str(correction_version)],separators=(',',':')).encode()).hexdigest(),rules_digest=rules_digest,content_digest=content_digest,thread_digest=thread_digest,now=now)
    if cached:return {'status':'reusable','reason':'all evidence fingerprints and deadline are current','assessment':cached}
    key=_identity_key(identity)
    if not Path(database).exists():return {'status':'awaiting_assessment','reason':'no_saved_assessment'}
    with connect(database):pass
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        alias=c.execute('SELECT item FROM item_aliases WHERE run_id=? AND identity_key=?',(run_id,key)).fetchone()
        aliases=[key]
        if alias:aliases=[r[0] for r in c.execute('SELECT identity_key FROM item_aliases WHERE run_id=? AND item=?',(run_id,alias[0])).fetchall()]
        marks=','.join('?' for _ in aliases)
        row=c.execute(f'SELECT rules_digest,content_digest,thread_digest,deadline,correction_version,invalidated_at,invalidation_reason FROM assessments WHERE run_id=? AND identity_key IN ({marks}) ORDER BY assessed_at DESC LIMIT 1',(run_id,*aliases)).fetchone()
    if not row:return {'status':'awaiting_assessment','reason':'no_saved_assessment'}
    if row[5]:return {'status':'awaiting_assessment','reason':row[6] or 'assessment_invalidated'}
    for old,new,reason in zip(row[:3],(rules_digest,content_digest,thread_digest),('rules_changed','content_changed','thread_reply')):
        if old!=new:return {'status':'awaiting_assessment','reason':reason}
    if row[4]!=str(correction_version):return {'status':'awaiting_assessment','reason':'user_correction'}
    return {'status':'awaiting_assessment','reason':'deadline_due_or_assessment_expired'}


FOLLOWUP_STATUSES={'ready','waiting_user_authentication','waiting_vendor','blocked_by_terms','completed','cancelled'}
def upsert_followup(database,task,*,preserve_progress=False):
    keys={'task_id','run_id','item','account','message_id','current_id','summary','next_action','status','deadline','waiting_on','evidence_refs','result_link','created_at','updated_at','result_confirmed_at'}
    require(isinstance(task,dict) and set(task)==keys,'Invalid follow-up fields')
    require(task['status'] in FOLLOWUP_STATUSES,'Invalid follow-up status')
    for key in ('task_id','run_id','item','account','message_id','summary','next_action','created_at','updated_at'):require(isinstance(task[key],str) and task[key],'Missing follow-up '+key)
    require(type(task['current_id']) is int and task['current_id']>0,'Invalid follow-up numeric identity')
    require(isinstance(task['evidence_refs'],list) and all(isinstance(x,str) for x in task['evidence_refs']),'Invalid follow-up evidence references')
    if task['status']=='completed':require(task['result_confirmed_at'] is not None,'Completion requires a confirmed result timestamp')
    conflict_sql='''ON CONFLICT(task_id) DO UPDATE SET current_id=excluded.current_id'''
    if not preserve_progress:
        conflict_sql='''ON CONFLICT(task_id) DO UPDATE SET
          summary=excluded.summary,next_action=excluded.next_action,status=excluded.status,deadline=excluded.deadline,waiting_on=excluded.waiting_on,
          evidence_refs_json=excluded.evidence_refs_json,result_link=excluded.result_link,updated_at=excluded.updated_at,result_confirmed_at=excluded.result_confirmed_at,
          current_id=excluded.current_id'''
    with connect(database) as c:
        c.execute('''INSERT INTO followups(task_id,run_id,item,account,message_id,current_id,summary,next_action,status,deadline,waiting_on,evidence_refs_json,result_link,created_at,updated_at,result_confirmed_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) '''+conflict_sql,
          (task['task_id'],task['run_id'],task['item'],task['account'],task['message_id'],task['current_id'],task['summary'],task['next_action'],task['status'],task['deadline'],task['waiting_on'],json.dumps(task['evidence_refs']),task['result_link'],task['created_at'],task['updated_at'],task['result_confirmed_at']))


def list_followups(database,statuses=None):
    if not Path(database).exists():return []
    with connect(database):pass
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        if statuses:
            require(all(x in FOLLOWUP_STATUSES for x in statuses),'Invalid follow-up status filter')
            q=','.join('?' for _ in statuses);rows=c.execute(f'SELECT task_id,run_id,item,account,message_id,current_id,summary,next_action,status,deadline,waiting_on,evidence_refs_json,result_link,created_at,updated_at,result_confirmed_at FROM followups WHERE status IN ({q}) ORDER BY deadline,updated_at',(tuple(statuses))).fetchall()
        else:rows=c.execute('SELECT task_id,run_id,item,account,message_id,current_id,summary,next_action,status,deadline,waiting_on,evidence_refs_json,result_link,created_at,updated_at,result_confirmed_at FROM followups ORDER BY deadline,updated_at').fetchall()
    cols=['task_id','run_id','item','account','message_id','current_id','summary','next_action','status','deadline','waiting_on','evidence_refs','result_link','created_at','updated_at','result_confirmed_at']
    return [dict(zip(cols,row))|{'evidence_refs':json.loads(row[11])} for row in rows]


def record_comment(database,run_id,item,identity,original_summary,comment,at=None):
    _identity_key(identity);require(isinstance(original_summary,str) and isinstance(comment,str) and comment.strip() and len(comment)<=4000,'Invalid user comment')
    stamp=at or dt.datetime.now(dt.timezone.utc).isoformat()
    with connect(database) as c:
        c.execute('INSERT OR IGNORE INTO comments VALUES(?,?,?,?,?,?,?,?)',(run_id,item,identity['account'],identity['message_id'],identity['current_id'],original_summary,comment,stamp))


def journal_attempt_state(events,snapshot_id):
    """Validate journal outcomes against exactly one intent and durable move receipt."""
    selected=[event for event in events if event.get('snapshot_id')==snapshot_id]
    intent_groups={};terminal_groups={};receipts={}
    for event in selected:
        attempt=event.get('attempt_id');status=event.get('status')
        if status=='intent' and attempt:intent_groups.setdefault(attempt,[]).append(event)
        elif status=='move-receipt' and attempt:receipts.setdefault(attempt,[]).append(event)
        elif attempt and status in ('verified-moved','verified-completed','verified-not-started','ambiguous'):
            terminal_groups.setdefault(attempt,[]).append(event)
    terminal={};invalid=[]
    for attempt,receipt_list in receipts.items():
        if attempt not in intent_groups:invalid.extend(receipt_list)
    for attempt,terminal_list in terminal_groups.items():
        intent_list=intent_groups.get(attempt,[])
        if len(terminal_list)!=1 or len(intent_list)!=1:
            invalid.extend(terminal_list);continue
        event=terminal_list[0];intent=intent_list[0];status=event['status'];receipt_list=receipts.get(attempt,[])
        identity_fields=('attempt_id','item','account','message_id','old_id','old_mailbox','destination','snapshot_id')
        if not all(intent.get(key)==event.get(key) for key in identity_fields):
            invalid.append(event);continue
        if status in ('verified-moved','verified-completed'):
            receipt_fields=identity_fields+('pre_destination_ids','pre_source_junk')
            pre_ids=intent.get('pre_destination_ids')
            if (len(receipt_list)!=1 or not all(receipt_list[0].get(key)==intent.get(key) for key in receipt_fields)
                or not isinstance(pre_ids,list) or any(type(value) is not int or value<=0 for value in pre_ids) or len(pre_ids)!=len(set(pre_ids))
                or type(intent.get('pre_source_junk')) is not bool
                or type(receipt_list[0].get('new_id')) is not int or receipt_list[0]['new_id']<=0 or type(receipt_list[0].get('junk')) is not bool
                or type(event.get('new_id')) is not int or type(event.get('junk')) is not bool
                or event.get('new_id')!=receipt_list[0].get('new_id') or event.get('junk') is not receipt_list[0].get('junk')
                or receipt_list[0].get('junk') is not (intent.get('destination')=='Junk')):
                invalid.append(event);continue
            if status=='verified-completed' and event.get('receipt_attempt_id')!=attempt:
                invalid.append(event);continue
        elif status=='verified-not-started':
            if receipt_list or not all(event.get(key)==intent.get(key) for key in ('pre_destination_ids','pre_source_junk')):
                invalid.append(event);continue
        elif status=='ambiguous' and (len(receipt_list)>1 or (receipt_list and not all(receipt_list[0].get(key)==intent.get(key) for key in identity_fields+('pre_destination_ids','pre_source_junk')))):
            invalid.append(event);continue
        terminal[attempt]=event
    verified=[event for event in terminal.values() if event.get('status') in ('verified-moved','verified-completed')]
    for event in selected:
        if event.get('status')=='verified-retained' and not event.get('attempt_id'):
            if (all(isinstance(event.get(key),str) and event[key] for key in ('item','account','message_id','old_mailbox','destination'))
                and type(event.get('old_id')) is int and event['old_id']>0 and type(event.get('new_id')) is int
                and event.get('new_id')==event.get('old_id') and event.get('destination')==event.get('old_mailbox')
                and type(event.get('junk')) is bool and event['junk']==(event.get('destination')=='Junk')):
                verified.append(event)
            else:invalid.append(event)
    conflicts=[event for event in selected if event.get('status')=='conflict-or-failed']
    intents={attempt:items[0] for attempt,items in intent_groups.items() if items}
    unresolved=[intents[attempt] for attempt in intents.keys()-terminal.keys()]
    not_started=[event for event in terminal.values() if event.get('status')=='verified-not-started']
    ambiguous=[event for event in terminal.values() if event.get('status')=='ambiguous']
    return {'selected':selected,'intents':intents,'terminal':terminal,'verified':verified,'conflicts':conflicts,
        'unresolved':unresolved,'not_started':not_started,'ambiguous':ambiguous+invalid}


def verified_journal_actions(events,snapshot_id):
    """Return only validated terminal actions, enriched with their matched receipt."""
    state=journal_attempt_state(events,snapshot_id)
    receipts={event.get('attempt_id'):event for event in state['selected'] if event.get('status')=='move-receipt' and event.get('attempt_id')}
    actions=[]
    for outcome in state['verified']:
        attempt=outcome.get('attempt_id')
        if not attempt:
            actions.append(dict(outcome));continue
        intent=state['intents'].get(attempt,{})
        receipt=receipts.get(attempt,{})
        event={**intent,**receipt,**outcome}
        if event.get('status') in ('verified-moved','verified-completed'):
            event['receipt_new_id']=receipt.get('new_id')
            event['at']=outcome.get('at') or receipt.get('completed_at') or intent.get('at')
        actions.append(event)
    return actions


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',default=str(ROOT/'history.sqlite3'));p.add_argument('--snapshot');p.add_argument('--review-html');p.add_argument('--journal');p.add_argument('--export');p.add_argument('--reviewed-at');p.add_argument('--since',help='Inclusive ISO timestamp/date for offline history window');p.add_argument('--until',help='Inclusive ISO timestamp/date for offline history window');p.add_argument('--timezone',help='Explicit IANA timezone for date-only bounds; required when legacy settings omit a configured timezone');p.add_argument('--limit',type=int,default=100);a=p.parse_args()
    if a.snapshot:
        require(a.review_html,'Review HTML required');actions=[]
        snapshot=read_json(a.snapshot)
        if a.journal:
            events=[json.loads(line) for line in Path(a.journal).read_text().splitlines() if line.strip()]
            # A completed journal normally binds to the pre-move source snapshot,
            # while this command registers the verified post-move snapshot. Validate
            # every source run represented by intents, then let register enforce the
            # exact destination identity against the supplied current snapshot.
            source_ids={event.get('snapshot_id') for event in events if event.get('status')=='intent' and isinstance(event.get('snapshot_id'),str)}
            if not source_ids:source_ids={normalize_snapshot(snapshot)['snapshot_id']}
            actions=[]
            for source_id in sorted(source_ids):actions.extend(verified_journal_actions(events,source_id))
        register(a.database,snapshot,a.review_html,actions,a.reviewed_at)
    if a.export:
        from review import private_write
        private_write(a.export,json.dumps(export_history(a.database,a.limit,a.since,a.until,a.timezone),indent=2)+'\n')

if __name__=='__main__':
    os.umask(0o077);main()
