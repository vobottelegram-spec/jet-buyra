
import sqlite3
import time
from contextlib import closing

LANGUAGES = frozenset(('fa', 'en', 'ru', 'zh', 'ar'))
USER_COLUMNS = ('user_id', 'first_started_at', 'language', 'numbers_sold', 'balance', 'withdrawn',
                'username', 'full_name', 'is_banned')


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute('PRAGMA busy_timeout = 10000')
    return conn


def init_schema(conn):
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_started_at INTEGER,
        language TEXT CHECK(language IS NULL OR language IN ('fa','en','ru','zh','ar')),
        numbers_sold INTEGER NOT NULL DEFAULT 0 CHECK(numbers_sold >= 0),
        balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
        withdrawn INTEGER NOT NULL DEFAULT 0 CHECK(withdrawn >= 0),
        username TEXT,
        full_name TEXT,
        is_banned INTEGER NOT NULL DEFAULT 0 CHECK(is_banned IN (0, 1))
    )''')
                                                                               
    columns = {row[1] for row in conn.execute('PRAGMA table_info(users)')}
    if 'username' not in columns:
        conn.execute('ALTER TABLE users ADD COLUMN username TEXT')
    if 'full_name' not in columns:
        conn.execute('ALTER TABLE users ADD COLUMN full_name TEXT')
    if 'is_banned' not in columns:
        conn.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0 CHECK(is_banned IN (0, 1))')
    conn.execute('''CREATE TABLE IF NOT EXISTS app_metadata (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )''')
    unit = conn.execute("SELECT value FROM app_metadata WHERE key = 'balance_unit'").fetchone()
    if unit is None:
        nonzero = conn.execute('SELECT COUNT(*) FROM users WHERE balance != 0 OR withdrawn != 0').fetchone()[0]
        if nonzero:
            raise RuntimeError('Cannot assign currency units to existing nonzero user balances automatically')
        conn.execute("INSERT INTO app_metadata (key, value) VALUES ('balance_unit', 'USD_MICRO')")
    elif unit[0] != 'USD_MICRO':
        raise RuntimeError('Unexpected user balance unit')
    conn.execute('''INSERT OR IGNORE INTO users (user_id)
                    SELECT DISTINCT seller_id FROM accounts WHERE seller_id IS NOT NULL''')
                                                                                   
                                                                     
    conn.execute('''UPDATE users SET numbers_sold = (
        SELECT COUNT(*) FROM accounts
        WHERE accounts.seller_id = users.user_id AND accounts.status = 'sold'
    )''')


def _get(conn, user_id):
    row = conn.execute('''SELECT user_id, first_started_at, language,
                          numbers_sold, balance, withdrawn, username, full_name, is_banned
                          FROM users WHERE user_id = ?''',
                       (user_id,)).fetchone()
    return dict(zip(USER_COLUMNS, row)) if row is not None else None


def _ensure(conn, user_id, started=False):
    timestamp = int(time.time()) if started else None
    conn.execute('INSERT OR IGNORE INTO users (user_id, first_started_at) VALUES (?, ?)',
                 (user_id, timestamp))
    if started:
        conn.execute('''UPDATE users SET first_started_at = COALESCE(first_started_at, ?)
                        WHERE user_id = ?''', (timestamp, user_id))


def ensure_user(db_path, user_id, started=False, username=None, full_name=None):
    
    with closing(_connect(db_path)) as conn:
        with conn:
            _ensure(conn, user_id, started)
            if username is not None or full_name is not None:
                conn.execute('''UPDATE users SET
                    username = COALESCE(?, username), full_name = COALESCE(?, full_name)
                    WHERE user_id = ?''', (username, full_name, user_id))
            return _get(conn, user_id)


def get_user(db_path, user_id):
    with closing(_connect(db_path)) as conn:
        return _get(conn, user_id)


def set_user_banned(db_path, user_id, banned):
    
    if banned not in (0, 1, False, True):
        raise ValueError('banned must be a boolean or 0/1')
    with closing(_connect(db_path)) as conn:
        with conn:
            _ensure(conn, user_id)
            conn.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', (int(banned), user_id))
            return _get(conn, user_id)


def ban_user(db_path, user_id):
    return set_user_banned(db_path, user_id, True)


def unban_user(db_path, user_id):
    return set_user_banned(db_path, user_id, False)


def search_users(db_path, term, limit=50):
    
    if term is None or not str(term).strip():
        return []
    limit = max(1, min(int(limit), 100))
    term = str(term).strip()
    try:
        user_id = int(term)
    except ValueError:
        user_id = None
    with closing(_connect(db_path)) as conn:
        if user_id is not None:
            rows = conn.execute('''SELECT user_id, username, full_name, is_banned,
                                  numbers_sold, balance, withdrawn, first_started_at, language FROM users
                                  WHERE user_id = ? LIMIT ?''', (user_id, limit)).fetchall()
        else:
            pattern = '%' + term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            rows = conn.execute('''SELECT user_id, username, full_name, is_banned,
                                  numbers_sold, balance, withdrawn, first_started_at, language FROM users
                                  WHERE username LIKE ? ESCAPE '\\' COLLATE NOCASE
                                     OR full_name LIKE ? ESCAPE '\\' COLLATE NOCASE
                                  ORDER BY user_id LIMIT ?''', (pattern, pattern, limit)).fetchall()
    keys = ('user_id', 'username', 'full_name', 'is_banned', 'numbers_sold', 'balance', 'withdrawn',
            'first_started_at', 'language')
    return [dict(zip(keys, row)) for row in rows]


def list_users(db_path, page=0, page_size=10):
    
    page_size = max(1, min(int(page_size), 50))
    page = max(0, int(page))
    with closing(_connect(db_path)) as conn:
        total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page >= total_pages:
            page = total_pages - 1
        rows = conn.execute('''SELECT user_id, username, full_name, is_banned,
                              numbers_sold, balance, withdrawn, first_started_at, language
                              FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?''',
                            (page_size, page * page_size)).fetchall()
    keys = ('user_id', 'username', 'full_name', 'is_banned', 'numbers_sold', 'balance', 'withdrawn',
            'first_started_at', 'language')
    return [dict(zip(keys, row)) for row in rows], total, page, total_pages


def set_language(db_path, user_id, language):
    if language not in LANGUAGES:
        raise ValueError('Unsupported language')
    with closing(_connect(db_path)) as conn:
        with conn:
            _ensure(conn, user_id)
            conn.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
            return _get(conn, user_id)


def set_account_status(db_path, account_id, status):
    
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT seller_id, status FROM accounts WHERE id = ?',
                               (account_id,)).fetchone()
            if row is None:
                return False
            seller_id, previous_status = row
            _ensure(conn, seller_id)
            conn.execute('UPDATE accounts SET status = ? WHERE id = ?', (status, account_id))
            conn.execute('''UPDATE users SET numbers_sold = (
                SELECT COUNT(*) FROM accounts WHERE seller_id = ? AND status = 'sold'
            ) WHERE user_id = ?''', (seller_id, seller_id))
            return previous_status != status
