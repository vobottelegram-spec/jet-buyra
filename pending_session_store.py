
from __future__ import annotations

import sqlite3
import time
from contextlib import closing

_DELAY = 24 * 60 * 60


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _now(value):
    return int(time.time()) if value is None else int(value)


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS pending_session_jobs (
        account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
        seller_id INTEGER NOT NULL,
        tg_user_id INTEGER NOT NULL,
        due_at INTEGER NOT NULL,
        next_attempt_at INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','done','cancelled','failed')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_session_jobs_due ON pending_session_jobs(status,next_attempt_at)")


def _eligible_sql(extra):
    return f"""SELECT a.id AS account_id,a.seller_id,a.tg_user_id,a.phone,
        a.session_string,a.created_at,o.created_at AS offer_created_at
        FROM accounts a JOIN sale_offers o ON o.account_id=a.id AND o.seller_id=a.seller_id
        WHERE a.id=? AND a.seller_id=? AND a.status='pending'
          AND a.tg_user_id IS NOT NULL AND a.tg_user_id>0
          AND a.session_string IS NOT NULL AND length(trim(a.session_string))>0
          AND NOT EXISTS (SELECT 1 FROM sale_credits c WHERE c.account_id=a.id OR c.tg_user_id=a.tg_user_id)
          {extra}"""


def schedule_in_connection(conn, account_id, seller_id, now=None):
    
    stamp = _now(now)
    cursor = conn.execute(_eligible_sql(""), (account_id, seller_id))
    raw = cursor.fetchone()
    if raw is None:
        return None
    row = dict(zip((column[0] for column in cursor.description), raw))
    due = max(int(row['created_at']), int(row['offer_created_at']), stamp) + _DELAY
    conn.execute("""INSERT OR IGNORE INTO pending_session_jobs
        (account_id,seller_id,tg_user_id,due_at,next_attempt_at,status,attempts,last_error)
        VALUES(?,?,?,?,?,'pending',0,NULL)""", (account_id,seller_id,row['tg_user_id'],due,due))
    return _job(conn, account_id)


def schedule(db_path, account_id, seller_id, now=None):
    with closing(_connect(db_path)) as c:
        try:
            c.execute("BEGIN IMMEDIATE")
            job = schedule_in_connection(c, account_id, seller_id, now)
            c.commit()
            return job
        except BaseException:
            c.rollback()
            raise


def _job(c, account_id):
    cursor = c.execute("SELECT * FROM pending_session_jobs WHERE account_id=?", (account_id,))
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row else None


def get_job(db_path, account_id):
    with closing(_connect(db_path)) as c:
        return _job(c, account_id)


def _eligible_jobs(c, where, args, stamp, limit):
    rows = c.execute(f"""SELECT j.account_id,j.seller_id,j.tg_user_id,j.due_at,
        j.next_attempt_at,j.status,j.attempts,j.last_error,
        a.phone,a.session_string,a.created_at,o.created_at AS offer_created_at
        FROM pending_session_jobs j JOIN accounts a ON a.id=j.account_id
        JOIN sale_offers o ON o.account_id=a.id AND o.seller_id=a.seller_id
        WHERE {where} AND j.status='pending' AND j.due_at<=? AND j.next_attempt_at<=?
          AND a.seller_id=j.seller_id AND a.tg_user_id=j.tg_user_id
          AND a.status='pending' AND a.tg_user_id>0
          AND a.session_string IS NOT NULL AND length(trim(a.session_string))>0
          AND NOT EXISTS (SELECT 1 FROM sale_credits c WHERE c.account_id=a.id OR c.tg_user_id=a.tg_user_id)
        ORDER BY j.next_attempt_at,j.account_id LIMIT ?""", (*args,stamp,stamp,limit)).fetchall()
    return [dict(r) for r in rows]


def due_jobs(db_path, now=None, limit=10):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError('limit must be a positive integer')
    with closing(_connect(db_path)) as c:
        return _eligible_jobs(c, '1=1', (), _now(now), limit)


def eligible_job(db_path, job_id, now=None):
    with closing(_connect(db_path)) as c:
        rows = _eligible_jobs(c, 'j.account_id=?', (job_id,), _now(now), 1)
        return rows[0] if rows else None


def reschedule(db_path, job_id, next_attempt_at, last_error=None):
    with closing(_connect(db_path)) as c, c:
        cur = c.execute("""UPDATE pending_session_jobs SET attempts=attempts+1,
            next_attempt_at=MAX(due_at,?),last_error=? WHERE account_id=? AND status='pending'""",
            (int(next_attempt_at), last_error, job_id))
        return cur.rowcount == 1


def finish(db_path, job_id, status='done', last_error=None):
    if status not in ('done', 'cancelled', 'failed'):
        raise ValueError('Invalid terminal job status')
    return _set_status(db_path, job_id, status, last_error)


def cancel(db_path, job_id):
    return _set_status(db_path, job_id, 'cancelled')


def cancel_seller(db_path, seller_id):
    
    with closing(_connect(db_path)) as conn, conn:
        result = conn.execute("UPDATE pending_session_jobs SET status='cancelled' WHERE seller_id=? AND status='pending'", (seller_id,))
        return result.rowcount


def _set_status(db_path, job_id, status, last_error=None):
    with closing(_connect(db_path)) as c, c:
        cur = c.execute("UPDATE pending_session_jobs SET status=?,last_error=? WHERE account_id=? AND status='pending'", (status,last_error,job_id))
        return cur.rowcount == 1
