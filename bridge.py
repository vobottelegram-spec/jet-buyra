"""Authenticated bridge between the BIYORA inventory and the Jet Number bot.

Stdlib-only HTTP/1.1 JSON server. Every request must be HMAC-SHA256 signed; every
response is signed back. Session strings and 2FA passwords are NEVER returned.

Signed string (request):  METHOD \n PATH \n TIMESTAMP \n NONCE \n sha256hex(body)
Signed string (response): STATUS \n NONCE \n sha256hex(body)
Headers: X-Key-Id, X-Timestamp, X-Nonce, X-Signature (hex)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import ssl
import time
from collections import defaultdict, deque
from contextlib import closing

log = logging.getLogger("bridge")

MAX_BODY = 2048
MAX_HEADER_BYTES = 8192
CLOCK_SKEW = 60
NONCE_TTL = 300
READ_TIMEOUT = 10
MAX_CONNECTIONS = 50
RATE_PER_MIN = 60
FAIL_LIMIT = 10
FAIL_WINDOW = 300
CODE_MIN_INTERVAL = 3
CODE_MAX_CALLS = 30
CODE_REPLAY_WINDOW = 60   # same login code may be shown again only within this many seconds
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_IDEM_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_REGION_RE = re.compile(r"^[A-Za-z0-9_+ -]{1,32}$")
_ORDER_RE = re.compile(r"^[0-9a-f]{24}$")


_CODE1 = re.compile(r"(?i)(?:code|\u06a9\u062f|\u043a\u043e\u0434)\D{0,20}(\d{5,6})(?!\d)")
_CODE2 = re.compile(r"(?<![\d:/.\-])(\d{5,6})(?![\d:/.\-])")


def extract_code(text):
    """Pull a Telegram login code out of a service message; ignore dates, times and long notices."""
    if not text or len(text) > 400:
        return None
    m = _CODE1.search(text)
    if m:
        return m.group(1)
    nums = _CODE2.findall(text)
    return nums[0] if len(nums) == 1 else None


def _now():
    return int(time.time())


def _connect(db_path):
    c = sqlite3.connect(db_path, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=10000")
    return c


def init_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bridge_orders (
        order_id TEXT PRIMARY KEY,
        key_id TEXT NOT NULL,
        idem_key TEXT NOT NULL,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        region TEXT,
        state TEXT NOT NULL CHECK(state IN ('reserved','completed','released','expired','review')),
        reserved_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        code_delivered_at INTEGER,
        code_calls INTEGER NOT NULL DEFAULT 0,
        last_code_call INTEGER NOT NULL DEFAULT 0,
        UNIQUE(key_id, idem_key)
    )""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bridge_orders)")}
    for name in ("last_msg_id", "last_code_at"):
        if name not in cols:
            conn.execute(f"ALTER TABLE bridge_orders ADD COLUMN {name} INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bridge_orders_acc ON bridge_orders(account_id,state)")
    conn.execute("CREATE TABLE IF NOT EXISTS bridge_nonces (nonce TEXT PRIMARY KEY, seen_at INTEGER NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS bridge_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, ip TEXT, key_id TEXT,
        path TEXT, status INTEGER, order_id TEXT)""")


class ApiError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


# ---------------------------------------------------------------- Telegram gateway
class TelethonGateway:
    """Reads login codes / logs out using a stored session. Telethon is imported lazily."""

    def __init__(self, api_id, api_hash, device_model="Samsung SM-S918B",
                 system_version="SDK 34", app_version="10.14.5"):
        self.api_id, self.api_hash = api_id, api_hash
        self.dev = dict(device_model=device_model, system_version=system_version,
                        app_version=app_version, lang_code="en", system_lang_code="en-US")

    def _client(self, session):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(session), self.api_id, self.api_hash,
                              flood_sleep_threshold=0, request_retries=0, **self.dev)

    async def fetch_code(self, session, since_ts):
        client = self._client(session)
        try:
            await asyncio.wait_for(client.connect(), 20)
            if not await client.is_user_authorized():
                raise ApiError(410, "session_dead")
            async for msg in client.iter_messages(777000, limit=5):
                if msg.date.timestamp() < since_ts - 5:
                    break
                code = extract_code(msg.raw_text or "")
                if code:
                    return code, msg.id, int(msg.date.timestamp())
            return None, None, None
        finally:
            await client.disconnect()

    async def logout(self, session):
        client = self._client(session)
        try:
            await asyncio.wait_for(client.connect(), 20)
            if await client.is_user_authorized():
                await asyncio.wait_for(client.log_out(), 20)
            return True
        finally:
            await client.disconnect()


# ---------------------------------------------------------------- business logic
class Bridge:
    def __init__(self, db_path, key_id, secrets_, gateway, decrypt,
                 allowed_ips=(), reserve_ttl=900, trust_proxy=False, auto_finalize=3600):
        if not secrets_ or any(len(s) < 32 for s in secrets_):
            raise ValueError("bridge secrets must be at least 32 characters")
        self.db_path, self.key_id = db_path, key_id
        self.secrets = [s.encode() for s in secrets_]
        self.gateway, self.decrypt = gateway, decrypt
        self.allowed_ips = set(allowed_ips)
        self.reserve_ttl = reserve_ttl
        self.trust_proxy, self.auto_finalize = trust_proxy, auto_finalize
        self._rate = defaultdict(deque)
        self._fails = defaultdict(deque)
        self._locks = defaultdict(asyncio.Lock)
        with closing(_connect(db_path)) as c, c:
            init_schema(c)

    # ---- auth
    def sign(self, secret, method, path, ts, nonce, body):
        msg = "\n".join([method, path, str(ts), nonce, hashlib.sha256(body).hexdigest()])
        return hmac.new(secret, msg.encode(), hashlib.sha256).hexdigest()

    def sign_response(self, secret, status, nonce, body):
        msg = "\n".join([str(status), nonce, hashlib.sha256(body).hexdigest()])
        return hmac.new(secret, msg.encode(), hashlib.sha256).hexdigest()

    def _blocked(self, ip):
        q = self._fails[ip]
        while q and q[0] < _now() - FAIL_WINDOW:
            q.popleft()
        return len(q) >= FAIL_LIMIT

    def authenticate(self, ip, method, path, headers, body):
        if self.allowed_ips and ip not in self.allowed_ips:
            raise ApiError(401, "unauthorized")
        matched = nonce = None
        try:
            kid = headers.get("x-key-id", "")
            ts = int(headers.get("x-timestamp", ""))
            nonce = headers.get("x-nonce", "")
            sig = headers.get("x-signature", "")
            ok = (hmac.compare_digest(kid.encode(), self.key_id.encode())
                  and abs(_now() - ts) <= CLOCK_SKEW and _NONCE_RE.match(nonce) is not None)
            if ok:
                for s_ in self.secrets:
                    if hmac.compare_digest(sig.encode(), self.sign(s_, method, path, ts, nonce, body).encode()):
                        matched = s_
        except Exception:
            matched = None
        if matched is None:
            self._fails[ip].append(_now())
            raise ApiError(429 if self._blocked(ip) else 401, "too_many_failures" if self._blocked(ip) else "unauthorized")
        with closing(_connect(self.db_path)) as c, c:  # replay protection (persisted)
            c.execute("DELETE FROM bridge_nonces WHERE seen_at<?", (_now() - NONCE_TTL,))
            try:
                c.execute("INSERT INTO bridge_nonces VALUES(?,?)", (f"{kid}:{nonce}", _now()))
            except sqlite3.IntegrityError:
                self._fails[ip].append(_now())
                raise ApiError(401, "unauthorized") from None
        q = self._rate[kid]
        while q and q[0] < _now() - 60:
            q.popleft()
        if len(q) >= RATE_PER_MIN:
            raise ApiError(429, "rate_limited")
        q.append(_now())
        return matched, nonce

    # ---- db helpers
    def _expire(self, c):
        now = _now()
        c.execute("UPDATE bridge_orders SET state='expired' WHERE state='reserved' AND expires_at<? "
                  "AND code_delivered_at IS NULL", (now,))
        n = c.execute("UPDATE bridge_orders SET state='review' WHERE state='reserved' AND expires_at<? "
                      "AND code_delivered_at IS NOT NULL", (now,)).rowcount
        if n:
            log.warning("%s bridge order(s) need manual review (code delivered, never completed)", n)

    _AVAILABLE = """FROM accounts a WHERE a.status='sold'
        AND a.session_string IS NOT NULL AND length(trim(a.session_string))>0
        AND (a.twofa IS NULL OR a.twofa='')
        AND a.region IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM bridge_orders o WHERE o.account_id=a.id
                        AND o.state IN ('reserved','completed','review'))"""

    # ---- endpoints
    async def stock(self, req):
        with closing(_connect(self.db_path)) as c, c:
            self._expire(c)
            rows = c.execute(f"SELECT a.region AS r, COUNT(*) AS n {self._AVAILABLE} GROUP BY a.region").fetchall()
        return {"regions": {r["r"]: r["n"] for r in rows}}

    async def reserve(self, req):
        region, idem = req.get("region"), req.get("idempotency_key")
        if not isinstance(region, str) or not _REGION_RE.match(region) or \
                not isinstance(idem, str) or not _IDEM_RE.match(idem):
            raise ApiError(400, "bad_request")
        with closing(_connect(self.db_path)) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                self._expire(c)
                old = c.execute("SELECT o.*, a.phone FROM bridge_orders o JOIN accounts a ON a.id=o.account_id "
                                "WHERE o.key_id=? AND o.idem_key=?", (self.key_id, idem)).fetchone()
                if old:
                    if old["region"] != region:
                        raise ApiError(409, "idempotency_conflict")
                    c.commit()
                    return self._order_view(old)
                acc = c.execute(f"SELECT a.id, a.phone {self._AVAILABLE} AND a.region=? "
                                "ORDER BY a.created_at, a.id LIMIT 1", (region,)).fetchone()
                if not acc:
                    raise ApiError(404, "out_of_stock")
                oid, now = secrets.token_hex(12), _now()
                c.execute("INSERT INTO bridge_orders(order_id,key_id,idem_key,account_id,region,state,"
                          "reserved_at,expires_at) VALUES(?,?,?,?,?,'reserved',?,?)",
                          (oid, self.key_id, idem, acc["id"], region, now, now + self.reserve_ttl))
                c.commit()
                return {"order_id": oid, "phone": acc["phone"], "state": "reserved",
                        "expires_at": now + self.reserve_ttl}
            except BaseException:
                c.rollback()
                raise

    @staticmethod
    def _order_view(o):
        return {"order_id": o["order_id"], "phone": o["phone"], "state": o["state"],
                "expires_at": o["expires_at"]}

    def _get_order(self, c, req):
        oid = req.get("order_id")
        if not isinstance(oid, str) or not _ORDER_RE.match(oid):
            raise ApiError(400, "bad_request")
        o = c.execute("SELECT o.*, a.phone, a.session_string FROM bridge_orders o "
                      "JOIN accounts a ON a.id=o.account_id WHERE o.order_id=? AND o.key_id=?",
                      (oid, self.key_id)).fetchone()
        if not o:
            raise ApiError(404, "not_found")
        return o

    async def order(self, req):
        with closing(_connect(self.db_path)) as c, c:
            self._expire(c)
            return self._order_view(self._get_order(c, req))

    async def code(self, req):
        oid = req.get("order_id")
        async with self._locks[oid if isinstance(oid, str) else ""]:
            with closing(_connect(self.db_path)) as c, c:
                self._expire(c)
                o = self._get_order(c, req)
                if o["state"] != "reserved":
                    raise ApiError(409, "order_" + o["state"])
                now = _now()
                if o["code_calls"] >= CODE_MAX_CALLS:
                    raise ApiError(429, "code_calls_exhausted")
                if now - o["last_code_call"] < CODE_MIN_INTERVAL:
                    raise ApiError(429, "slow_down")
                c.execute("UPDATE bridge_orders SET code_calls=code_calls+1,last_code_call=? WHERE order_id=?",
                          (now, o["order_id"]))
                session = self.decrypt(o["session_string"])
            try:
                code, msg_id, at = await self.gateway.fetch_code(session, o["reserved_at"])
            except ApiError:
                raise
            except Exception as exc:
                log.warning("code fetch failed (%s)", type(exc).__name__)
                raise ApiError(502, "telegram_error") from None
            finally:
                session = None
            if code:
                now = _now()
                with closing(_connect(self.db_path)) as c, c:
                    cur = c.execute("SELECT last_msg_id,last_code_at FROM bridge_orders WHERE order_id=?",
                                    (o["order_id"],)).fetchone()
                    if msg_id is not None and cur["last_msg_id"] == msg_id:
                        # same message as last time: re-show only while it is still fresh,
                        # otherwise the buyer must trigger a NEW login code
                        if now - (cur["last_code_at"] or 0) > CODE_REPLAY_WINDOW:
                            return {"code": None, "received_at": None}
                    else:
                        c.execute("UPDATE bridge_orders SET last_msg_id=?,last_code_at=?,"
                                  "code_delivered_at=COALESCE(code_delivered_at,?) WHERE order_id=?",
                                  (msg_id, now, now, o["order_id"]))
            return {"code": code, "received_at": at}

    async def release(self, req):
        with closing(_connect(self.db_path)) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                self._expire(c)
                o = self._get_order(c, req)
                if o["state"] in ("released", "expired"):
                    c.commit()
                    return {"state": o["state"]}
                if o["state"] != "reserved" or o["code_delivered_at"] is not None:
                    raise ApiError(409, "cannot_release")
                c.execute("UPDATE bridge_orders SET state='released' WHERE order_id=?", (o["order_id"],))
                c.commit()
                return {"state": "released"}
            except BaseException:
                c.rollback()
                raise

    async def _finalize(self, oid):
        """Log our session out of the sold account, wipe it from the DB, mark the order completed."""
        async with self._locks[oid]:
            with closing(_connect(self.db_path)) as c, c:
                o = c.execute("SELECT o.*, a.session_string FROM bridge_orders o "
                              "JOIN accounts a ON a.id=o.account_id WHERE o.order_id=?", (oid,)).fetchone()
                if not o:
                    raise ApiError(404, "not_found")
                if o["state"] == "completed":
                    return
                if o["state"] not in ("reserved", "review") or o["code_delivered_at"] is None:
                    raise ApiError(409, "cannot_complete")
                session = self.decrypt(o["session_string"])
            try:
                await self.gateway.logout(session)  # drop our own access first
            except Exception as exc:
                log.warning("logout failed (%s); order stays open for retry", type(exc).__name__)
                raise ApiError(502, "logout_failed") from None
            finally:
                session = None
            with closing(_connect(self.db_path)) as c, c:
                c.execute("PRAGMA secure_delete=ON")
                c.execute("UPDATE accounts SET session_string='', twofa=NULL WHERE id=?", (o["account_id"],))
                c.execute("UPDATE bridge_orders SET state='completed' WHERE order_id=?", (oid,))

    async def complete(self, req):
        with closing(_connect(self.db_path)) as c, c:
            o = self._get_order(c, req)
        await self._finalize(o["order_id"])
        return {"state": "completed"}

    async def auto_finalize_loop(self):
        """Safety net: never keep a live session on an account whose login code was already handed out."""
        while True:
            await asyncio.sleep(60)
            try:
                with closing(_connect(self.db_path)) as c, c:
                    due = [r[0] for r in c.execute(
                        "SELECT order_id FROM bridge_orders WHERE state IN ('reserved','review') "
                        "AND code_delivered_at IS NOT NULL AND code_delivered_at<?",
                        (_now() - self.auto_finalize,)).fetchall()]
                for oid in due:
                    try:
                        await self._finalize(oid)
                        log.info("auto-completed order %s", oid)
                    except ApiError as e:
                        log.warning("auto-complete %s failed: %s", oid, e.code)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("auto_finalize_loop")

    ROUTES = {"/v1/stock": "stock", "/v1/reserve": "reserve", "/v1/order": "order",
              "/v1/code": "code", "/v1/release": "release", "/v1/complete": "complete"}

    # ---- HTTP plumbing
    def _audit(self, ip, path, status, order_id=None):
        try:
            with closing(_connect(self.db_path)) as c, c:
                c.execute("INSERT INTO bridge_audit(ts,ip,key_id,path,status,order_id) VALUES(?,?,?,?,?,?)",
                          (_now(), ip, self.key_id, path[:64], status, order_id))
        except Exception:
            pass

    async def handle(self, reader, writer):
        ip = (writer.get_extra_info("peername") or ("?",))[0]
        status, payload, secret, nonce, path = 500, {"error": "internal"}, None, "", ""
        try:
            async with asyncio.timeout(READ_TIMEOUT + 5):
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_TIMEOUT)
                if len(head) > MAX_HEADER_BYTES:
                    raise ApiError(431, "headers_too_large")
                lines = head.decode("latin-1").split("\r\n")
                parts = lines[0].split(" ")
                if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
                    raise ApiError(400, "bad_request")
                method, path = parts[0], parts[1]
                headers = {}
                for ln in lines[1:]:
                    if ln:
                        k, _, v = ln.partition(":")
                        headers[k.strip().lower()] = v.strip()
                if self.trust_proxy and headers.get("x-forwarded-for"):
                    cand = headers["x-forwarded-for"].split(",")[-1].strip()  # appended by our own proxy
                    try:
                        import ipaddress
                        ip = str(ipaddress.ip_address(cand))
                    except ValueError:
                        pass
                if "transfer-encoding" in headers:
                    raise ApiError(400, "bad_request")
                try:
                    n = int(headers.get("content-length", "0"))
                except ValueError:
                    raise ApiError(400, "bad_request") from None
                if n < 0 or n > MAX_BODY:
                    raise ApiError(413, "body_too_large")
                body = await asyncio.wait_for(reader.readexactly(n), READ_TIMEOUT) if n else b""
                if method != "POST" or path not in self.ROUTES:
                    # authenticate first so unauthenticated callers learn nothing about routes
                    self.authenticate(ip, method, path, headers, body)
                    raise ApiError(404, "not_found")
                secret, nonce = self.authenticate(ip, method, path, headers, body)
                try:
                    req = json.loads(body.decode() or "{}")
                    if not isinstance(req, dict):
                        raise ValueError
                except ValueError:
                    raise ApiError(400, "bad_json") from None
                payload = await getattr(self, self.ROUTES[path])(req)
                status = 200
        except ApiError as e:
            status, payload = e.status, {"error": e.code}
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError,
                asyncio.TimeoutError, ConnectionError):
            status, payload = 400, {"error": "bad_request"}
        except Exception:
            log.exception("bridge internal error")
            status, payload = 500, {"error": "internal"}
        body_out = json.dumps(payload, separators=(",", ":")).encode()
        hdr = [f"HTTP/1.1 {status} {'OK' if status == 200 else 'ERR'}",
               "Content-Type: application/json", f"Content-Length: {len(body_out)}",
               "Cache-Control: no-store", "X-Content-Type-Options: nosniff", "Connection: close"]
        if secret:
            hdr.append("X-Signature: " + self.sign_response(secret, status, nonce, body_out))
        try:
            writer.write(("\r\n".join(hdr) + "\r\n\r\n").encode() + body_out)
            await writer.drain()
        except Exception:
            pass
        finally:
            self._audit(ip, path, status, payload.get("order_id") if isinstance(payload, dict) else None)
            writer.close()


async def start(bridge, host="127.0.0.1", port=8787, tls_cert=None, tls_key=None):
    sem = asyncio.Semaphore(MAX_CONNECTIONS)
    ctx = None
    if tls_cert and tls_key:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key)

    async def guarded(r, w):
        if sem.locked():
            w.close()
            return
        async with sem:
            await bridge.handle(r, w)

    server = await asyncio.start_server(guarded, host, port, ssl=ctx, limit=MAX_HEADER_BYTES * 2)
    server._bridge_task = asyncio.create_task(bridge.auto_finalize_loop()) if bridge.auto_finalize > 0 else None
    log.info("bridge listening on %s:%s (tls=%s, ip_allowlist=%s)", host, port, bool(ctx),
             bool(bridge.allowed_ips))
    return server


def shutdown(server):
    if server is None:
        return
    t = getattr(server, "_bridge_task", None)
    if t:
        t.cancel()
    server.close()


async def start_from_env(db_path, api_id, api_hash, decrypt):
    """Start the bridge when BRIDGE_ENABLED=1; returns the server or None."""
    if os.getenv("BRIDGE_ENABLED", "0") != "1":
        return None
    key_id = os.getenv("BRIDGE_KEY_ID", "jetnumber")
    secrets_ = [s for s in (os.getenv("BRIDGE_SECRET", ""), os.getenv("BRIDGE_SECRET_PREV", "")) if s]
    ips = [i.strip() for i in os.getenv("BRIDGE_ALLOWED_IPS", "").split(",") if i.strip()]
    b = Bridge(db_path, key_id, secrets_, TelethonGateway(api_id, api_hash), decrypt,
               allowed_ips=ips, reserve_ttl=int(os.getenv("BRIDGE_RESERVE_TTL", "900")),
               trust_proxy=os.getenv("BRIDGE_TRUST_PROXY", "0") == "1",
               auto_finalize=int(os.getenv("BRIDGE_AUTO_FINALIZE", "3600")))
    port = int(os.getenv("BRIDGE_PORT") or os.getenv("PORT") or "8787")
    return await start(b, os.getenv("BRIDGE_HOST", "127.0.0.1"), port,
                       os.getenv("BRIDGE_TLS_CERT") or None, os.getenv("BRIDGE_TLS_KEY") or None)
