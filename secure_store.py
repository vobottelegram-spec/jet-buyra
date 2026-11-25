"""Encryption at rest for Telegram session strings and 2FA passwords.

Keys come from the DATA_KEYS env var (comma separated Fernet keys, first = current,
others = old keys still accepted for decryption/rotation). DATA_KEY is accepted as an
alias for a single key. Without a key the bot refuses to start (fail closed).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

PREFIX = "enc1:"
_cached = None


class KeyError_(RuntimeError):
    pass


def _load():
    global _cached
    raw = os.getenv("DATA_KEYS") or os.getenv("DATA_KEY") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise KeyError_("DATA_KEYS is not set. Generate one with: "
                        "python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\"")
    try:
        fernets = [Fernet(k.encode()) for k in keys]
    except Exception as exc:  # malformed key
        raise KeyError_("DATA_KEYS contains an invalid Fernet key") from exc
    if _cached is None or _cached[0] != tuple(keys):
        _cached = (tuple(keys), MultiFernet(fernets))
    return _cached[1]


def require_key():
    _load()


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value):
    if value is None or value == "":
        return value
    if is_encrypted(value):
        return value
    return PREFIX + _load().encrypt(value.encode()).decode()


def decrypt(value):
    """Return plaintext. Legacy plaintext values (no prefix) are returned unchanged."""
    if value is None or value == "" or not is_encrypted(value):
        return value
    try:
        return _load().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise KeyError_("cannot decrypt stored value: wrong or missing key") from exc


def migrate_plaintext(db_path):
    """Encrypt any plaintext session_string/twofa already in the DB. Returns rows changed."""
    _load()
    changed = 0
    with closing(sqlite3.connect(db_path, timeout=30)) as conn:
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id, session_string, twofa FROM accounts").fetchall()
        for rid, sess, twofa in rows:
            new_sess = encrypt(sess) if sess and not is_encrypted(sess) else sess
            new_twofa = encrypt(twofa) if twofa and not is_encrypted(twofa) else twofa
            if new_sess != sess or new_twofa != twofa:
                conn.execute("UPDATE accounts SET session_string=?, twofa=? WHERE id=?",
                             (new_sess, new_twofa, rid))
                changed += 1
        conn.commit()
        if changed:
            # drop leftover plaintext from free pages / WAL
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
    return changed


def rotate(db_path):
    """Re-encrypt every value with the current (first) key. Old keys must still be listed."""
    f = _load()
    changed = 0
    with closing(sqlite3.connect(db_path, timeout=30)) as conn:
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("BEGIN IMMEDIATE")
        for rid, sess, twofa in conn.execute("SELECT id, session_string, twofa FROM accounts").fetchall():
            def r(v):
                if not is_encrypted(v):
                    return v
                return PREFIX + f.rotate(v[len(PREFIX):].encode()).decode()
            ns, nt = r(sess), r(twofa)
            if (ns, nt) != (sess, twofa):
                conn.execute("UPDATE accounts SET session_string=?, twofa=? WHERE id=?", (ns, nt, rid))
                changed += 1
        conn.commit()
        if changed:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
    return changed
