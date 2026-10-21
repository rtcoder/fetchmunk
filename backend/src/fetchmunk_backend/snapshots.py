"""Bounded SQLite readers with authenticated keyset cursors; no history copies."""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from .wire import MAX_FRAME


class SnapshotError(ValueError):
    pass


@dataclass
class Snapshot:
    db: sqlite3.Connection
    started: float
    seq: int
    filter: str


class SnapshotStore:
    def __init__(self, clock=time.monotonic, wal_budget=64*1024*1024):
        self.clock = clock
        self.wal_budget = wal_budget
        self.snapshots = {}
        self.secret = secrets.token_bytes(32)

    @staticmethod
    def validate(limit, filter=None, anchor=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SnapshotError('invalid_params')
        if filter is not None and filter not in ('all','active','history'):
            raise SnapshotError('invalid_params')
        if anchor is not None and (not isinstance(anchor,list) or len(anchor)!=2 or
                                   not all(isinstance(v,str) and len(v)<=128 for v in anchor)):
            raise SnapshotError('invalid_params')

    def create(self, store, at_seq, limit=100, filter='all', anchor=None):
        self.validate(limit,filter,anchor)
        self.maintain(store)
        if len(self.snapshots)>=4:
            self._drop(next(iter(self.snapshots)))
        db=sqlite3.connect((store.data_dir/'state.sqlite').as_uri()+'?mode=ro',uri=True,
                           isolation_level=None,check_same_thread=False)
        sid=str(uuid.uuid4())
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA cache_size=-1024')
            db.execute('BEGIN')
            # Pin the read version now, while the service holds its mutation lock.
            db.execute('SELECT id FROM jobs LIMIT 1').fetchone()
            self.snapshots[sid]=Snapshot(db,self.clock(),at_seq,filter)
            return self._page(sid,'at',anchor,limit)
        except Exception:
            if sid in self.snapshots:self._drop(sid)
            else:db.close()
            raise

    def _token(self,sid,direction,anchor):
        payload=json.dumps([sid,direction,anchor],separators=(',',':')).encode()
        signature=hmac.digest(self.secret,payload,hashlib.sha256)
        return base64.urlsafe_b64encode(signature+payload).decode()

    def page(self,cursor,limit=100,filter=None):
        self.validate(limit,filter)
        self._expire()
        try:
            if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
            raw=base64.b64decode(cursor,altchars=b'-_',validate=True)
            signature,payload=raw[:32],raw[32:]
            if not hmac.compare_digest(signature,hmac.digest(self.secret,payload,hashlib.sha256)):raise ValueError()
            sid,direction,anchor=json.loads(payload)
            self.validate(limit,filter,anchor)
            if direction not in ('older','newer'):raise ValueError()
        except (ValueError,TypeError):
            raise SnapshotError('invalid_params') from None
        snap=self.snapshots.get(sid)
        if snap is None:raise SnapshotError('snapshot_expired')
        if filter is not None and filter!=snap.filter:raise SnapshotError('invalid_params')
        return self._page(sid,direction,anchor,limit)

    def _drop(self,sid):
        self.snapshots.pop(sid).db.close()

    def _expire(self):
        for sid,snap in list(self.snapshots.items()):
            if self.clock()-snap.started>=60:self._drop(sid)

    def maintain(self,store):
        self._expire()
        path=store.data_dir/'state.sqlite-wal'
        if path.exists() and path.stat().st_size>self.wal_budget:
            self.close()
            # Never wait for another reader; the threshold is an intervention point.
            store.db.execute('PRAGMA busy_timeout=0')
            try:store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            finally:store.db.execute('PRAGMA busy_timeout=5000')

    def close(self):
        for sid in list(self.snapshots):self._drop(sid)

    @staticmethod
    def predicate(snap,direction,anchor):
        clauses=[];args=[]
        if snap.filter!='all':clauses.append('bucket=?');args.append(snap.filter)
        if anchor is not None:
            comparison={'newer':'>','older':'<','at':'<='}[direction]
            clauses.append(f'(created_at,id){comparison}(?,?)');args.extend(anchor)
        return (' WHERE '+' AND '.join(clauses) if clauses else ''),args

    def _page(self,sid,direction,anchor,limit):
        snap=self.snapshots[sid]
        where,args=self.predicate(snap,direction,anchor)
        order='ASC' if direction=='newer' else 'DESC'
        rows=snap.db.execute(f'SELECT data,created_at,id FROM jobs{where} ORDER BY created_at {order},id {order} LIMIT ?',(*args,limit))
        items=[];keys=[];size=1024
        for raw,date,jid in rows:
            item=json.loads(raw)
            item_size=len(json.dumps(item,ensure_ascii=False).encode())+1
            if size+item_size>MAX_FRAME:
                if not items:raise SnapshotError('record_too_large')
                break
            items.append(item);keys.append([date,jid]);size+=item_size
        rows.close()
        if direction=='newer':items.reverse();keys.reverse()
        def cursor_for(direction,key):
            where,args=self.predicate(snap,direction,key)
            exists=snap.db.execute('SELECT 1 FROM jobs'+where+' LIMIT 1',args).fetchone()
            return self._token(sid,direction,key) if exists else None
        return dict(snapshot_id=sid,at_seq=snap.seq,jobs=items,
                    next_cursor=cursor_for('older',keys[-1]) if keys else None,
                    previous_cursor=cursor_for('newer',keys[0]) if keys else (cursor_for('newer',anchor) if anchor else None))
