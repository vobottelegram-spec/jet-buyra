"""Drop this file into the Jet Number bot. Stdlib only.

    c = BridgeClient("https://HOST:8787", "jetnumber", SECRET)
    c.call("/v1/stock")
    o = c.call("/v1/reserve", {"region": "US", "idempotency_key": "order-1234-abcd"})
    c.call("/v1/code", {"order_id": o["order_id"]})      # poll every >=3s
    c.call("/v1/complete", {"order_id": o["order_id"]})  # after the buyer logged in
"""
import hashlib, hmac, json, secrets, time, urllib.request, urllib.error


class BridgeError(Exception):
    def __init__(self, msg, status=0, code=""):
        super().__init__(msg)
        self.status, self.code = status, code


class BridgeClient:
    def __init__(self, base_url, key_id, secret, timeout=25, cafile=None):
        from urllib.parse import urlparse
        u = urlparse(base_url)
        if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("bridge URL must be https:// (plain http is only allowed for localhost)")
        if len(secret) < 32:
            raise ValueError("bridge secret must be at least 32 characters")
        self.base, self.kid, self.secret, self.timeout, self.cafile = base_url.rstrip("/"), key_id, secret.encode(), timeout, cafile

    def call(self, path, payload=None):
        body = json.dumps(payload or {}, separators=(",", ":")).encode()
        ts, nonce = str(int(time.time())), secrets.token_urlsafe(24)
        msg = "\n".join(["POST", path, ts, nonce, hashlib.sha256(body).hexdigest()])
        sig = hmac.new(self.secret, msg.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(self.base + path, data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Key-Id": self.kid, "X-Timestamp": ts,
            "X-Nonce": nonce, "X-Signature": sig})
        ctx = None
        if self.cafile:
            import ssl
            ctx = ssl.create_default_context(cafile=self.cafile)
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
            status, raw, rsig = resp.status, resp.read(), resp.headers.get("X-Signature", "")
        except urllib.error.HTTPError as e:
            status, raw, rsig = e.code, e.read(), e.headers.get("X-Signature", "")
        if rsig:  # always verify signed responses
            exp = hmac.new(self.secret, "\n".join([str(status), nonce, hashlib.sha256(raw).hexdigest()]).encode(),
                           hashlib.sha256).hexdigest()
            if not hmac.compare_digest(rsig, exp):
                raise BridgeError("response signature mismatch", status, "bad_signature")
        elif status == 200:
            raise BridgeError("unsigned response", status, "unsigned")
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise BridgeError(f"{status}:bad_json", status, "bad_json") from None
        if status != 200:
            raise BridgeError(f"{status}:{data.get('error')}", status, str(data.get("error")))
        return data
