"""Trusted synthetic issue-import target. Python 3.11+, SQLite, no network.

An import batch, its progress checkpoint, and its event commit atomically.
Cancellation and processing serialize through SQLite's BEGIN IMMEDIATE.
This small fixture is not the coding-agent service or a security boundary.
"""
import base64
import csv
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager


class Conflict(ValueError):
    """An idempotency key has already been used for a different input."""


class InvalidCursor(ValueError):
    pass


class IssueTracker:
    MAX_CSV_BYTES = 65536
    MAX_ROWS = 1000

    def __init__(self, database=":memory:"):
        self.db = sqlite3.connect(database, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY, tenant TEXT NOT NULL,
                request_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','complete','cancelled')),
                total INTEGER NOT NULL, processed INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant, request_key), CHECK(processed BETWEEN 0 AND total));
            CREATE TABLE IF NOT EXISTS staged_rows (
                job_id INTEGER NOT NULL REFERENCES jobs(id), position INTEGER NOT NULL,
                issue_id TEXT NOT NULL, title TEXT NOT NULL,
                PRIMARY KEY(job_id, position));
            CREATE TABLE IF NOT EXISTS issues (
                tenant TEXT NOT NULL, issue_id TEXT NOT NULL, title TEXT NOT NULL,
                PRIMARY KEY(tenant, issue_id));
            CREATE TABLE IF NOT EXISTS events (
                job_id INTEGER NOT NULL REFERENCES jobs(id), seq INTEGER NOT NULL,
                kind TEXT NOT NULL, processed INTEGER NOT NULL,
                PRIMARY KEY(job_id, seq));
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def _identity(value):
        if not isinstance(value, str) or not value or len(value) > 100:
            raise ValueError("identity must be a nonempty string of at most 100 characters")

    @classmethod
    def _parse(cls, text):
        if not isinstance(text, str) or len(text.encode("utf-8")) > cls.MAX_CSV_BYTES:
            raise ValueError("CSV must be bounded UTF-8 text")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != ["issue_id", "title"]:
            raise ValueError("CSV headers must be issue_id,title")
        result = []
        for row in reader:
            if None in row or not row["issue_id"] or not row["title"]:
                raise ValueError("each row needs exactly a nonempty issue_id and title")
            if len(row["issue_id"]) > 100 or len(row["title"]) > 1000:
                raise ValueError("CSV field limit exceeded")
            result.append((row["issue_id"], row["title"]))
            if len(result) > cls.MAX_ROWS:
                raise ValueError("CSV row limit exceeded")
        return result

    def _job(self, tenant, job_id):
        self._identity(tenant)
        if type(job_id) is not int or job_id <= 0:
            raise ValueError("invalid import identity")
        row = self.db.execute("SELECT * FROM jobs WHERE tenant=? AND id=?", (tenant, job_id)).fetchone()
        if row is None:
            raise KeyError("import not found")
        return dict(row)

    def _event(self, job_id, kind, processed):
        sequence = self.db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE job_id=?", (job_id,)).fetchone()[0]
        self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (job_id, sequence, kind, processed))

    def submit_import(self, tenant, request_key, csv_text):
        self._identity(tenant)
        self._identity(request_key)
        rows = self._parse(csv_text)
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        with self._transaction():
            previous = self.db.execute("SELECT * FROM jobs WHERE tenant=? AND request_key=?", (tenant, request_key)).fetchone()
            if previous is not None:
                if previous["payload_hash"] != digest:
                    raise Conflict("same tenant/key with changed payload")
                return previous["id"]
            status = "queued" if rows else "complete"
            job_id = self.db.execute("INSERT INTO jobs(tenant,request_key,payload_hash,status,total) VALUES(?,?,?,?,?)", (tenant, request_key, digest, status, len(rows))).lastrowid
            self.db.executemany("INSERT INTO staged_rows VALUES(?,?,?,?)", ((job_id, index, issue_id, title) for index, (issue_id, title) in enumerate(rows)))
            self._event(job_id, "submitted", 0)
            return job_id

    def status(self, tenant, job_id):
        return self._job(tenant, job_id)

    def process_batch(self, tenant, job_id, batch_size=2, *, crash_before_commit=False):
        if type(batch_size) is not int or not 1 <= batch_size <= self.MAX_ROWS:
            raise ValueError("invalid batch size")
        with self._transaction():
            job = self._job(tenant, job_id)
            if job["status"] in ("complete", "cancelled"):
                return job
            start = max(0, job["processed"] - 1)
            rows = self.db.execute("SELECT * FROM staged_rows WHERE job_id=? AND position>=? ORDER BY position LIMIT ?", (job_id, start, batch_size)).fetchall()
            for row in rows:
                self.db.execute("INSERT INTO issues VALUES(?,?,?) ON CONFLICT(tenant,issue_id) DO NOTHING", (tenant, row["issue_id"], row["title"]))
            processed = job["processed"] + len(rows)
            status = "complete" if processed == job["total"] else "running"
            self.db.execute("UPDATE jobs SET processed=?,status=? WHERE id=?", (processed, status, job_id))
            self._event(job_id, "batch", processed)
            if crash_before_commit:
                raise RuntimeError("injected crash before commit")
            return self._job(tenant, job_id)

    def cancel(self, tenant, job_id):
        with self._transaction():
            job = self._job(tenant, job_id)
            if job["status"] not in ("complete", "cancelled"):
                self.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
                self._event(job_id, "cancelled", job["processed"])
            return self._job(tenant, job_id)

    def list_issues(self, tenant):
        self._identity(tenant)
        return [dict(row) for row in self.db.execute("SELECT issue_id,title FROM issues WHERE tenant=? ORDER BY issue_id", (tenant,))]

    @staticmethod
    def _cursor(tenant, job_id, seq):
        raw = json.dumps([1, tenant, job_id, seq], separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def progress(self, tenant, job_id, cursor=None, limit=2):
        self._job(tenant, job_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid page size")
        after = 0
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or len(cursor) > 1024:
                    raise ValueError("invalid cursor size")
                version, owner, import_id, after = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if type(version) is not int or type(import_id) is not int or (version, owner, import_id) != (1, tenant, job_id):
                    raise ValueError("cursor belongs to a different import")
                if type(after) is not int or after < 0:
                    raise ValueError("invalid cursor sequence")
                max_seq = self.db.execute("SELECT MAX(seq) FROM events WHERE job_id=?", (job_id,)).fetchone()[0]
                if after > max_seq:
                    raise ValueError("cursor is beyond committed progress")
            except (ValueError, TypeError, UnicodeError) as error:
                raise InvalidCursor("malformed or cross-import cursor") from error
        rows = [dict(row) for row in self.db.execute("SELECT seq,kind,processed FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT ?", (job_id, after, limit))]
        next_seq = rows[-1]["seq"] if rows else after
        return {"events": rows, "cursor": self._cursor(tenant, job_id, next_seq)}
