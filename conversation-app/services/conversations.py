"""SQLite conversation history, replayable events and durable usage outbox."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from urllib.parse import urlparse

TERMINAL = {'completed', 'cancelled', 'failed', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def citations(text):
    urls = re.findall(r'https?://[^\s<>\]\)"\x00-\x1f]+', text)
    return [{'url': u, 'title': urlparse(u).netloc} for u in dict.fromkeys(urls) if urlparse(u).hostname]


class Store:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.path = root / 'conversations.sqlite3'
        self.wake = threading.Condition()
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,content TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,message_id TEXT REFERENCES messages(id),request_id TEXT UNIQUE,settings TEXT,status TEXT,text TEXT DEFAULT '',error TEXT,provider TEXT DEFAULT '{}',usage TEXT,citations TEXT DEFAULT '[]',search_count INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_per_conversation ON attempts(conversation_id) WHERE status IN ('queued','streaming');
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,attempt_id TEXT REFERENCES attempts(id) ON DELETE CASCADE,type TEXT,data TEXT);
            CREATE INDEX IF NOT EXISTS attempt_events ON events(attempt_id,id);
            CREATE TABLE IF NOT EXISTS usage_outbox(attempt_id TEXT PRIMARY KEY,event TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,value TEXT);
            ''')
            # Recovery is persisted as an event so reconnecting browsers terminate.
            rows = db.execute("SELECT id FROM attempts WHERE status IN ('queued','streaming')").fetchall()
            for row in rows:
                db.execute("UPDATE attempts SET status='interrupted',updated_at=? WHERE id=?", (now(), row['id']))
                db.execute('INSERT INTO events(attempt_id,type,data) VALUES(?,?,?)',
                           (row['id'], 'done', json.dumps({'status': 'interrupted'})))
                usage = db.execute('SELECT event FROM usage_outbox WHERE attempt_id=?', (row['id'],)).fetchone()
                if usage:
                    event = json.loads(usage['event'])
                    event['status'] = 'interrupted'
                    db.execute('UPDATE usage_outbox SET event=? WHERE attempt_id=?', (json.dumps(event), row['id']))
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def conversations(self, query=''):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM conversations WHERE title LIKE ? ORDER BY updated_at DESC', ('%' + query + '%',))]

    def create(self):
        row = {'id': uid(), 'title': '새 대화', 'created_at': now(), 'updated_at': now()}
        with self.db() as db:
            db.execute('INSERT INTO conversations VALUES(:id,:title,:created_at,:updated_at)', row)
        return row

    def change(self, cid, title=None, delete=False):
        with self.db() as db:
            if not db.execute('SELECT id FROM conversations WHERE id=?', (cid,)).fetchone():
                raise KeyError(cid)
            if delete:
                if db.execute("SELECT id FROM attempts WHERE conversation_id=? AND status IN ('queued','streaming')", (cid,)).fetchone():
                    raise ValueError('응답을 중단한 뒤 삭제해 주세요.')
                db.execute('DELETE FROM conversations WHERE id=?', (cid,))
            else:
                db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=?', (title[:160], now(), cid))

    def attempt(self, aid):
        with self.db() as db:
            row = db.execute('SELECT * FROM attempts WHERE id=?', (aid,)).fetchone()
        if not row:
            raise KeyError(aid)
        row = dict(row)
        for key in ('settings', 'provider', 'usage', 'citations'):
            row[key] = json.loads(row[key]) if row[key] else None
        return row

    def messages(self, cid):
        with self.db() as db:
            if not db.execute('SELECT id FROM conversations WHERE id=?', (cid,)).fetchone():
                raise KeyError(cid)
            rows = [dict(r) for r in db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at,id', (cid,))]
            for row in rows:
                row['attempts'] = [self.attempt(r['id']) for r in db.execute('SELECT id FROM attempts WHERE message_id=? ORDER BY created_at,id', (row['id'],))]
        return rows

    def enqueue(self, cid, content, request_id, settings, retry=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT id,conversation_id FROM attempts WHERE request_id=?', (request_id,)).fetchone()
            if old:
                if old['conversation_id'] != cid:
                    raise ValueError('다른 대화에서 사용된 request ID입니다.')
                return self.attempt(old['id']), False
            if not db.execute('SELECT id FROM conversations WHERE id=?', (cid,)).fetchone():
                raise KeyError(cid)
            if db.execute("SELECT id FROM attempts WHERE conversation_id=? AND status IN ('queued','streaming')", (cid,)).fetchone():
                raise ValueError('이 대화는 이미 응답 생성 중입니다.')
            if retry:
                original = db.execute('SELECT message_id FROM attempts WHERE id=? AND conversation_id=?', (retry, cid)).fetchone()
                if not original:
                    raise ValueError('재시도할 응답을 찾을 수 없습니다.')
                mid = original['message_id']
                latest = db.execute('SELECT id FROM messages WHERE conversation_id=? ORDER BY created_at DESC,id DESC LIMIT 1', (cid,)).fetchone()
                if latest['id'] != mid:
                    raise ValueError('가장 최근 메시지만 재시도할 수 있습니다.')
            else:
                mid = uid()
                db.execute('INSERT INTO messages VALUES(?,?,?,?)', (mid, cid, content, now()))
                db.execute("UPDATE conversations SET title=CASE WHEN title='새 대화' THEN ? ELSE title END WHERE id=?", (content[:60], cid))
            aid, at = uid(), now()
            db.execute('INSERT INTO attempts(id,conversation_id,message_id,request_id,settings,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (aid, cid, mid, request_id, json.dumps(settings), 'queued', at, at))
            db.execute('UPDATE conversations SET updated_at=? WHERE id=?', (at, cid))
        return self.attempt(aid), True

    def history(self, aid):
        attempt = self.attempt(aid)
        result = []
        for row in self.messages(attempt['conversation_id']):
            result.append({'role': 'user', 'content': row['content']})
            if row['id'] == attempt['message_id']:
                break
            complete = [r for r in row['attempts'] if r['status'] == 'completed']
            if complete:
                result.append({'role': 'assistant', 'content': complete[-1]['text']})
        return result

    def emit(self, aid, kind, data):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM attempts WHERE id=?', (aid,)).fetchone()
            if not row:
                return
            updates = {'updated_at': now()}
            if kind == 'delta':
                updates.update(text=row['text'] + data['text'], status='streaming')
            elif kind == 'answer' and data.get('text'):
                updates['text'] = data['text']
            elif kind == 'provider':
                updates.update(provider=json.dumps(data), status='streaming')
            elif kind == 'usage':
                updates['usage'] = json.dumps(data)
            elif kind == 'search':
                found = json.loads(row['citations'])
                seen = {r['url'] for r in found}
                for result in data.get('item', {}).get('results') or []:
                    url = result.get('url', '')
                    if urlparse(url).scheme in ('http', 'https') and urlparse(url).hostname and url not in seen:
                        found.append({'url': url, 'title': result.get('title') or urlparse(url).netloc,
                                      'searched_at': now(), 'published_at': result.get('published_at')})
                        seen.add(url)
                updates['citations'] = json.dumps(found)
                updates['search_count'] = row['search_count'] + (1 if data['status'] == '검색 중' else 0)
            elif kind == 'done':
                found = json.loads(row['citations'])
                seen = {r['url'] for r in found}
                found.extend(c for c in citations(row['text']) if c['url'] not in seen)
                updates.update(status=data['status'], error=data.get('error'), citations=json.dumps(found))
                settings = json.loads(row['settings'])
                if data['status'] == 'completed' and settings['search'] == 'on' and row['search_count'] == 0:
                    updates.update(status='failed', error='검색이 실행되지 않았습니다. 검색을 재시도하거나 검색 끄기로 답변받으세요.')
                    data = {'status': 'failed', 'error': updates['error']}
            db.execute('UPDATE attempts SET ' + ','.join(k + '=?' for k in updates) + ' WHERE id=?', (*updates.values(), aid))
            db.execute('INSERT INTO events(attempt_id,type,data) VALUES(?,?,?)', (aid, kind, json.dumps(data)))
            # A cumulative notification replaces the outbox record, never adds it.
            updated = db.execute('SELECT * FROM attempts WHERE id=?', (aid,)).fetchone()
            if json.loads(updated['provider']).get('turn_id'):
                usage = json.loads(updated['usage']) if updated['usage'] else {}
                last = usage.get('total') or {}
                info = json.loads(updated['provider'])
                settings = json.loads(updated['settings'])
                event = {**info, 'event_id': 'chat:' + aid, 'application': 'workbench-chat',
                         'attempt_id': aid, 'account_id': settings['account_id'],
                         'provider_account_id': settings['provider_account_id'],
                         'recorded_at': now(), 'execution_started_at': row['created_at'],
                         'execution_completed_at': now(), 'source': 'chat-outbox',
                         'status': updated['status'], 'usage_pending': not bool(updated['usage']), 'input_tokens': last.get('inputTokens', 0),
                         'cached_input_tokens': last.get('cachedInputTokens', 0),
                         'output_tokens': last.get('outputTokens', 0), 'reasoning_output_tokens': last.get('reasoningOutputTokens', 0),
                         'total_tokens': last.get('totalTokens', 0)}
                db.execute('INSERT OR REPLACE INTO usage_outbox VALUES(?,?)', (aid, json.dumps(event)))
        with self.wake:
            self.wake.notify_all()

    def events(self, aid, after):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT id,type,data FROM events WHERE attempt_id=? AND id>? ORDER BY id', (aid, after))]

    def settings(self, value=None):
        with self.db() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(value),))
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            return json.loads(row['value']) if row else {}

    def usage(self):
        with self.db() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT event FROM usage_outbox')]
        return {'total_tokens': sum(e['total_tokens'] for e in rows), 'attempts': len(rows), 'pending_attempts': sum(bool(e.get('usage_pending')) for e in rows),
                'last_observed_at': max((e['recorded_at'] for e in rows), default=None),
                'status': '잠정 관측치 · 공통 수집기에서 rollout으로 확정'}
