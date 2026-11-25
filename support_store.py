
import sqlite3


def init_schema(conn):
    
    conn.execute('''CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed')),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )''')
    conn.execute('''CREATE INDEX IF NOT EXISTS support_tickets_user_status
                    ON support_tickets(user_id, status, id DESC)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS support_ticket_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
        sender_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        text TEXT NOT NULL,
        telegram_message_id INTEGER,
        media_kind TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )''')
    conn.execute('''CREATE INDEX IF NOT EXISTS support_ticket_messages_thread
                    ON support_ticket_messages(ticket_id, id)''')


def _ticket(row):
    return dict(zip(('id', 'user_id', 'status', 'created_at', 'updated_at'), row)) if row else None


def create_ticket(db, user_id):
    
    cursor = db.execute('INSERT INTO support_tickets (user_id) VALUES (?)', (user_id,))
    return cursor.lastrowid


def get_ticket(db, ticket_id, user_id=None):
    
    row = db.execute('''SELECT id, user_id, status, created_at, updated_at
                        FROM support_tickets WHERE id = ?''', (ticket_id,)).fetchone()
    ticket = _ticket(row)
    if ticket is None or (user_id is not None and ticket['user_id'] != user_id):
        return None
    rows = db.execute('''SELECT id, sender_id, role, text, telegram_message_id, media_kind, created_at
                         FROM support_ticket_messages WHERE ticket_id = ? ORDER BY id''',
                      (ticket_id,)).fetchall()
    keys = ('id', 'sender_id', 'role', 'text', 'telegram_message_id', 'media_kind', 'created_at')
    ticket['messages'] = [dict(zip(keys, message)) for message in rows]
    return ticket


def list_tickets(db, limit=50):
    
    limit = max(1, min(int(limit), 500))
    rows = db.execute('''SELECT id, user_id, status, created_at, updated_at
                         FROM support_tickets ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()
    return [_ticket(row) for row in rows]


def add_message(db, ticket_id, sender_id, role, text, telegram_message_id=None, media_kind=None):
    
    if not isinstance(text, str):
        raise TypeError('text must be a string')
    cursor = db.execute('''INSERT INTO support_ticket_messages
        (ticket_id, sender_id, role, text, telegram_message_id, media_kind)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (ticket_id, sender_id, role, text, telegram_message_id, media_kind))
    db.execute("UPDATE support_tickets SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
               (ticket_id,))
    return cursor.lastrowid


def set_ticket_status(db, ticket_id, status):
    
    if status not in ('open', 'closed'):
        raise ValueError("status must be 'open' or 'closed'")
    cursor = db.execute("UPDATE support_tickets SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                        (status, ticket_id))
    return cursor.rowcount == 1


def close_ticket(db, ticket_id):
    return set_ticket_status(db, ticket_id, 'closed')


def reopen_ticket(db, ticket_id):
    return set_ticket_status(db, ticket_id, 'open')
