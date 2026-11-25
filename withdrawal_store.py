
import sqlite3
import secrets
import string
import time
from contextlib import closing

MAX_SQLITE_INT = 2**63 - 1
MAX_WALLET_LENGTH = 2048
PUBLIC_TAG_ALPHABET = string.ascii_uppercase + string.digits
PUBLIC_TAG_LENGTH = 6


class InsufficientFunds(Exception):
    pass


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute('PRAGMA busy_timeout = 10000')
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn):
    
    conn.execute('''CREATE TABLE IF NOT EXISTS withdrawal_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        amount_microusd INTEGER NOT NULL CHECK(amount_microusd > 0),
        wallet TEXT NOT NULL CHECK(length(wallet) BETWEEN 1 AND 2048),
        wallet_raw TEXT NOT NULL CHECK(length(wallet_raw) BETWEEN 1 AND 2048),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','paid','rejected')),
        created_at INTEGER NOT NULL,
        paid_at INTEGER,
        admin_id INTEGER,
        admin_notified INTEGER NOT NULL DEFAULT 0 CHECK(admin_notified IN (0,1)),
        user_notified INTEGER NOT NULL DEFAULT 0 CHECK(user_notified IN (0,1))
    )''')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(withdrawal_requests)')}
    if 'public_tag' not in columns:
        conn.execute('ALTER TABLE withdrawal_requests ADD COLUMN public_tag TEXT')
    conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_withdrawal_public_tag
                    ON withdrawal_requests(public_tag) WHERE public_tag IS NOT NULL''')
    for row in conn.execute('SELECT id FROM withdrawal_requests WHERE public_tag IS NULL ORDER BY id').fetchall():
        while True:
            tag = _new_public_tag()
            try:
                conn.execute('UPDATE withdrawal_requests SET public_tag=? WHERE id=?', (tag, row[0]))
                break
            except sqlite3.IntegrityError:
                continue
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_withdrawal_status_created
                    ON withdrawal_requests(status, created_at, id)''')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_withdrawal_user
                    ON withdrawal_requests(user_id, id)''')


def _as_dict(row):
    return dict(row) if row is not None else None


def _new_public_tag():
    return ''.join(secrets.choice(PUBLIC_TAG_ALPHABET) for _ in range(PUBLIC_TAG_LENGTH))


def create_request(db_path, user_id, amount_microusd, wallet, wallet_raw):
    if isinstance(amount_microusd, bool) or not isinstance(amount_microusd, int) or not 0 < amount_microusd <= MAX_SQLITE_INT:
        raise ValueError('amount_microusd must be a positive SQLite integer')
    for name, value in (('wallet', wallet), ('wallet_raw', wallet_raw)):
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_WALLET_LENGTH:
            raise ValueError(f'{name} must be nonempty and at most {MAX_WALLET_LENGTH} characters')
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?',
                               (amount_microusd, user_id, amount_microusd))
            if cur.rowcount != 1:
                raise InsufficientFunds('insufficient funds or user does not exist')
            created_at = int(time.time())
            while True:
                tag = _new_public_tag()
                try:
                    cur = conn.execute('''INSERT INTO withdrawal_requests
                        (user_id, amount_microusd, wallet, wallet_raw, created_at, public_tag)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                        (user_id, amount_microusd, wallet, wallet_raw, created_at, tag))
                    break
                except sqlite3.IntegrityError as exc:
                    if 'withdrawal_requests.public_tag' not in str(exc):
                        raise
            return _as_dict(conn.execute('SELECT * FROM withdrawal_requests WHERE id = ?',
                                         (cur.lastrowid,)).fetchone())


def get_request(db_path, request_id):
    with closing(_connect(db_path)) as conn:
        return _as_dict(conn.execute('SELECT * FROM withdrawal_requests WHERE id = ?',
                                      (request_id,)).fetchone())


def mark_paid(db_path, request_id, admin_id):
    
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM withdrawal_requests WHERE id = ?',
                               (request_id,)).fetchone()
            if row is None:
                return 'not_found', None
            if row['status'] != 'pending':
                return row['status'], dict(row)
            now = int(time.time())
            cur = conn.execute('''UPDATE withdrawal_requests SET status='paid', paid_at=?, admin_id=?
                                  WHERE id=? AND status='pending' ''', (now, admin_id, request_id))
            if cur.rowcount != 1:
                current = conn.execute('SELECT * FROM withdrawal_requests WHERE id = ?',
                                       (request_id,)).fetchone()
                return (current['status'], dict(current)) if current else ('not_found', None)
            updated = conn.execute('''UPDATE users SET withdrawn = withdrawn + ?
                WHERE user_id = ? AND withdrawn <= ?''',
                (row['amount_microusd'], row['user_id'], MAX_SQLITE_INT - row['amount_microusd']))
            if updated.rowcount != 1:
                raise OverflowError('withdrawn total cannot be recorded safely')
            result = conn.execute('SELECT * FROM withdrawal_requests WHERE id = ?',
                                  (request_id,)).fetchone()
            return 'paid', dict(result)


def pending_notifications(db_path, kind):
    if kind not in ('admin', 'user'):
        raise ValueError("kind must be 'admin' or 'user'")
    status = 'pending' if kind == 'admin' else 'paid'
    flag = 'admin_notified' if kind == 'admin' else 'user_notified'
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(f'''SELECT * FROM withdrawal_requests
            WHERE status=? AND {flag}=0 ORDER BY created_at, id''', (status,)).fetchall()
        return [dict(row) for row in rows]


def mark_notification(db_path, request_id, kind):
    if kind not in ('admin', 'user'):
        raise ValueError("kind must be 'admin' or 'user'")
    status = 'pending' if kind == 'admin' else 'paid'
    flag = 'admin_notified' if kind == 'admin' else 'user_notified'
    with closing(_connect(db_path)) as conn:
        with conn:
            cur = conn.execute(f'''UPDATE withdrawal_requests SET {flag}=1
                WHERE id=? AND status=? AND {flag}=0''', (request_id, status))
            return cur.rowcount == 1
