
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

MAX_AMOUNT = Decimal("1000000000000")
MAX_SQLITE_INT = 2**63 - 1
CURRENCIES = frozenset(("USD", "IRT", "IRR"))
CREDIT_COLUMNS = ("account_id", "seller_id", "tg_user_id", "region", "price_country",
                  "source_amount", "source_currency", "usd_micros",
                  "rate_toman_per_usd", "rate_updated_utc", "credited_at")


class DuplicateAccountError(ValueError):
    pass


def init_schema(conn):
    
    conn.execute('''CREATE TABLE IF NOT EXISTS sale_credits (
        account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
        seller_id INTEGER NOT NULL,
        tg_user_id INTEGER NOT NULL UNIQUE,
        region TEXT NULL,
        price_country TEXT NOT NULL,
        source_amount TEXT NOT NULL,
        source_currency TEXT NOT NULL CHECK(source_currency IN ('USD','IRT','IRR')),
        usd_micros INTEGER NOT NULL CHECK(usd_micros > 0),
        rate_toman_per_usd TEXT NULL,
        rate_updated_utc TEXT NULL,
        credited_at INTEGER NOT NULL,
        seller_notified INTEGER NOT NULL DEFAULT 0 CHECK(seller_notified IN (0,1))
    )''')
    cols = {row[1] for row in conn.execute('PRAGMA table_info(sale_credits)')}
    if 'seller_notified' not in cols:
        conn.execute('ALTER TABLE sale_credits ADD COLUMN seller_notified INTEGER NOT NULL DEFAULT 0')
    conn.execute('''CREATE TABLE IF NOT EXISTS sale_offers (account_id INTEGER PRIMARY KEY REFERENCES accounts(id), seller_id INTEGER NOT NULL, price_country TEXT NOT NULL, region TEXT NULL, source_amount TEXT NOT NULL, source_currency TEXT NOT NULL CHECK(source_currency IN ('USD','IRT','IRR')), usd_micros INTEGER NOT NULL CHECK(usd_micros > 0), rate_toman_per_usd TEXT NULL, rate_updated_utc TEXT NULL, created_at INTEGER NOT NULL)''')


def _decimal(value, name):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"Invalid {name}")
    try:
        d = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {name}") from None
    if not d.is_finite():
        raise ValueError(f"Invalid {name}")
    return d


def _utc(value):
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("Invalid rate_updated_utc")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        raise ValueError("Invalid rate_updated_utc") from None
    if dt.tzinfo is None or dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("rate_updated_utc must be UTC-aware")


def _validate_quote(q):
    if not isinstance(q, dict):
        raise ValueError("quote must be a dict")
    required = ("region", "price_country", "source_amount", "source_currency", "usd_micros",
                "rate_toman_per_usd", "rate_updated_utc")
    if any(k not in q for k in required):
        raise ValueError("Missing quote field")
    if q["region"] is not None and not isinstance(q["region"], str):
        raise ValueError("Invalid region")
    if not isinstance(q["price_country"], str) or not q["price_country"]:
        raise ValueError("Invalid price_country")
    currency = q["source_currency"]
    if currency not in CURRENCIES:
        raise ValueError("Invalid source_currency")
    amount = _decimal(q["source_amount"], "source_amount")
    if amount <= 0 or amount > MAX_AMOUNT:
        raise ValueError("source_amount out of range")
    micros = q["usd_micros"]
    if isinstance(micros, bool) or not isinstance(micros, int) or not 0 < micros <= MAX_SQLITE_INT:
        raise ValueError("Invalid usd_micros")
    rate, stamp = q["rate_toman_per_usd"], q["rate_updated_utc"]
    if currency == "USD":
        if rate is not None or stamp is not None:
            raise ValueError("USD quote must not have an exchange rate")
        if amount * 1_000_000 != micros:
            raise ValueError("USD amount does not match usd_micros")
    else:
        if not isinstance(rate, str):
            raise ValueError("Exchange rate is required")
        if stamp is None:
            raise ValueError("Exchange-rate timestamp is required")
        r = _decimal(rate, "rate_toman_per_usd")
        if r <= 0:
            raise ValueError("Exchange rate must be positive")
        _utc(stamp)
        with localcontext() as ctx:
            ctx.prec = 100
            expected = (amount / r / (10 if currency == "IRR" else 1) * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if expected != micros:
            raise ValueError("Converted amount does not match usd_micros")
    return amount


def store_offer(db_path, account_id, seller_id, quote):
    _validate_quote(quote)
    with closing(sqlite3.connect(db_path, timeout=10)) as c:
        c.execute('PRAGMA busy_timeout=10000')
        try:
            c.execute('BEGIN IMMEDIATE')
            a=c.execute("SELECT seller_id,status FROM accounts WHERE id=?",(account_id,)).fetchone()
            if not a or a != (seller_id,'pending'): raise ValueError('Account missing, wrong owner, or not pending')
            vals=(seller_id,quote['price_country'],quote['region'],quote['source_amount'],quote['source_currency'],quote['usd_micros'],quote['rate_toman_per_usd'],quote['rate_updated_utc'])
            old=c.execute('SELECT seller_id,price_country,region,source_amount,source_currency,usd_micros,rate_toman_per_usd,rate_updated_utc FROM sale_offers WHERE account_id=?',(account_id,)).fetchone()
            if old and tuple(old)!=vals: raise ValueError('Offer is immutable')
            if not old: c.execute('INSERT INTO sale_offers VALUES(?,?,?,?,?,?,?,?,?,?)',(account_id,*vals,int(datetime.now().timestamp())))
            c.commit()
        except BaseException: c.rollback(); raise


def get_offer(db_path, account_id):
    with closing(sqlite3.connect(db_path)) as c:
        c.row_factory=sqlite3.Row
        r=c.execute('SELECT * FROM sale_offers WHERE account_id=?',(account_id,)).fetchone()
        return dict(r) if r else None


def has_credited_account(db_path, tg_user_id):
    
    with closing(sqlite3.connect(db_path, timeout=10)) as conn:
        return conn.execute("SELECT 1 FROM sale_credits WHERE tg_user_id = ? LIMIT 1", (tg_user_id,)).fetchone() is not None


def pending_notifications(db_path):
    with closing(sqlite3.connect(db_path, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''SELECT c.account_id, c.seller_id, c.usd_micros, a.phone
            FROM sale_credits c JOIN accounts a ON a.id = c.account_id
            WHERE c.seller_notified = 0 ORDER BY c.account_id''').fetchall()
        return [dict(row) for row in rows]


def mark_notified(db_path, account_id):
    with closing(sqlite3.connect(db_path, timeout=10)) as conn, conn:
        cur = conn.execute('UPDATE sale_credits SET seller_notified = 1 WHERE account_id = ? AND seller_notified = 0', (account_id,))
        return cur.rowcount == 1


def save_account_with_offer(db_path,seller_id,phone,session_string,twofa,tg_user_id,username,quote,*,schedule_cleanup=False):
    _validate_quote(quote)
    with closing(sqlite3.connect(db_path,timeout=10)) as c:
        try:
            c.execute('BEGIN IMMEDIATE')
                                                                                                   
            if tg_user_id is None or isinstance(tg_user_id, bool) or not isinstance(tg_user_id, int) or tg_user_id <= 0:
                raise ValueError('Invalid Telegram account identity')
            if c.execute('SELECT 1 FROM accounts WHERE tg_user_id=? LIMIT 1', (tg_user_id,)).fetchone():
                raise DuplicateAccountError('Telegram account has already been submitted')
            import secure_store
            cur=c.execute("INSERT INTO accounts(seller_id,phone,session_string,twofa,tg_user_id,tg_username,status,region,payout,created_at) VALUES(?,?,?,?,?,?,'pending',?,?,?)",(seller_id,phone,secure_store.encrypt(session_string),secure_store.encrypt(twofa),tg_user_id,username,quote['region'],quote['usd_micros'],int(datetime.now().timestamp())))
            aid=cur.lastrowid
            vals=(seller_id,quote['price_country'],quote['region'],quote['source_amount'],quote['source_currency'],quote['usd_micros'],quote['rate_toman_per_usd'],quote['rate_updated_utc'])
            c.execute('INSERT INTO sale_offers VALUES(?,?,?,?,?,?,?,?,?,?)',(aid,*vals,int(datetime.now().timestamp())))
            if schedule_cleanup:
                import pending_session_store
                job = pending_session_store.schedule_in_connection(c, aid, seller_id)
                if not job or job['status'] != 'pending':
                    raise RuntimeError('Could not schedule the pending-session cleanup')
            c.commit(); return aid
        except BaseException: c.rollback(); raise


def credit_sale(db_path, account_id, seller_id, *, require_cleanup_job=False):
    
    if isinstance(account_id, bool) or not isinstance(account_id, int):
        raise ValueError("Invalid account_id")
    if isinstance(seller_id, bool) or not isinstance(seller_id, int):
        raise ValueError("Invalid seller_id")
    with closing(sqlite3.connect(db_path, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            conn.execute("BEGIN IMMEDIATE")
            def record(row):
                return dict(row) if row is not None else None
            acc = conn.execute("SELECT id,seller_id,tg_user_id,status FROM accounts WHERE id=?", (account_id,)).fetchone()
            if acc is None or acc["seller_id"] != seller_id:
                conn.commit()
                return "not_found", None
            if require_cleanup_job:
                job = conn.execute('''SELECT 1 FROM pending_session_jobs
                    WHERE account_id=? AND seller_id=? AND tg_user_id=?
                      AND status='pending' AND due_at<=? AND next_attempt_at<=?''',
                    (account_id, seller_id, acc['tg_user_id'], int(datetime.now().timestamp()),
                     int(datetime.now().timestamp()))).fetchone()
                if job is None:
                    conn.commit()
                    return 'cancelled', None
            prior = conn.execute("SELECT * FROM sale_credits WHERE account_id=?", (account_id,)).fetchone()
            if prior:
                conn.commit()
                return "already_credited", record(prior)
            if acc["status"] == "sold":
                conn.commit()
                return "already_sold", None
            if acc["status"] != "pending" or isinstance(acc["tg_user_id"], bool) or not isinstance(acc["tg_user_id"], int) or acc["tg_user_id"] <= 0:
                conn.commit()
                return "not_found", None
            offer = conn.execute("SELECT region,price_country,source_amount,source_currency,usd_micros,rate_toman_per_usd,rate_updated_utc FROM sale_offers WHERE account_id=? AND seller_id=?", (account_id,seller_id)).fetchone()
            if offer is None: raise ValueError("No persisted sale offer")
            quote = dict(zip(("region","price_country","source_amount","source_currency","usd_micros","rate_toman_per_usd","rate_updated_utc"), offer))
            _validate_quote(quote)
            prior = conn.execute("SELECT * FROM sale_credits WHERE tg_user_id=?", (acc["tg_user_id"],)).fetchone()
            if prior:
                conn.commit()
                return "duplicate_account", record(prior)
            user = conn.execute("SELECT balance FROM users WHERE user_id=?", (seller_id,)).fetchone()
            if user is None:
                raise ValueError("Seller user does not exist")
            if user["balance"] < 0 or user["balance"] > MAX_SQLITE_INT - quote["usd_micros"]:
                raise OverflowError("Balance overflow")
            now = int(datetime.now().timestamp())
            conn.execute('''INSERT INTO sale_credits
                (account_id,seller_id,tg_user_id,region,price_country,source_amount,source_currency,
                 usd_micros,rate_toman_per_usd,rate_updated_utc,credited_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (account_id,seller_id,acc["tg_user_id"],quote["region"],quote["price_country"],
                 quote["source_amount"],quote["source_currency"],quote["usd_micros"],
                 quote["rate_toman_per_usd"],quote["rate_updated_utc"],now))
            conn.execute("UPDATE accounts SET status='sold', region=?, payout=? WHERE id=?",
                         (quote["region"],quote["usd_micros"],account_id))
            conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (quote["usd_micros"],seller_id))
            conn.execute("UPDATE users SET numbers_sold=(SELECT COUNT(*) FROM accounts WHERE seller_id=? AND status='sold') WHERE user_id=?", (seller_id,seller_id))
            row = conn.execute("SELECT * FROM sale_credits WHERE account_id=?", (account_id,)).fetchone()
            conn.commit()
            return "credited", record(row)
        except BaseException:
            conn.rollback()
            raise
