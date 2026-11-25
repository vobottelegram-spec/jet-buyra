#!/usr/bin/env python3
"""One container, two bots.

BIYORA (Telethon, sells Telegram accounts) and Jet Number (aiogram, sells virtual numbers) run as two
supervised child processes. They talk through the signed bridge on 127.0.0.1 inside the container, so
nothing about the bridge is exposed to the internet and no bridge secret has to be configured by hand.
The only things you must provide are the bot tokens (see .env.example)."""
import asyncio
import os
import secrets
import signal
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()                      # local runs: read ./.env ; on Railway the dashboard variables are used
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
BRIDGE_PORT = "8787"


def log(msg):
    print(f"[run] {msg}", flush=True)


def data_dir():
    d = Path(os.getenv("DATA_DIR") or ("/data" if Path("/data").is_dir() else HERE / "data"))
    d.mkdir(parents=True, exist_ok=True)
    if str(d) == "/data" and not os.path.ismount("/data"):
        log("WARNING: /data is not a mounted volume - databases will be lost on redeploy")
    elif str(d) != "/data" and not os.getenv("DATA_DIR"):
        log(f"WARNING: no /data volume found, using {d} (not persistent on Railway - add a Volume at /data)")
    return d


def ensure_data_key(data):
    """Encryption key for stored sessions. Prefer DATA_KEYS in the environment; otherwise create one
    key file inside the data volume (fine for testing; for production keep the key outside the volume)."""
    if os.getenv("DATA_KEYS") or os.getenv("DATA_KEY"):
        return
    kf = data / "data_keys.key"
    if not kf.exists():
        from cryptography.fernet import Fernet
        fd = os.open(kf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
        log(f"created encryption key file {kf} (set DATA_KEYS in the environment for production)")
    os.environ["DATA_KEYS"] = kf.read_text().strip()


SECRETS_NOT_FOR_BIYORA = ("JETNUMBER_BOT_TOKEN", "TNUMBER_API_KEY", "OKAYPAY_TOKEN", "OKAYPAY_APP_ID",
                          "BIYORA_SECRET", "OWNER_IDS")
SECRETS_NOT_FOR_JETNUMBER = ("BIYORA_BOT_TOKEN", "API_ID", "API_HASH", "ADMIN_IDS", "DATA_KEYS", "DATA_KEY",
                             "BRIDGE_SECRET", "BRIDGE_SECRET_PREV")


def biyora_env(data, bridge_secret):
    e = {k: v for k, v in os.environ.items() if k not in SECRETS_NOT_FOR_BIYORA}
    e.update(BOT_TOKEN=os.getenv("BIYORA_BOT_TOKEN", ""), DB_PATH=str(data / "accounts.db"),
             BRIDGE_ENABLED="1", BRIDGE_HOST="127.0.0.1", BRIDGE_PORT=BRIDGE_PORT,
             BRIDGE_KEY_ID="jetnumber", BRIDGE_SECRET=bridge_secret,
             BRIDGE_RESERVE_TTL=os.getenv("BRIDGE_RESERVE_TTL", "86400"),
             BRIDGE_AUTO_FINALIZE=os.getenv("BRIDGE_AUTO_FINALIZE", "3600"))
    return e


def jetnumber_env(data, bridge_secret, bridge_on):
    e = {k: v for k, v in os.environ.items() if k not in SECRETS_NOT_FOR_JETNUMBER}
    e.update(BOT_TOKEN=os.getenv("JETNUMBER_BOT_TOKEN", ""), DATABASE_PATH=str(data / "jetnumber.db"))
    e.pop("JETNUMBER_BOT_TOKEN", None)
    if bridge_on:
        e.update(BIYORA_URL=f"http://127.0.0.1:{BRIDGE_PORT}", BIYORA_KEY_ID="jetnumber", BIYORA_SECRET=bridge_secret)
    return e


def missing(names):
    return [n for n in names if not os.getenv(n, "").strip()]


async def pump(name, stream):
    async for line in stream:
        print(f"[{name}] {line.decode(errors='replace').rstrip()}", flush=True)


async def supervise(name, args, env, cwd, stop):
    delay = 3
    while not stop.is_set():
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(*args, env=env, cwd=str(cwd),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out = asyncio.create_task(pump(name, proc.stdout))
        waiter, stopper = asyncio.create_task(proc.wait()), asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if stopper in done:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 15)
            except asyncio.TimeoutError:
                proc.kill()
            await out
            return
        stopper.cancel()
        await out
        delay = 3 if time.monotonic() - started > 120 else min(delay * 2, 60)
        log(f"{name} exited with code {proc.returncode}; restarting in {delay}s")
        try:
            await asyncio.wait_for(stop.wait(), delay)
        except asyncio.TimeoutError:
            pass


async def main():
    data = data_dir()
    ensure_data_key(data)
    bridge_secret = os.getenv("BRIDGE_SECRET") or secrets.token_urlsafe(48)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    miss_b = missing(["BIYORA_BOT_TOKEN", "API_ID", "API_HASH", "ADMIN_IDS"])
    miss_j = missing(["JETNUMBER_BOT_TOKEN"])
    tasks = []
    if miss_b:
        log("BIYORA NOT started - missing variables: " + ", ".join(miss_b))
    else:
        tasks.append(("BIYORA", [sys.executable, str(HERE / "bot.py")], biyora_env(data, bridge_secret)))
    if miss_j:
        log("Jet Number NOT started - missing variables: " + ", ".join(miss_j))
    else:
        tasks.append(("JetNumber", [sys.executable, str(HERE / "jn_main.py")],
                      jetnumber_env(data, bridge_secret, not miss_b)))
    if not tasks:
        log("nothing to run: fill in the tokens (see .env.example)")
        sys.exit(1)
    log("starting: " + ", ".join(t[0] for t in tasks) + f" | data dir {data}")
    runs = []
    for i, (name, args, env) in enumerate(tasks):
        if i:
            await asyncio.sleep(4)     # let BIYORA's bridge come up first
        runs.append(asyncio.create_task(supervise(name, args, env, data, stop)))
    await stop.wait()
    await asyncio.gather(*runs, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
