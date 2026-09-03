import json
import os
import sqlite3
import threading
import time


class RouteCache:
    def __init__(self, db_path="data/yaobao.sqlite3", max_routes=20):
        self.db_path = db_path
        self.max_routes = max_routes
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._conn() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            db.commit()

    def put(self, key, payload):
        with self._lock, self._conn() as db:
            db.execute("INSERT INTO routes(cache_key,payload,created_at) VALUES(?,?,?)",
                       (key, json.dumps(payload, ensure_ascii=False), time.time()))
            db.execute("""
                DELETE FROM routes WHERE id NOT IN
                (SELECT id FROM routes ORDER BY created_at DESC LIMIT ?)
            """, (self.max_routes,))
            db.commit()

    def get(self, key):
        with self._lock, self._conn() as db:
            row = db.execute(
                "SELECT payload FROM routes WHERE cache_key=? ORDER BY created_at DESC LIMIT 1",
                (key,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def latest(self):
        with self._lock, self._conn() as db:
            row = db.execute(
                "SELECT payload FROM routes ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return json.loads(row[0]) if row else None
