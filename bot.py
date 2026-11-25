#!/usr/bin/env python3
                       


import asyncio
import json
import logging
import os
import re
import sqlite3
import secrets
import time
from decimal import Decimal, ROUND_HALF_UP, localcontext
import unicodedata
from datetime import datetime, timezone
from html import escape
from contextlib import closing

import phonenumbers
from telethon import Button, TelegramClient, errors, events, functions
from telethon.extensions import html as html_ext
from telethon.sessions import StringSession
from telethon.tl import types as tl_types

from countries import COUNTRIES, DEFAULT_KEY, flag_emoji
import i18n
from i18n import tr
import user_store
import withdrawal_store
import withdrawal_text
import sale_credit
import sale_text
import support_store
import secure_store
import bridge
import pending_session_store
import pending_session_worker
from ton_address import validate_ton_address, TonAddressError

withdrawal_text.install(i18n)
sale_text.install(i18n)
import currency

                                                                               
        
                                                                               

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.db"))
EMOJI_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji_state.json")
EMOJI_MAP_FILE = os.getenv(
    "EMOJI_MAP", os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji_map.json")
)

                                                        
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
}

                                                                                    
                                                                                      
EMOJI_PACKS = tuple(
    p.strip()
    for p in os.getenv(
        "EMOJI_PACKS",
        "DuckEmoji,EmoticonEmoji,MemeEmoji,GameEmoji,OutlineEmoji,MashupEmoji,"
        "AnimatedAsianEmoji,ABCEmoji,BirthdayCollection,LoveDayEmoji,CreepyEmoji,CrayonsEmoji",
    ).split(",")
    if p.strip()
)

DEVICE_MODEL = "Samsung SM-S918B"
SYSTEM_VERSION = "SDK 34"
APP_VERSION = "10.14.5"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("sellerbot")

bot: TelegramClient = None                 

STEP_PHONE = "phone"
STEP_CODE = "code"
STEP_2FA = "2fa"
STEP_LOGOUT = "logout"
STEP_WITHDRAW_AMOUNT = "withdraw_amount"
STEP_WITHDRAW_WALLET = "withdraw_wallet"

STATE = {}                                                                                                                 
PRICE_STATE = {}                                                                                 
PANEL_STATE = {}                                                                 
SUPPORT_STATE = {}                                                                
DB_LOCK = asyncio.Lock()
LOGOUT_CHECK_INTERVAL = 30
LOGOUT_CHECK_ATTEMPTS = 10
PENDING_SESSION_LOCKS = {}


def pending_session_lock(tg_user_id):
    return PENDING_SESSION_LOCKS.setdefault(tg_user_id, asyncio.Lock())

                                                                               
       
                                                                               

WELCOME = (
    "🚀 <b>فروش اکانت تلگرام</b> 💎\n\n"
    "👋 سلام {name}!\n"
    "🔥 اینجا می‌تونی اکانت تلگرامت رو سریع بفروشی.\n\n"
    "✨ یکی از گزینه‌های زیر رو انتخاب کن:"
)

INFO = (
    "💡 <b>توضیحات</b>\n\n"
    "۱️⃣ روی «فروش اکانت» بزن.\n"
    "۲️⃣ شماره اکانت رو با کد کشور بفرست. مثال: <code>+989****4567</code>\n"
    "۳️⃣ کدی که تلگرام برات می‌فرسته رو با کیبورد عددی وارد کن و «تایید» رو بزن.\n"
    "۴️⃣ اگر اکانت رمز دو مرحله‌ای (2FA) داره، رمز رو بفرست.\n"
    "۵️⃣ دستگاه‌ها و سشن‌های دیگه رو از اکانت خارج کن؛ تا ۵ دقیقه هر ۳۰ ثانیه خودکار بررسی می‌کنیم. برای بررسی فوری «لاگ اوت کردم» رو بزن.\n\n"
    "❗️ اکانت باید همین الان روی گوشی/دستگاه خودت لاگین باشه تا کد رو ببینی."
)

ASK_PHONE = (
    "📞 شماره اکانتی که می‌خوای بفروشی رو با کد کشور بفرست:\n"
    "مثال:\n<code>+989121234567</code>\n\n"
    "❌ برای لغو /cancel رو بزن."
)

TWOFA_ASK = (
    "🔒 این اکانت رمز دو مرحله‌ای (2FA) داره.\n"
    "🔑 رمز دو مرحله‌ایش رو بفرست.\n\n"
    "🗑 پیام رمز بلافاصله بعد از دریافت پاک می‌شه."
)

TWOFA_WRONG = (
    "❌ رمز دو مرحله‌ای اشتباهه. دوباره بفرست یا /cancel بزن."
)

def success_text(phone, acc):
    return tr("success", phone=phone, acc=acc)

                                                                               
    
                                                                               

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL,
    phone          TEXT    NOT NULL,
    session_string TEXT    NOT NULL,
    twofa          TEXT,
    tg_user_id     INTEGER,
    tg_username    TEXT,
    status         TEXT    NOT NULL DEFAULT 'pending',
    region         TEXT,
    payout         INTEGER,
    created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);

CREATE TABLE IF NOT EXISTS disabled_regions (
    country TEXT PRIMARY KEY,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    country    TEXT PRIMARY KEY,
    price      INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
    ,price_amount TEXT
    ,price_currency TEXT
);
"""


def _migrate(conn):
    
    cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if "region" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN region TEXT")
    if "payout" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN payout INTEGER")
    price_cols = {row[1] for row in conn.execute("PRAGMA table_info(prices)")}
    if "price_amount" not in price_cols:
        conn.execute("ALTER TABLE prices ADD COLUMN price_amount TEXT")
    if "price_currency" not in price_cols:
        conn.execute("ALTER TABLE prices ADD COLUMN price_currency TEXT")


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        user_store.init_schema(conn)
        withdrawal_store.init_schema(conn)
        sale_credit.init_schema(conn)
        support_store.init_schema(conn)
        pending_session_store.init_schema(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    migrated = secure_store.migrate_plaintext(DB_PATH)
    if migrated:
        log.info("encrypted %s legacy plaintext account row(s)", migrated)


def _save_account(seller_id, phone, session_string, twofa, tg_user_id, username,
                  region=None, payout=None):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "INSERT INTO accounts (seller_id, phone, session_string, twofa, tg_user_id,"
            " tg_username, status, region, payout, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (seller_id, phone, secure_store.encrypt(session_string), secure_store.encrypt(twofa),
             tg_user_id, username, region, payout, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid


def _set_status(account_id, status):
    return user_store.set_account_status(DB_PATH, account_id, status)


                                                                             

def _get_disabled_regions():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        return {row[0] for row in conn.execute("SELECT country FROM disabled_regions")}


def _set_region_disabled(country, disabled):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        if disabled:
            conn.execute("INSERT INTO disabled_regions (country, updated_at) VALUES (?, ?) ON CONFLICT(country) DO UPDATE SET updated_at=excluded.updated_at", (country, int(time.time())))
        else:
            conn.execute("DELETE FROM disabled_regions WHERE country = ?", (country,))
        conn.commit()


def _get_all_prices():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("SELECT country, price_amount, price_currency, price FROM prices").fetchall()
    return {country: ({"amount": Decimal(amount), "currency": cur} if amount is not None and cur in ("IRR", "IRT", "USD") else {"legacy": price})
            for country, amount, cur, price in rows}


def _set_price(country, amount, currency_code):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO prices (country, price, updated_at, price_amount, price_currency) VALUES (?, 0, ?, ?, ?)"
            " ON CONFLICT(country) DO UPDATE SET price = 0, updated_at = excluded.updated_at,"
            " price_amount = excluded.price_amount, price_currency = excluded.price_currency",
            (country, int(time.time()), str(amount), currency_code),
        )
        conn.commit()


def _delete_price(country):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("DELETE FROM prices WHERE country = ?", (country,))
        conn.commit()


async def save_account(*args, **kwargs):
    async with DB_LOCK:
        return await asyncio.to_thread(_save_account, *args, **kwargs)


async def set_status(account_id, status):
    async with DB_LOCK:
        await asyncio.to_thread(_set_status, account_id, status)


async def all_prices():
    async with DB_LOCK:
        return await asyncio.to_thread(_get_all_prices)


async def set_price(country, amount, currency_code):
    async with DB_LOCK:
        await asyncio.to_thread(_set_price, country, amount, currency_code)


async def delete_price(country):
    async with DB_LOCK:
        await asyncio.to_thread(_delete_price, country)


async def disabled_regions():
    async with DB_LOCK:
        return await asyncio.to_thread(_get_disabled_regions)


async def set_region_disabled(country, disabled):
    async with DB_LOCK:
        await asyncio.to_thread(_set_region_disabled, country, disabled)


async def price_for_region(iso):
    
    prices = await all_prices()
    if iso and iso in await disabled_regions():
        return None
    if iso and prices.get(iso) is not None:
        return prices[iso]
    return prices.get(DEFAULT_KEY)


                                                                             

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_ANY_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def fmt_price(n):
    return f"{int(n):,}".translate(_FA_DIGITS).replace(",", "٬")


_RATE_CACHE = None
_RATE_CACHE_MONO = 0
_RATE_LOCK = asyncio.Lock()
RATE_REFRESH_SECONDS = 3600


async def current_rate(force=False):
    global _RATE_CACHE, _RATE_CACHE_MONO
    async with _RATE_LOCK:
        now = time.monotonic()
        if (not force and _RATE_CACHE is not None
                and now - _RATE_CACHE_MONO < RATE_REFRESH_SECONDS
                and not _RATE_CACHE.stale):
            return _RATE_CACHE
        rate = await asyncio.to_thread(currency.fetch_rate)
        if rate.stale:
            raise currency.CurrencyError("Exchange-rate data is stale")
        _RATE_CACHE, _RATE_CACHE_MONO = rate, time.monotonic()
        return rate


async def refresh_rates_forever():
    
    while True:
        try:
            rate = await current_rate(force=True)
            log.info("USD rate refreshed: %s IRT/USD, source time %s",
                     rate.toman_per_usd, rate.updated_utc.isoformat())
        except Exception as exc:
            log.warning("USD rate refresh failed: %s", type(exc).__name__)
        await asyncio.sleep(RATE_REFRESH_SECONDS)


def fmt_record(record):
    if "legacy" in record:
        return "قدیمی · واحد نامشخص"
    amount, code = record["amount"], record["currency"]
    return f"{amount} {code}"


def parse_price(text):
    return currency.parse_amount(text)


                                                                               
            
                                                                               

_STYLE_FLAGS = {"primary": "bg_primary", "success": "bg_success", "danger": "bg_danger"}
_STYLE_OK = hasattr(tl_types, "KeyboardButtonStyle")          # Telethon >= layer 222 (1.45.0 is layer 229)
_STYLE_WARNED = False


def _auto_style(data):
    """Default colour per button purpose (green = go, red = stop/destructive, blue = navigation)."""
    d = data.decode("utf-8", "ignore") if isinstance(data, bytes) else str(data)
    if d == "cancel" or d.endswith((":del", ":no", ":reject", ":delete")) or d in ("panel:ban",):
        return "danger"
    if (d.endswith((":ok", ":yes", ":approve", ":confirm", ":request", ":done"))
            or d.startswith("withdraw:paid") or d in ("menu:sell", "menu:withdraw", "panel:unban")):
        return "success"
    if d.startswith(("menu:", "panel:")) or d in ("home", "price:back", "region:back", "panel:home"):
        return "primary"
    return None


def _strip_lead(text, emoji):
    for e in (emoji, emoji.rstrip("\ufe0f"), emoji + "\ufe0f"):
        if e and text.startswith(e):
            return text[len(e):].lstrip() or text
    return text


def btn(text, data, icon=None, style=None):
    """Inline button with colour (Bot API 9.4 style) and a premium-emoji icon.

    The icon is `icon` if given, otherwise the label's leading emoji when it has a premium id.
    Falls back to a plain button if this Telethon build can't express styles."""
    global _STYLE_WARNED
    if isinstance(data, str):
        data = data.encode()
    style = style or _auto_style(data)
    doc_id, label = None, text
    if PREMIUM_ENABLED:
        key = icon or next((k for k in PREMIUM_KEYS if text.startswith(k)), None)
        doc_id = PREMIUM_EMOJI.get(key) if key else None
        if doc_id:
            label = _strip_lead(text, key)
    if _STYLE_OK and (style in _STYLE_FLAGS or doc_id):
        try:
            flags = {_STYLE_FLAGS[style]: True} if style in _STYLE_FLAGS else {}
            return tl_types.KeyboardButtonCallback(
                text=label, data=data, style=tl_types.KeyboardButtonStyle(icon=doc_id, **flags))
        except (TypeError, AttributeError, ValueError):
            if not _STYLE_WARNED:
                _STYLE_WARNED = True
                log.warning("button styles unsupported by this Telethon build; using plain buttons")
    return Button.inline(text, data)


def country_list_text(disabled):
    codes = sorted(COUNTRIES)
    closed = " ".join(flag_emoji(code) for code in codes if code in disabled)
    opened = " ".join(flag_emoji(code) for code in codes if code not in disabled) or tr("countries_none")
    prefix = f"{tr('countries_closed')}\n\n{closed}\n\n\n" if closed else ""
    return f"{prefix}{tr('countries_open')}\n\n{opened}"


async def show_country_list(uid):
    await set_ui(uid, country_list_text(await disabled_regions()), buttons=back_kb())


def main_kb():
    return [[btn(tr("info_btn"), b"menu:info", "💡"), btn(tr("sell"), b"menu:sell", "🚀")],
            [btn(tr("my_info_btn"), b"menu:profile", "🙂"),
             btn(tr("withdraw_withdraw_btn"), b"menu:withdraw", "💰")],
            [btn(tr("support_btn"), b"menu:support", "🎧")],
            [btn(tr("countries_btn"), b"menu:countries", "🚩")]]


def back_kb():
    return [[btn(tr("back"), b"home", "🔙")]]


def cancel_kb():
    return [[btn(tr("cancel_btn"), b"cancel", "❌")]]


def language_kb():
    buttons = [btn(label, ("lang:" + code).encode())
               for code, label in i18n.LANGUAGES.items()]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


async def user_language(uid):
    profile = await asyncio.to_thread(user_store.ensure_user, DB_PATH, uid)
    language = profile.get("language")
    i18n.LANGUAGE.set(language or "fa")
    return language


async def show_language_picker(uid):
    return await ui_send(uid, i18n.PICK_LANGUAGE, buttons=language_kb())


async def require_language(uid):
    if await user_language(uid):
        return True
    await show_language_picker(uid)
    return False


async def show_welcome(uid, sender=None):
    name = " ".join(x for x in [getattr(sender, "first_name", None),
                               getattr(sender, "last_name", None)] if x) or tr("friend")
    await set_ui(uid, tr("welcome", name=escape(name)), buttons=main_kb())


async def show_profile(uid):
    profile = await asyncio.to_thread(user_store.ensure_user, DB_PATH, uid)
    timestamp = profile["first_started_at"]
    started = (datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
               if timestamp is not None else tr("unknown_date"))
    await set_ui(uid, tr("my_info", user_id=profile["user_id"], started=started,
                         sold=profile["numbers_sold"], balance=display_usd(profile["balance"]) + " USD",
                         withdrawn=display_usd(profile["withdrawn"]) + " USD"), buttons=back_kb())


def display_usd(micros):
    return f"{Decimal(micros) / Decimal(1_000_000):,.6f}".rstrip("0").rstrip(".")


def parse_usd_micros(text):
    
    parsed = currency.parse_amount((text or "").strip() + " USD")
    if not parsed or parsed[0] != "USD" or parsed[1] <= 0:
        return None
    micros = int(parsed[1] * 1_000_000)
    return micros if 0 < micros <= withdrawal_store.MAX_SQLITE_INT else None


def withdraw_kb():
    return [[btn(tr("withdraw_request_btn"), b"withdraw:request", "💰")],
            [btn(tr("back"), b"home", "🔙")]]


async def show_withdrawal_page(uid):
    profile = await asyncio.to_thread(user_store.ensure_user, DB_PATH, uid)
    balance, withdrawn = profile["balance"], profile["withdrawn"]
    try:
        rate = await current_rate()
        balance_toman = currency.format_irt(Decimal(balance) / 1_000_000 * rate.toman_per_usd)
        withdrawn_toman = currency.format_irt(Decimal(withdrawn) / 1_000_000 * rate.toman_per_usd)
        rate_info = tr("withdraw_rate_info", rate=currency.format_irt(rate.toman_per_usd))
    except Exception as exc:
        log.warning("withdrawal page FX unavailable: %s", type(exc).__name__)
        balance_toman = withdrawn_toman = tr("withdraw_unavailable")
        rate_info = tr("withdraw_rate_unavailable")
    await set_ui(uid, tr("withdraw_page", balance=display_usd(balance), withdrawn=display_usd(withdrawn),
                         balance_toman=balance_toman, withdrawn_toman=withdrawn_toman,
                         rate_info=rate_info), buttons=withdraw_kb())


async def start_withdrawal(uid):
    st = STATE.setdefault(uid, {})
    if st.get("step") or st.get("busy"):
        await set_ui(uid, tr("withdraw_flow_busy"), buttons=cancel_kb())
        return
    profile = await asyncio.to_thread(user_store.ensure_user, DB_PATH, uid)
    if profile["balance"] <= 0:
        await set_ui(uid, tr("withdraw_no_balance"), buttons=withdraw_kb())
        return
    st["step"] = STEP_WITHDRAW_AMOUNT
    await set_ui(uid, tr("withdraw_ask_amount", balance=display_usd(profile["balance"])),
                 buttons=cancel_kb())


async def handle_withdraw_amount(uid, text):
    st = STATE.get(uid)
    if not st or st.get("step") != STEP_WITHDRAW_AMOUNT or st.get("busy"):
        return
    st["busy"] = True
    try:
        amount = parse_usd_micros(text)
        profile = await asyncio.to_thread(user_store.get_user, DB_PATH, uid)
        if STATE.get(uid) is not st or st.get("step") != STEP_WITHDRAW_AMOUNT:
            return
        if not amount or not profile or amount > profile["balance"]:
            await set_ui(uid, tr("withdraw_invalid_amount"), buttons=cancel_kb())
            return
        st.update(step=STEP_WITHDRAW_WALLET, withdraw_amount=amount)
        await set_ui(uid, tr("withdraw_ask_wallet", amount=display_usd(amount)), buttons=cancel_kb())
    finally:
        st["busy"] = False


_WITHDRAW_NOTIFY_LOCK = asyncio.Lock()


async def process_withdraw_notifications():
    
    async with _WITHDRAW_NOTIFY_LOCK:
        for request in await asyncio.to_thread(withdrawal_store.pending_notifications, DB_PATH, "admin"):
            delivered = False
            for admin_id in sorted(ADMIN_IDS):
                try:
                    await notify_send(admin_id,
                        "💰 <b>درخواست برداشت #{id}</b>\n\n"
                        "🙂 شناسه کاربر: <code>{user_id}</code>\n"
                        "💰 مبلغ درخواست: <b>{amount} USD</b>\n"
                        "💎 کیف پول TON: <code>{wallet}</code>\n\n"
                        "پس از پرداخت دستی، دکمه زیر را بزن.".format(
                            id=request["public_tag"], user_id=request["user_id"],
                            amount=display_usd(request["amount_microusd"]),
                            wallet=escape(request["wallet"])),
                        buttons=[[btn("پرداخت شد", f"withdraw:paid:{request['id']}", "🆗")]])
                    delivered = True
                except Exception as exc:
                    log.warning("withdrawal admin notification failed for request %s admin %s: %s",
                                request["id"], admin_id, type(exc).__name__)
            if delivered:
                await asyncio.to_thread(withdrawal_store.mark_notification, DB_PATH, request["id"], "admin")
        for request in await asyncio.to_thread(withdrawal_store.pending_notifications, DB_PATH, "user"):
            try:
                profile = await asyncio.to_thread(user_store.get_user, DB_PATH, request["user_id"])
                token = i18n.LANGUAGE.set((profile or {}).get("language") or "fa")
                try:
                    await notify_send(request["user_id"], tr("withdraw_paid", id=request["public_tag"],
                        amount=display_usd(request["amount_microusd"])))
                finally:
                    i18n.LANGUAGE.reset(token)
                await asyncio.to_thread(withdrawal_store.mark_notification, DB_PATH, request["id"], "user")
            except Exception as exc:
                log.warning("withdrawal user notification failed for request %s: %s",
                            request["id"], type(exc).__name__)


async def withdrawal_notification_loop():
    while True:
        try:
            await process_withdraw_notifications()
        except Exception:
            log.exception("withdrawal outbox processing failed")
        await asyncio.sleep(30)


async def notify_withdrawals_safely():
    try:
        await process_withdraw_notifications()
    except Exception:
        log.exception("withdrawal outbox processing failed; will retry")


async def handle_withdraw_wallet(uid, text):
    st = STATE.get(uid)
    if not st or st.get("step") != STEP_WITHDRAW_WALLET or st.get("busy"):
        return
    try:
        wallet = validate_ton_address((text or "").strip())
    except TonAddressError:
        await set_ui(uid, tr("withdraw_bad_wallet"), buttons=cancel_kb())
        return
    st["busy"] = True
    try:
        try:
            request = await asyncio.to_thread(withdrawal_store.create_request, DB_PATH, uid,
                                              st["withdraw_amount"], wallet.original, wallet.canonical_raw)
        except withdrawal_store.InsufficientFunds:
            st.pop("withdraw_amount", None)
            st.pop("step", None)
            await set_ui(uid, tr("withdraw_balance_changed"), buttons=withdraw_kb())
            return
        still_current = STATE.get(uid) is st
        st.pop("withdraw_amount", None)
        st.pop("step", None)
        try:
            receipt = tr("withdraw_submitted", id=request["public_tag"],
                         amount=display_usd(request["amount_microusd"]))
            if still_current:
                await set_ui(uid, receipt, buttons=back_kb())
            else:
                await notify_send(uid, receipt)
        finally:
                                                                                 
            asyncio.create_task(notify_withdrawals_safely())
    finally:
        st["busy"] = False


                                                                               
                          
                                                                               
                                                                                 
                                                                                 
                                                                                    
                         
                                                                                
                                                                                
                                                                                    
                                                                                      
                                                                                      

PREMIUM_EMOJI = {}                          
PREMIUM_KEYS = []                                                            
PREMIUM_ENABLED = True                                                           

USED_EMOJI = (
    "🚀", "💎", "👋", "🔥", "✨", "💡", "⚠️", "🔒", "📞", "❌", "🔑", "🎉",
    "🆗", "👍", "⌛️", "⏳", "👀", "⛔️", "🖥", "⚡️", "🌍", "👤", "📲", "🗑",
    "🔙", "🚫", "💰", "📌", "✅", "💳", "◀️", "▶️",
    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣",
)


def _u16_len(s):
    return len(s.encode("utf-16-le")) // 2


def _emoji_alt_ok(alt):
    
    return bool(alt) and not alt.isascii()


async def load_premium_emoji(client):
    
    global PREMIUM_KEYS
    found = {}

                                                                                     
    try:
        with open(EMOJI_MAP_FILE, encoding="utf-8") as f:
            file_map = {k: int(v) for k, v in json.load(f).items()}
        found.update({k: v for k, v in file_map.items() if _emoji_alt_ok(k)})
        log.info("emoji map: %d ids from %s", len(found), os.path.basename(EMOJI_MAP_FILE))
    except FileNotFoundError:
        log.info("emoji_map.json not found — run discover_emoji.py once for full coverage")
    except Exception:
        log.warning("emoji_map.json unreadable", exc_info=True)

                                                               
    for name in EMOJI_PACKS:
        try:
            res = await client(
                functions.messages.GetStickerSetRequest(
                    stickerset=tl_types.InputStickerSetShortName(short_name=name), hash=0
                )
            )
        except Exception as exc:
            log.info("emoji pack %s skipped (%s)", name, type(exc).__name__)
            continue

        before = len(found)
        for doc in res.documents or []:
            for attr in doc.attributes or []:
                if not isinstance(attr, tl_types.DocumentAttributeCustomEmoji):
                    continue                                                          
                alt = (attr.alt or "").strip()
                if _emoji_alt_ok(alt):
                    found.setdefault(alt, doc.id)
        log.info("emoji pack %s: %d custom emoji", name, len(found) - before)

    if not found:
        log.warning("no custom emoji available — plain emoji only")
        return

    PREMIUM_EMOJI.clear()
    PREMIUM_EMOJI.update(found)
                                                            
    for alt, doc in list(PREMIUM_EMOJI.items()):
        if alt.endswith("\ufe0f"):
            PREMIUM_EMOJI.setdefault(alt[:-1], doc)
        elif len(alt) == 1:
            PREMIUM_EMOJI.setdefault(alt + "\ufe0f", doc)

    PREMIUM_KEYS = sorted(PREMIUM_EMOJI, key=len, reverse=True)
    have = [e for e in USED_EMOJI if e in PREMIUM_EMOJI]
    log.info(
        "premium emoji: %d ids, %d/%d of the bot's own emoji covered: %s",
        len(PREMIUM_EMOJI), len(have), len(USED_EMOJI), " ".join(have) or "-",
    )


def render(src):
    
    text, entities = html_ext.parse(src)
    if not (PREMIUM_ENABLED and PREMIUM_KEYS):
        return text, entities

    hits = []
    for key in PREMIUM_KEYS:
                                                                              
                                                                              
        if any(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in key):
            continue
        start = 0
        while True:
            i = text.find(key, start)
            if i < 0:
                break
            hits.append((i, len(key), PREMIUM_EMOJI[key]))
            start = i + len(key)

                                                   
    hits.sort(key=lambda h: (h[0], -h[1]))
    end = -1
    for i, ln, doc_id in hits:
        if i < end:
            continue
        end = i + ln
        entities.append(
            tl_types.MessageEntityCustomEmoji(
                offset=_u16_len(text[:i]),
                length=_u16_len(text[i:i + ln]),
                document_id=doc_id,
            )
        )

    entities.sort(key=lambda e: (e.offset, -e.length))
    return text, entities


def _premium_refused(exc):
    
    if isinstance(exc, (errors.PremiumAccountRequiredError, errors.DocumentInvalidError)):
        return True
    text = str(exc).upper()
    return any(k in text for k in ("PREMIUM", "CUSTOM_EMOJI", "DOCUMENT_INVALID", "DOCUMENT FILE WAS INVALID"))


def premium_state_load():
    
    global PREMIUM_ENABLED
    if os.getenv("PREMIUM_EMOJI", "1").lower() in ("0", "false", "no", "off"):
        PREMIUM_ENABLED = False
        return
    try:
        with open(EMOJI_STATE_FILE, encoding="utf-8") as f:
            PREMIUM_ENABLED = bool(json.load(f).get("premium", True))
    except Exception:
        pass


def premium_state_save():
    try:
        with open(EMOJI_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"premium": PREMIUM_ENABLED}, f)
    except Exception:
        log.debug("could not persist premium state", exc_info=True)


async def _deliver(call, src, **kwargs):
    
    global PREMIUM_ENABLED
    for attempt in (0, 1):
        text, entities = render(src)
        try:
            return await call(text, entities, **kwargs)
        except errors.RPCError as exc:
            if attempt or not _premium_refused(exc):
                raise
            PREMIUM_ENABLED = False
            premium_state_save()
            log.warning(
                "custom emoji refused (%s) — this bot may need a Fragment username; "
                "switching to plain emoji for good", type(exc).__name__,
            )


async def notify_send(uid, src, buttons=None):
    
    async def call(text, entities, buttons=None):
        return await bot.send_message(
            uid, text, buttons=buttons, formatting_entities=entities,
            parse_mode=None, link_preview=False,
        )
    return await _deliver(call, src, buttons=buttons)


async def ui_send(uid, src, buttons=None):
    async def call(text, entities, buttons=None):
        return await bot.send_message(
            uid, text, buttons=buttons, formatting_entities=entities,
            parse_mode=None, link_preview=False,
        )

    msg = await _deliver(call, src, buttons=buttons)
    STATE.setdefault(uid, {})["ui_msg"] = msg.id
    return msg


def code_kb():
    return [
        [btn("❶", b"code:1"), btn("❷", b"code:2"), btn("❸", b"code:3")],
        [btn("❹", b"code:4"), btn("❺", b"code:5"), btn("❻", b"code:6")],
        [btn("❼", b"code:7"), btn("❽", b"code:8"), btn("❾", b"code:9")],
        [btn("⌫", b"code:del"), btn("⓿", b"code:0"), btn(tr("confirm"), b"code:ok", "🆗")],
        [btn(tr("cancel_btn"), b"cancel", "❌")],
    ]


def phone_region(phone):
    
    try:
        number = phonenumbers.parse(phone, None)
        region = phonenumbers.region_code_for_number(number)
        return region if region in COUNTRIES else None
    except phonenumbers.NumberParseException:
        return None


def code_text(phone, code, quote=None):
    shown = " · ".join(code) if code else "—"
    region = phone_region(phone)
    flag = flag_emoji(region) if region else "🌐"
    text = tr("code_prefix", flag=flag, phone=phone, code=shown)
    if quote is not None:
        text += "\n\n" + tr("sale_offer", amount=display_usd(quote["usd_micros"]))
    return text


async def set_ui(uid, src, buttons=None):
    
    st = STATE.setdefault(uid, {})
    mid = st.get("ui_msg")
    if mid is not None:
        async def call(text, entities, buttons=None):
            return await bot.edit_message(
                uid, mid, text, buttons=buttons, formatting_entities=entities,
                parse_mode=None, link_preview=False,
            )

        try:
            return await _deliver(call, src, buttons=buttons)
        except errors.MessageNotModifiedError:
            return None
        except errors.MessageIdInvalidError:
            st["ui_msg"] = None
    return await ui_send(uid, src, buttons)


async def ack(event, text="", alert=False):
    try:
        await event.answer(text, alert=alert)
    except Exception:
        pass


                                                                               
                          
                                                                               

PRICE_PAGE_SIZE = 14


def normalize_country_search(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه"}))
    return " ".join("".join(c for c in text if not unicodedata.combining(c))
                    .replace("\u200c", " ").split())


def country_search_codes(query=""):
    needle = normalize_country_search(query)
    if not needle:
        return list(COUNTRIES)
    return [iso for iso, country in COUNTRIES.items()
            if any(needle in normalize_country_search(value)
                   for value in (iso, country["fa"], country["name"]))]


def price_label(iso, price, disabled=False):
    label = f"{flag_emoji(iso)} {COUNTRIES[iso]['fa']}" + (" · ⛔️ خرید غیرفعال" if disabled else "")
    if price is not None:
        label += f" · {fmt_record(price)}"
    return label


def price_panel_text(prices, page, note="", query=""):
    codes = country_search_codes(query)
    total_pages = max(1, (len(codes) + PRICE_PAGE_SIZE - 1) // PRICE_PAGE_SIZE)
    explicit = sum(1 for k in prices if k != DEFAULT_KEY)
    default = prices.get(DEFAULT_KEY)
    lines = ["💰 <b>قیمت هر کشور</b>", ""]
    if note:
        lines += [note, ""]
    lines.append(
        "🌍 قیمت پیش‌فرض: <b>{value}</b>".format(
            value=fmt_record(default) if default is not None else "ثبت نشده"
        )
    )
    lines.append("📌 قیمت اختصاصی: <b>{n}</b> کشور".format(n=explicit))
    lines.append("")
    if query:
        lines.append("🔎 نتیجه جستجو برای «{query}»: {count} کشور".format(
            query=escape(query), count=len(codes)))
        if not codes:
            lines.append("کشوری پیدا نشد؛ دوباره جستجو کن یا همه کشورها رو ببین.")
        lines.append("")
    lines.append(
        "صفحه {p} از {t} — روی هر کشور بزن تا قیمتش رو ست کنی.".format(p=page + 1, t=total_pages)
    )
    return "\n".join(lines)


def price_page_buttons(prices, page, query="", disabled=None):
    disabled = disabled or set()
    codes = country_search_codes(query)
    total_pages = max(1, (len(codes) + PRICE_PAGE_SIZE - 1) // PRICE_PAGE_SIZE)
    chunk = codes[page * PRICE_PAGE_SIZE:(page + 1) * PRICE_PAGE_SIZE]
    rows = [
        [btn(price_label(iso, prices.get(iso), iso in disabled), f"price:c:{iso}") for iso in pair]
        for pair in (chunk[i:i + 2] for i in range(0, len(chunk), 2))
    ]
    rows.append([btn("🔎 جستجوی کشور", b"price:search")])
    rows.append([btn("⛔️ مدیریت خرید کشورها", b"region:list")])
    if query:
        rows.append([btn("🌍 همه کشورها", b"price:all")])
    default = prices.get(DEFAULT_KEY)
    rows.append([
        btn(
            "💰 قیمت پیش‌فرض: {v}".format(
                v=fmt_record(default) if default is not None else "ثبت نشده"
            ),
            b"price:default",
        )
    ])
    nav = []
    if page > 0:
        nav.append(btn("◀️ قبلی", f"price:p:{page - 1}"))
    if page < total_pages - 1:
        nav.append(btn("بعدی ▶️", f"price:p:{page + 1}"))
    if nav:
        rows.append(nav)
    return rows


async def price_ui(uid, src, buttons=None):
    
    st = PRICE_STATE.setdefault(uid, {})
    mid = st.get("ui_msg")
    if mid is not None:
        async def call(text, entities, buttons=None):
            return await bot.edit_message(
                uid, mid, text, buttons=buttons, formatting_entities=entities,
                parse_mode=None, link_preview=False,
            )
        try:
            return await _deliver(call, src, buttons=buttons)
        except errors.MessageNotModifiedError:
            return None
        except errors.MessageIdInvalidError:
            st["ui_msg"] = None
    async def call(text, entities, buttons=None):
        return await bot.send_message(
            uid, text, buttons=buttons, formatting_entities=entities,
            parse_mode=None, link_preview=False,
        )
    msg = await _deliver(call, src, buttons=buttons)
    st["ui_msg"] = msg.id
    return msg


async def show_price_panel(uid, message_id, page=0, note="", query=""):
    prices = await all_prices()
    disabled = await disabled_regions()
    codes = country_search_codes(query)
    page = max(0, min(page, max(0, (len(codes) - 1) // PRICE_PAGE_SIZE)))
    PRICE_STATE[uid] = {"ui_msg": message_id, "page": page, "query": query}
    await price_ui(uid, price_panel_text(prices, page, note, query), price_page_buttons(prices, page, query, disabled))


async def price_prompt(uid, target):
    prices = await all_prices()
    record = prices.get(target)
    current = ""
    if record and "legacy" in record:
        current = "\nقیمت فعلی: قدیمی؛ واحد نامشخص است و تبدیل نمی‌شود."
    elif record:
        try:
            rate = await current_rate()
            converted = currency.convert(record["amount"], record["currency"], rate)
            current = (f"\nقیمت فعلی: {fmt_record(record)}\nUSD: {currency.format_usd(converted['usd'])} · "
                       f"IRR: {currency.format_irr(converted['irr'])} · تومان: {currency.format_irt(converted['irt'])}\n"
                       f"هر دلار: {currency.format_irr(rate.toman_per_usd * 10)} ریال\n"
                       f"نرخ: {rate.updated_utc.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC} · "
                       '<a href="https://nerkhara.com/en/dollar/">NerkhAra</a>')
        except Exception as exc:
            log.warning("price display FX lookup failed: %s", type(exc).__name__)
            current = "\nقیمت فعلی ثبت شده؛ نرخ تازه در دسترس نیست و تبدیل نمایش داده نشد."
    if target == DEFAULT_KEY:
        src = (
            "💰 <b>قیمت پیش‌فرض (همه کشورها)</b> رو بفرست.\n\n"
            "این قیمت برای کشورهایی است که قیمت اختصاصی ندارن.\n"
            "مثلاً: <code>500000 ریال</code>، <code>50000 تومان</code> یا <code>0.183 دلار</code>\n"
            "واحد را حتماً بنویس.\n"
            "0 = حذف پیش‌فرض\n"
            "❌ /cancel برای انصراف."
        )
    else:
        c = COUNTRIES[target]
        src = (
            "💰 قیمت {flag} <b>{name}</b> رو بفرست.\n\n"
            "مثلاً: <code>500000 ریال</code>، <code>50000 تومان</code> یا <code>0.183 دلار</code>\n"
            "واحد را حتماً بنویس.\n"
            "0 = حذف قیمت اختصاصی (استفاده از پیش‌فرض)\n"
            "❌ /cancel برای انصراف."
        ).format(flag=flag_emoji(target), name=c["fa"])
    src += current
    buttons = []
    if target != DEFAULT_KEY:
        off = target in await disabled_regions()
        buttons.append([btn("✅ فعال کردن خرید" if off else "⛔️ غیرفعال کردن خرید", f"region:toggle:{target}", style="success" if off else "danger")])
    buttons.append([btn("🔙 بازگشت به پنل", b"price:back")])
    await price_ui(uid, src, buttons)


async def show_region_panel(uid, event):
    disabled = await disabled_regions(); st = PRICE_STATE[uid]
    codes = country_search_codes(st.get("query", "")); total=max(1,(len(codes)+PRICE_PAGE_SIZE-1)//PRICE_PAGE_SIZE)
    page=max(0,min(st.get("region_page",st.get("page",0)),total-1)); st["region_page"]=page
    chunk=codes[page*PRICE_PAGE_SIZE:(page+1)*PRICE_PAGE_SIZE]
    rows=[[btn(("✅ فعال کردن " if iso in disabled else "⛔️ غیرفعال کردن ")+price_label(iso,None),f"region:toggle:{iso}",style="success" if iso in disabled else "danger")] for iso in chunk]
    nav=[]
    if page: nav.append(btn("◀️ قبلی",f"region:page:{page-1}"))
    if page+1<total: nav.append(btn("بعدی ▶️",f"region:page:{page+1}"))
    if nav: rows.append(nav)
    rows.append([btn("🔙 قیمت‌ها",b"region:back")])
    await price_ui(uid,f"⛔️ برای تغییر وضعیت خرید کشور بزن. صفحه {page+1} از {total}",rows)

async def handle_price_callback(uid, event, data):
    st = PRICE_STATE.get(uid)
    if not st or st.get("ui_msg") != event.message_id:
        await ack(event, "پنل منقضی شده؛ /price رو بزن.", True)
        return
    if data.startswith("price:p:"):
        part = data.split(":")[-1]
        query = st.get("query", "")
        total_pages = max(1, (len(country_search_codes(query)) + PRICE_PAGE_SIZE - 1) // PRICE_PAGE_SIZE)
        if not part.isascii() or not part.isdigit() or int(part) >= total_pages:
            await ack(event, "صفحه نامعتبره.", True)
            return
        page = int(part)
        await ack(event)
        await show_price_panel(uid, event.message_id, page, query=query)
    elif data == "price:search":
        st.pop("target", None)
        st["searching"] = True
        await ack(event)
        await price_ui(uid, "🔎 اسم کشور رو به فارسی یا انگلیسی، یا کد دوحرفی کشور رو بفرست.\n\n"
                       "❌ برای لغو /cancel رو بزن.",
                       [[btn("🔙 بازگشت به پنل", b"price:back")]])
    elif data == "price:all":
        await ack(event)
        await show_price_panel(uid, event.message_id)
    elif data.startswith("price:c:"):
        iso = data.split(":")[2]
        if iso not in COUNTRIES:
            await ack(event)
            return
        PRICE_STATE.setdefault(uid, {})["target"] = iso
        await ack(event)
        await price_prompt(uid, iso)
    elif data == "price:default":
        PRICE_STATE.setdefault(uid, {})["target"] = DEFAULT_KEY
        await ack(event)
        await price_prompt(uid, DEFAULT_KEY)
    elif data == "price:back":
        st = PRICE_STATE.get(uid, {})
        page = st.get("page", 0)
        await ack(event)
        await show_price_panel(uid, event.message_id, page, query=st.get("query", ""))


async def handle_price_input(uid, event):
    st = PRICE_STATE.get(uid)
    if not st:
        return
    if st.get("searching"):
        query = (event.raw_text or "").strip()
        if not query or not normalize_country_search(query) or len(query) > 80:
            await price_ui(uid, "❌ نام معتبر کشور رو بفرست (حداکثر ۸۰ کاراکتر).",
                           [[btn("🔙 بازگشت به پنل", b"price:back")]])
            return
        await show_price_panel(uid, st.get("ui_msg"), query=query)
        return
    if "target" not in st:
        return
    target = st["target"]
    parsed = parse_price(event.raw_text or "")
    if parsed is None:
        await price_ui(
            uid,
            "❌ قالب نامعتبره. مثلاً 500000 ریال، 50000 تومان یا 0.183 دلار بفرست؛ /cancel برای انصراف.",
            [[btn("🔙 بازگشت به پنل", b"price:back")]],
        )
        return

    page = st.get("page", 0)
    label = "پیش‌فرض" if target == DEFAULT_KEY else f"{flag_emoji(target)} {COUNTRIES[target]['fa']}"
    if parsed[1] == 0:
        await delete_price(target)
        note = f"✅ قیمت {label} حذف شد."
    else:
        try:
            rate = await current_rate()
            converted = currency.convert(parsed[1], parsed[0], rate)
        except Exception as exc:
            log.warning("price FX lookup failed: %s", type(exc).__name__)
            await price_ui(uid, "❌ نرخ تازهٔ ارز در دسترس نیست؛ قیمت ذخیره نشد. دوباره تلاش کن.",
                           [[btn("🔙 بازگشت به پنل", b"price:back")]])
            return
        await set_price(target, parsed[1], parsed[0])
        record = {"amount": parsed[1], "currency": parsed[0]}
        note = (f"✅ قیمت {label} ذخیره شد: {fmt_record(record)}\n"
                f"USD: {currency.format_usd(converted['usd'])} · IRR: {currency.format_irr(converted['irr'])} · "
                f"تومان: {currency.format_irt(converted['irt'])}\n"
                f"هر دلار: {currency.format_irr(rate.toman_per_usd * 10)} ریال\n"
                f"نرخ به‌روزرسانی: {rate.updated_utc.astimezone(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
                'منبع: <a href="https://nerkhara.com/en/dollar/">NerkhAra</a>')

    await show_price_panel(uid, st.get("ui_msg"), page, note, query=st.get("query", ""))


def build_user_client():
    return TelegramClient(
        StringSession(),
        API_ID,
        API_HASH,
        device_model=DEVICE_MODEL,
        system_version=SYSTEM_VERSION,
        app_version=APP_VERSION,
        lang_code="en",
        system_lang_code="en-US",
    )


async def reset_state(uid, *, cancel_pending=True):
    previous = STATE.get(uid)
    if previous and previous.get('cleanup_scheduled') and not previous.get('_reset_lock_owned'):
        previous['resetting'] = True
        if cancel_pending:
            await asyncio.to_thread(pending_session_store.cancel, DB_PATH, previous['account_id'])
        async with pending_session_lock(previous['tg_user_id']):
            if STATE.get(uid) is not previous:
                return
            previous['_reset_lock_owned'] = True
            try:
                await reset_state(uid, cancel_pending=cancel_pending)
            finally:
                previous.pop('_reset_lock_owned', None)
        return
    st = STATE.pop(uid, None)
    if not st:
        return
    task = st.get("logout_task")
    if task is not None and task is not asyncio.current_task():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    client = st.get("client")
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            log.debug("disconnect failed for %s", uid, exc_info=True)


                                                                               
                             
                                                                               

async def other_authorizations(client):
    res = await client(functions.account.GetAuthorizationsRequest())
    return [a for a in res.authorizations if not getattr(a, "current", False)]


def _device_icon(platform):
    p = (platform or "").lower()
    if any(k in p for k in ("android", "ios", "iphone", "ipad")):
        return "📱"
    if any(k in p for k in ("windows", "macos", "linux", "os x")):
        return "🖥"
    return "📲"


def fmt_auth(a):
    def dt(value):
        try:
            return value.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "?"

    name = escape(getattr(a, "device_model", None) or tr("unknown_device"))
    platform = escape(getattr(a, "platform", None) or "-")
    country = escape(getattr(a, "country", None) or "-")
    ip = escape(getattr(a, "ip", None) or "-")
    return (
        "{icon} <b>{name}</b>\n"
        "     🧩 {platform} · 🌍 {country}\n"
        "     ⚡️ {ip} · 🗓 {created}"
    ).format(
        icon=_device_icon(platform), name=name, platform=platform,
        country=country, ip=ip, created=dt(getattr(a, "date_created", None)),
    )


def sessions_report(others):
    if not others:
        return tr("no_devices")
    lines = [tr("devices_title"), ""]
    lines += [fmt_auth(a) for a in others]
    return "\n".join(lines)


def logout_kb():
    return [[btn(tr("logged_out"), b"check:done", "🆗")]]


                                                                               
      
                                                                               

class SaleQuoteError(Exception):
    def __init__(self, key):
        self.key = key
        super().__init__(key)


async def sale_quote_for_phone(phone):
    
    region = phone_region(phone)
    if region and region in await disabled_regions():
        raise SaleQuoteError("sale_region_disabled")
    prices = await all_prices()
    price_country = region if region and region in prices else DEFAULT_KEY
    record = prices.get(price_country)
    if not record or "legacy" in record:
        raise SaleQuoteError("sale_not_priced")
    amount, code = record.get("amount"), record.get("currency")
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0 or code not in ("USD", "IRT", "IRR"):
        raise SaleQuoteError("sale_too_small")
    rate = None
    if code == "USD":
        usd = amount
    else:
        try:
            rate = await current_rate()
            with localcontext() as ctx:
                ctx.prec = 100
                usd = amount / rate.toman_per_usd / (10 if code == "IRR" else 1)
        except Exception as exc:
            log.warning("sale quote rate unavailable: %s", type(exc).__name__)
            raise SaleQuoteError("sale_rate_unavailable") from exc
    with localcontext() as ctx:
        ctx.prec = 100
        micros = int((usd * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not 0 < micros <= withdrawal_store.MAX_SQLITE_INT:
        raise SaleQuoteError("sale_too_small")
    return {"region": region, "price_country": price_country,
            "source_amount": str(amount), "source_currency": code, "usd_micros": micros,
            "rate_toman_per_usd": str(rate.toman_per_usd) if rate else None,
            "rate_updated_utc": rate.updated_utc.isoformat() if rate else None}


async def start_sell(uid, event):
    await reset_state(uid, cancel_pending=False)
    STATE[uid] = {"step": STEP_PHONE, "ui_msg": event.message_id}
    await set_ui(uid, tr("ask_phone"), buttons=cancel_kb())


async def handle_phone(uid, phone_raw):
    st = STATE.get(uid)
    if not st or st.get("step") != STEP_PHONE or st.get("busy"):
        return

    phone = re.sub(r"[\s\-().]", "", phone_raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif not phone.startswith("+"):
        phone = "+" + phone

    if not re.fullmatch(r"\+\d{7,15}", phone):
        await set_ui(uid, tr("invalid_phone"), buttons=cancel_kb())
        return

    st["busy"] = True
    client = None
    try:
        try:
            quote = await sale_quote_for_phone(phone)
        except SaleQuoteError as exc:
            if STATE.get(uid) is st:
                await set_ui(uid, tr(exc.key), buttons=cancel_kb())
            return
        if STATE.get(uid) is not st or st.get("step") != STEP_PHONE:
            return
        if st.get("client") is not None:
            await st["client"].disconnect()
        client = build_user_client()
        st["client"] = client
        await client.connect()
        if STATE.get(uid) is not st:
            await client.disconnect()
            return
        region = phone_region(phone)
        if region and region in await disabled_regions():
            await client.disconnect(); st.pop("client", None)
            await set_ui(uid, tr("sale_region_disabled"), buttons=cancel_kb()); return
        sent = await client.send_code_request(phone)
        if STATE.get(uid) is not st:
            await client.disconnect()
            return
        st.update(client=client, phone=phone, phone_code_hash=sent.phone_code_hash,
                  code="", step=STEP_CODE, sale_quote=quote)
        await set_ui(uid, code_text(phone, "", quote), buttons=code_kb())
    except errors.FloodWaitError as exc:
        if client is not None:
            await client.disconnect()
        if STATE.get(uid) is st:
            log.warning("flood on send_code_request %s: %ss", phone, exc.seconds)
            await set_ui(uid, tr("phone_flood", m=max(1, (exc.seconds + 59) // 60)), buttons=back_kb())
            await reset_state(uid)
    except errors.PhoneNumberInvalidError:
        if client is not None:
            await client.disconnect()
        if STATE.get(uid) is st:
            st["client"] = None
            await set_ui(uid, tr("retry_phone"), buttons=cancel_kb())
    except errors.PhoneNumberUnoccupiedError:
        if client is not None:
            await client.disconnect()
        if STATE.get(uid) is st:
            await set_ui(uid, tr("unregistered_phone"), buttons=back_kb())
            await reset_state(uid)
    except Exception:
        log.exception("send_code_request failed for %s", phone)
        if client is not None:
            await client.disconnect()
        if STATE.get(uid) is st:
            await set_ui(uid, tr("generic_error"), buttons=back_kb())
            await reset_state(uid)
    finally:
        st["busy"] = False


async def handle_code_digit(uid, event, action):
    st = STATE.get(uid)
    if not st or st.get("step") not in (STEP_CODE, STEP_2FA) or st.get("client") is None:
        await ack(event, tr("step_expired"), True)
        return
    if st.get("step") == STEP_2FA:
        await ack(event, tr("needs_password"), True)
        return
    if st.get("busy"):
        await ack(event)
        return

    if action == "del":
        st["code"] = st["code"][:-1]
    elif action == "ok":
        if len(st["code"]) < 4:
            await ack(event, tr("incomplete_code"), True)
            return
        st["busy"] = True
        try:
            await set_ui(uid, tr("checking_code"))
            await submit_code(uid)
        finally:
            st["busy"] = False
        await ack(event)
        return
    else:
        if len(st["code"]) >= 6:
            await ack(event, tr("code_too_long"), True)
            return
        st["code"] += action

    await set_ui(uid, code_text(st["phone"], st["code"], st.get("sale_quote")), buttons=code_kb())
    await ack(event)


async def submit_code(uid):
    st = STATE.get(uid)
    client = st["client"]
    try:
        await client.sign_in(phone=st["phone"], code=st["code"], phone_code_hash=st["phone_code_hash"])
    except errors.SessionPasswordNeededError:
        st["step"] = STEP_2FA
        st["busy"] = False
        await set_ui(uid, tr("ask_2fa"), buttons=cancel_kb())
        return
    except errors.PhoneCodeInvalidError:
        st["code"] = ""
        await set_ui(uid, tr("wrong_code") + code_text(st["phone"], "", st.get("sale_quote")), buttons=code_kb())
        return
    except errors.PhoneCodeExpiredError:
        await set_ui(uid, tr("code_expired"),
                     buttons=back_kb())
        await reset_state(uid)
        return
    except errors.PhoneCodeHashEmptyError:
        await set_ui(uid, tr("login_expired"), buttons=back_kb())
        await reset_state(uid)
        return
    except errors.FloodWaitError as exc:
        await set_ui(uid, tr("wait_seconds", s=exc.seconds),
                     buttons=back_kb())
        return
    except Exception:
        log.exception("sign_in failed for %s", st.get("phone"))
        await set_ui(uid, tr("login_failed"),
                     buttons=back_kb())
        return

    await after_login(uid)


async def handle_2fa(uid, password):
    st = STATE.get(uid)
    if not st or st.get("step") != STEP_2FA or st.get("busy"):
        return
    password = password.strip()
    if not password:
        await set_ui(uid, tr("wrong_2fa"))
        return

    st["busy"] = True
    try:
        await st["client"].sign_in(password=password)
    except errors.PasswordHashInvalidError:
        await set_ui(uid, tr("wrong_2fa"), buttons=cancel_kb())
        return
    except errors.FloodWaitError as exc:
        await set_ui(uid, tr("wait_seconds", s=exc.seconds))
        return
    except Exception:
        log.exception("2fa sign_in failed for %s", st.get("phone"))
        await set_ui(uid, tr("password_login_failed"))
        return
    finally:
        st["busy"] = False

    st["twofa"] = password
    await after_login(uid)


def _is_frozen_error(exc):
                                                                    
    return (type(exc).__name__ in (
        "FrozenMethodInvalidError", "FrozenParticipantMissingError")
        or getattr(exc, "message", "") in (
            "FROZEN_METHOD_INVALID", "FROZEN_PARTICIPANT_MISSING"))


async def account_is_frozen(client):
    
    try:
        result = await client(functions.help.GetAppConfigRequest(hash=0))
    except errors.RPCError as exc:
        if _is_frozen_error(exc):
            return True
        raise
    config = getattr(result, "config", None)
    if not isinstance(config, tl_types.JsonObject):
                                                                                   
        raise RuntimeError("Telegram returned no full account configuration")
    frozen = False
    for item in config.value:
        if item.key not in ("freeze_since_date", "freeze_until_date"):
            continue
        if not isinstance(item.value, tl_types.JsonNumber):
            raise RuntimeError("Telegram returned an invalid freeze timestamp")
        frozen = frozen or item.value.value != 0
    return frozen


async def reject_login(uid, st, message_key, **message_values):
    
    logout_ok = False
    try:
        logout_ok = bool(await st["client"].log_out())
        if not logout_ok:
            log.error("Rejected-account logout was not confirmed for seller %s", uid)
    except Exception:
        log.exception("Rejected-account logout failed for seller %s", uid)
    finally:
        if STATE.get(uid) is st:
            await reset_state(uid)
                                                                      
    if uid not in STATE:
        message = tr(message_key, **message_values)
        if not logout_ok:
            message += "\n\n" + tr("rejected_logout_failed")
        await set_ui(uid, message, buttons=back_kb())


def classify_spambot_reply(text):
    
    if not isinstance(text, str):
        return "unknown"
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold()
                          .replace("\u2019", "'").replace("\u2018", "'").split())
    clean = "good news, no limits are currently applied to your account."
    if normalized in (clean, clean + " you're free as a bird!"):
        return "clean"
    if re.search(r"^unfortunately,.*\byour account (?:is now limited|is currently limited|has been limited|was limited)\b",
                 normalized):
        return "limited"
    return "unknown"


async def spambot_status(client):
    
    old_threshold = client.flood_sleep_threshold
    client.flood_sleep_threshold = 0
    try:
        return await _spambot_exchange(client)
    finally:
        client.flood_sleep_threshold = old_threshold


async def _spambot_exchange(client):
    
    resolved = await client(functions.contacts.ResolveUsernameRequest(username="SpamBot"),
                            flood_sleep_threshold=0)
    if not isinstance(getattr(resolved, "peer", None), tl_types.PeerUser):
        raise RuntimeError("SpamBot did not resolve to a user")
    matches = [user for user in getattr(resolved, "users", [])
               if isinstance(user, tl_types.User) and user.id == resolved.peer.user_id
               and user.bot and (user.username or "").casefold() == "spambot"
               and user.access_hash is not None]
    if len(matches) != 1:
        raise RuntimeError("Could not verify the SpamBot username and bot identity")
    bot_user = matches[0]
    peer = tl_types.InputPeerUser(bot_user.id, bot_user.access_hash)
    async with client.conversation(peer, timeout=15, total_timeout=25,
                                   max_messages=5, exclusive=True) as conversation:
        sent = await conversation.send_message("/start", parse_mode=None,
                                               link_preview=False)
        response = await conversation.get_response(sent)
        if (response.out or response.sender_id != bot_user.id
                or response.chat_id != bot_user.id or response.id <= sent.id
                or response.fwd_from is not None
                or getattr(response, "via_bot_id", None) is not None):
            raise RuntimeError("SpamBot reply was not fresh and directly from the bot")
        reply = getattr(response, "reply_to", None)
        if reply is not None and reply.reply_to_msg_id != sent.id:
            raise RuntimeError("SpamBot reply belongs to another request")
        return classify_spambot_reply(response.raw_text)


async def verify_spambot(uid, st):
    try:
        status = await asyncio.wait_for(spambot_status(st["client"]), timeout=30)
    except Exception as exc:
        log.warning("SpamBot check failed for seller %s (%s)", uid, type(exc).__name__)
        key = "account_frozen" if _is_frozen_error(exc) else "spambot_check_failed"
        await reject_login(uid, st, key)
        return False
    if status != "clean":
        key = "spambot_limited" if status == "limited" else "spambot_check_failed"
        await reject_login(uid, st, key)
        return False
    return STATE.get(uid) is st


async def verify_channel_creation(uid, st):
    client = st["client"]
    old_threshold = client.flood_sleep_threshold
    client.flood_sleep_threshold = 0
    try:
        return await _verify_channel_creation(uid, st)
    finally:
        client.flood_sleep_threshold = old_threshold


async def _verify_channel_creation(uid, st):
    
    client = st["client"]
    title = "Verification-" + secrets.token_hex(12)
    try:
        result = await client(functions.channels.CreateChannelRequest(
            title=title, about="Temporary account verification channel",
            broadcast=True, megagroup=False), flood_sleep_threshold=0)
        matches = [chat for chat in getattr(result, "chats", [])
                   if isinstance(chat, tl_types.Channel) and chat.title == title
                   and chat.creator and chat.broadcast and not chat.megagroup
                   and chat.access_hash is not None]
        if len(matches) != 1:
            raise RuntimeError("Could not identify the newly created test channel")
        channel = matches[0]
    except Exception as exc:
        log.exception("Channel creation verification failed for seller %s (test %s)", uid, title)
        key = "account_frozen" if _is_frozen_error(exc) else "channel_check_failed"
        await reject_login(uid, st, key, title=title)
        return False

    try:
        await client(functions.channels.DeleteChannelRequest(
            channel=tl_types.InputChannel(channel.id, channel.access_hash)),
            flood_sleep_threshold=0)
    except Exception:
        log.exception("Test-channel cleanup failed for seller %s (channel %s, title %s)",
                      uid, channel.id, title)
        await reject_login(uid, st, "channel_cleanup_failed", title=title)
        return False
    return STATE.get(uid) is st


async def after_login(uid):
    st = STATE.get(uid)
    if not st:
        return
    if st.get("step") == "verify_account":
        return
    st.update(step="verify_account", busy=True)
    client = st["client"]
    try:
        frozen = await account_is_frozen(client)
    except Exception:
        log.exception("Frozen-account check failed for seller %s", uid)
        await reject_login(uid, st, "freeze_check_failed")
        return
    if frozen:
        await reject_login(uid, st, "account_frozen")
        return
    if STATE.get(uid) is not st:
        return
    try:
        me = await client.get_me()
        if me is None:
            raise RuntimeError("get_me() returned None")
    except errors.UserDeactivatedBanError:
        await set_ui(uid, tr("account_blocked"), buttons=back_kb())
        await reset_state(uid)
        return
    except errors.AuthKeyUnregisteredError:
        await set_ui(uid, tr("no_session"),
                     buttons=back_kb())
        await reset_state(uid)
        return
    except Exception:
        log.exception("after_login failed for %s", st.get("phone"))
        await set_ui(uid, tr("finish_login_failed"), buttons=back_kb())
        await reset_state(uid)
        return

    try:
        if await asyncio.to_thread(sale_credit.has_credited_account, DB_PATH, me.id):
            if STATE.get(uid) is st:
                await set_ui(uid, tr("sale_duplicate"), buttons=back_kb())
                await reset_state(uid)
            return
        if STATE.get(uid) is not st:
            return
        if not await verify_spambot(uid, st):
            return
        if not await verify_channel_creation(uid, st):
            return
        session_string = client.session.save()
        async with DB_LOCK:
            account_id = await asyncio.to_thread(
                sale_credit.save_account_with_offer, DB_PATH, uid, st["phone"], session_string,
                st.get("twofa"), me.id, me.username, st["sale_quote"], schedule_cleanup=True)
    except sale_credit.DuplicateAccountError:
        if STATE.get(uid) is st:
            await set_ui(uid, tr("sale_duplicate"), buttons=back_kb())
            await reset_state(uid)
        return
    except Exception:
        log.exception("Could not save pending account and sale offer for seller %s", uid)
        if STATE.get(uid) is st:
            await set_ui(uid, tr("sale_pending_error"), buttons=back_kb())
            await reset_state(uid)
        return
    if STATE.get(uid) is not st:
        await asyncio.to_thread(pending_session_store.cancel, DB_PATH, account_id)
        return
    st.update(account_id=account_id, tg_user_id=me.id, cleanup_scheduled=True,
              step=STEP_LOGOUT, code="", busy=False)
    st["logout_lock"] = asyncio.Lock()
    st["logout_task"] = asyncio.create_task(auto_check_logout(uid, st))

    try:
        others = await other_authorizations(client)
    except Exception:
        log.exception("GetAuthorizations failed for %s", st.get("phone"))
        await set_ui(uid, tr("device_check_failed") + "\n\n" + tr("pending_cleanup_notice"), buttons=logout_kb())
        return

    head = tr("login_head", phone=st["phone"], user=(("@" + me.username) if me.username else "—"))
    head += "\n"

    if not others:
        await complete_sale(uid, head)
        return

    await set_ui(
        uid,
        head + sessions_report(others) + tr("logout_instructions") + "\n\n" + tr("pending_cleanup_notice"),
        buttons=logout_kb(),
    )


async def auto_check_logout(uid, st):
    
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        for attempt in range(1, LOGOUT_CHECK_ATTEMPTS + 1):
            await asyncio.sleep(max(0, started + attempt * LOGOUT_CHECK_INTERVAL - loop.time()))
            if STATE.get(uid) is not st or st.get("step") != STEP_LOGOUT:
                return
            await check_logout(uid)
        if STATE.get(uid) is st and st.get("step") == STEP_LOGOUT:
            notice = "\n\n" + tr("pending_cleanup_notice") if st.get('cleanup_scheduled') else ""
            await set_ui(uid, tr("auto_expired") + notice,
                         buttons=logout_kb())
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("automatic logout check failed for seller %s", uid)


async def check_logout(uid, event=None):
    st = STATE.get(uid)
    if not st:
        if event is not None:
            await ack(event, tr("step_inactive"), True)
        return
    async with st.setdefault("logout_lock", asyncio.Lock()):
        if STATE.get(uid) is st:
            await _check_logout(uid, event, st)


async def _check_logout(uid, event, st):
    async def answer(text="", alert=False):
        if event is not None:
            await ack(event, text, alert)

    if st.get("step") != STEP_LOGOUT or st.get("client") is None:
        await answer(tr("step_inactive"), True)
        return
    if st.get("busy"):
        await answer()
        return

    if asyncio.get_running_loop().time() < st.get("logout_retry_after", 0):
        await answer(tr("wait_limit"), True)
        return
    st["busy"] = True
    try:
        others = await other_authorizations(st["client"])
    except errors.AuthKeyUnregisteredError:
        if STATE.get(uid) is st:
            await set_ui(uid, tr("session_revoked"), buttons=back_kb())
            await reset_state(uid)
        await answer()
        return
    except errors.FloodWaitError as exc:
        log.warning("logout check flood wait for seller %s: %ss", uid, exc.seconds)
        st["logout_retry_after"] = asyncio.get_running_loop().time() + exc.seconds
        await answer(tr("wait_limit"), True)
        return
    except Exception:
        log.exception("re-check failed for %s", st.get("phone"))
        await answer(tr("retry_check"), True)
        return
    finally:
        st["busy"] = False

    if STATE.get(uid) is not st:
        return
    if others:
        if event is None:
            return
        await set_ui(
            uid,
            tr("remaining_report",
                n=len(others), r=sessions_report(others)
            ),
            buttons=logout_kb(),
        )
        await answer(tr("sessions_remaining", n=len(others)), True)
        return

    await complete_sale(uid)
    await answer()


_SALE_NOTIFY_LOCK = asyncio.Lock()


async def process_pending_session_job(job):
    
    result = 'skipped'
    borrowed = None
    account_id = job['account_id']
    async with _SALE_NOTIFY_LOCK:
        async with pending_session_lock(job['tg_user_id']):
            current = await asyncio.to_thread(pending_session_store.eligible_job, DB_PATH, account_id)
            if current is None:
                return result
            active = [(uid, st) for uid, st in STATE.items()
                      if st.get('client') is not None and st.get('tg_user_id') == job['tg_user_id']]
            if active and (len(active) != 1 or active[0][1].get('account_id') != account_id
                           or active[0][1].get('busy') or active[0][1].get('resetting')):
                await asyncio.to_thread(pending_session_store.reschedule, DB_PATH, account_id,
                                        int(time.time()) + 300, 'AccountBusy')
                return 'deferred'
            owned = not active
            if active:
                borrowed = active[0]
                client = borrowed[1]['client']
            else:
                try:
                    client = TelegramClient(StringSession(secure_store.decrypt(current['session_string'])), API_ID, API_HASH,
                        device_model=DEVICE_MODEL, system_version=SYSTEM_VERSION, app_version=APP_VERSION,
                        lang_code='en', system_lang_code='en-US', flood_sleep_threshold=0, request_retries=0)
                except Exception as exc:
                    await asyncio.to_thread(pending_session_store.finish, DB_PATH, account_id,
                                            status='failed', last_error=type(exc).__name__)
                    return 'failed'
            old_threshold = client.flood_sleep_threshold
            client.flood_sleep_threshold = 0
            try:
                if not client.is_connected():
                    await asyncio.wait_for(client.connect(), timeout=20)

                async def credit(account, seller):
                    async with DB_LOCK:
                        if await asyncio.to_thread(pending_session_store.eligible_job, DB_PATH, account) is None:
                            return 'cancelled', None
                        return await asyncio.to_thread(sale_credit.credit_sale, DB_PATH, account, seller,
                                                       require_cleanup_job=True)

                result = await asyncio.wait_for(pending_session_worker.process_job(
                    DB_PATH, account_id, client, credit), timeout=120)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                name = type(exc).__name__
                if name in ('AuthKeyDuplicatedError', 'AuthKeyUnregisteredError',
                            'SessionRevokedError', 'SessionExpiredError',
                            'UserDeactivatedError', 'UserDeactivatedBanError'):
                    await asyncio.to_thread(pending_session_store.finish, DB_PATH, account_id,
                                            status='failed', last_error=name)
                    result = 'failed'
                else:
                    await asyncio.to_thread(pending_session_store.reschedule, DB_PATH, account_id,
                                            int(time.time()) + 1800, name)
                    result = 'deferred'
                log.warning('Pending-session job %s: %s', account_id, name)
            finally:
                client.flood_sleep_threshold = old_threshold
                if owned:
                    try:
                        await client.disconnect()
                    except Exception:
                        log.warning('Could not disconnect pending-session client for job %s', account_id)
    if borrowed is not None and result in ('done', 'failed'):
        uid, st = borrowed
        if STATE.get(uid) is st:
            await reset_state(uid)
    return result


async def pending_session_loop():
    log.info('Persistent pending-session cleanup worker started (new sales, 24-hour minimum)')
    while True:
        try:
            jobs = await asyncio.to_thread(pending_session_store.due_jobs, DB_PATH)
            for job in jobs:
                await process_pending_session_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('Pending-session worker failed (%s)', type(exc).__name__)
        await asyncio.sleep(60)


async def sale_notification_loop():
    
    while True:
        try:
            async with _SALE_NOTIFY_LOCK:
                pending = await asyncio.to_thread(sale_credit.pending_notifications, DB_PATH)
                for credit in pending:
                    try:
                        profile = await asyncio.to_thread(user_store.get_user, DB_PATH, credit['seller_id'])
                        token = i18n.LANGUAGE.set((profile or {}).get('language') or 'fa')
                        try:
                            text = (success_text(escape(credit['phone']), credit['account_id']) + '\n\n' +
                                    tr('sale_credited', amount=display_usd(credit['usd_micros'])))
                            await bot.send_message(credit['seller_id'], text, parse_mode='html', link_preview=False)
                        finally:
                            i18n.LANGUAGE.reset(token)
                        await asyncio.to_thread(sale_credit.mark_notified, DB_PATH, credit['account_id'])
                    except Exception as exc:
                        log.warning('Sale notification failed for sale %s: %s', credit['account_id'], type(exc).__name__)
        except Exception:
            log.exception('Sale notification outbox failed')
        await asyncio.sleep(30)


async def complete_sale(uid, head=""):
    st = STATE.get(uid) or {}
    account_id = st.get("account_id")
    phone = st.get("phone", "-")
    if not account_id:
        await set_ui(uid, tr("sale_pending_error"), buttons=back_kb())
        return
    async with _SALE_NOTIFY_LOCK:
        try:
            async with DB_LOCK:
                status, credit = await asyncio.to_thread(sale_credit.credit_sale, DB_PATH, account_id, uid)
        except Exception:
            log.exception("Could not credit sale #%s for seller %s", account_id, uid)
            if STATE.get(uid) is st:
                await set_ui(uid, tr("sale_pending_error"), buttons=logout_kb())
            return
        if STATE.get(uid) is not st:
                                                                                          
            return
        if status == "duplicate_account":
            await set_ui(uid, tr("sale_duplicate"), buttons=back_kb())
            await reset_state(uid)
            return
        if status not in ("credited", "already_credited") or not credit:
            await set_ui(uid, tr("sale_pending_error"), buttons=logout_kb())
            return
        if st.get('cleanup_scheduled'):
            await asyncio.to_thread(pending_session_store.finish, DB_PATH, account_id)
        log.info("SOLD AND CREDITED #%s seller=%s USD=%s", account_id, uid, display_usd(credit["usd_micros"]))
        await set_ui(uid, head + success_text(phone, account_id) + "\n\n" +
                     tr("sale_credited", amount=display_usd(credit["usd_micros"])))
        await asyncio.to_thread(sale_credit.mark_notified, DB_PATH, account_id)
        await reset_state(uid)


                                                                               
          
                                                                               

async def refresh_event_profile(event, sender=None):
    
    if sender is None:
        sender = getattr(event, 'sender', None)
    if sender is None:
        return
    username = None
    if hasattr(sender, 'username') and not getattr(sender, 'min', False):
                                                                            
        username = getattr(sender, 'username', None) or ''
    has_name = hasattr(sender, 'first_name') or hasattr(sender, 'last_name')
    full_name = ' '.join(x for x in (getattr(sender, 'first_name', None),
                                      getattr(sender, 'last_name', None)) if x) if has_name else None
    try:
        await asyncio.to_thread(user_store.ensure_user, DB_PATH, event.sender_id,
                                username=username, full_name=full_name)
    except Exception:
        log.exception('Failed to update seller profile for user %s', event.sender_id)


def _support_create_ticket(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
        return support_store.create_ticket(conn, user_id)


def _support_get_ticket(ticket_id, user_id=None):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        return support_store.get_ticket(conn, ticket_id, user_id)


def _support_add_message(ticket_id, sender_id, role, text, message_id, media_kind):
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
        return support_store.add_message(conn, ticket_id, sender_id, role, text, message_id, media_kind)


def support_reply_kb(ticket_id, user=False):
    if user:
        return [[btn(tr('support_reply_btn'), f"support:user_reply:{ticket_id}".encode(), "📨")]]
    return [[btn(f"پاسخ به تیکت #{ticket_id}", f"support:admin_reply:{ticket_id}".encode(), "📨")]]


async def relay_support_content(target, source):
    
    text = source.message or ''
    entities = source.entities or []
    if source.media:
        return await bot.send_file(target, source.media, caption=text,
                                   formatting_entities=entities, parse_mode=None)
    return await bot.send_message(target, text, formatting_entities=entities,
                                  parse_mode=None, link_preview=False)


async def support_handle_input(event, pending):
    uid = event.sender_id
    ticket_id = pending.get('ticket_id')
    role = pending['role']
    if role == 'user' and ticket_id is None:
        ticket_id = await asyncio.to_thread(_support_create_ticket, uid)
        pending['ticket_id'] = ticket_id
    ticket = await asyncio.to_thread(_support_get_ticket, ticket_id,
                                     uid if role == 'user' else None)
    if not ticket or ticket['status'] != 'open':
        SUPPORT_STATE.pop(uid, None)
        await notify_send(uid, "این تیکت در دسترس نیست یا بسته شده است.")
        return
    source = event.message
    text = source.message or ''
    if not text and not source.media:
        await notify_send(uid, "پیام خالی است؛ متن یا فایل بفرست.")
        return
    media_kind = type(source.media).__name__ if source.media else None
    await asyncio.to_thread(_support_add_message, ticket_id, uid, role, text,
                            getattr(source, 'id', None), media_kind)
    SUPPORT_STATE.pop(uid, None)

    if role == 'user':
        profile = await asyncio.to_thread(user_store.get_user, DB_PATH, uid) or {}
        name = escape(profile.get('full_name') or 'کاربر')
        username = ('@' + escape(profile['username'])) if profile.get('username') else '—'
        header = (f"🎫 <b>تیکت پشتیبانی #{ticket_id}</b>\n"
                  f"👤 {name} · {username}\n🆔 <code>{uid}</code>")
        delivered = False
        for admin_id in sorted(ADMIN_IDS):
            try:
                await notify_send(admin_id, header,
                                  buttons=support_reply_kb(ticket_id))
                await relay_support_content(admin_id, source)
                delivered = True
            except Exception as exc:
                log.warning("Support ticket delivery failed ticket=%s admin=%s: %s",
                            ticket_id, admin_id, type(exc).__name__)
        language_token = i18n.LANGUAGE.set((profile or {}).get('language') or 'fa')
        try:
            if delivered:
                await notify_send(uid, tr('support_received'))
            else:
                await notify_send(uid, tr('generic_error'))
        finally:
            i18n.LANGUAGE.reset(language_token)
    else:
        profile = await asyncio.to_thread(user_store.get_user, DB_PATH, ticket['user_id']) or {}
        language_token = i18n.LANGUAGE.set(profile.get('language') or 'fa')
        try:
            try:
                await notify_send(ticket['user_id'], tr('support_reply_header', id=ticket_id),
                                  buttons=support_reply_kb(ticket_id, user=True))
                await relay_support_content(ticket['user_id'], source)
            except Exception as exc:
                log.warning("Support reply delivery failed ticket=%s user=%s: %s",
                            ticket_id, ticket['user_id'], type(exc).__name__)
        finally:
            i18n.LANGUAGE.reset(language_token)
        await notify_send(uid, f"✅ پاسخ تیکت #{ticket_id} ارسال شد.")


async def support_prompt(uid, ticket_id, role):
    SUPPORT_STATE[uid] = {'ticket_id': ticket_id, 'role': role}
    prompt = tr('support_prompt') if role == 'user' else f"✍️ پاسخ خود را برای تیکت #{ticket_id} بفرست. متن یا فایل مجاز است. /cancel برای لغو."
    await notify_send(uid, prompt)


def panel_menu_buttons():
    return [
        [btn("🔍 جستجوی کاربر", b"panel:search", "🔍"), btn("🚫 مسدودسازی", b"panel:ban", "⛔️")],
        [btn("✅ رفع مسدودی", b"panel:unban", "✅"), btn("📨 پیام به کاربر", b"panel:message", "📨")],
        [btn("📢 ارسال همگانی", b"panel:broadcast", "📣"), btn("📊 آمار", b"panel:stats", "📊")],
        [btn("👥 لیست کاربران", b"panel:users", "👥")],
    ]


async def panel_menu(uid, edit=False):
    text = "🛠 <b>پنل مدیریت</b>\nیک عملیات را انتخاب کن:"
    if edit:
        await set_ui(uid, text, buttons=panel_menu_buttons())
    else:
        await ui_send(uid, text, buttons=panel_menu_buttons())


def panel_resolve_user(term):
    term = (term or '').strip()
    if term.startswith('@'):
        term = term[1:]
    if term.isascii() and term.isdigit():
        try:
            return user_store.get_user(DB_PATH, int(term))
        except (ValueError, OverflowError):
            return None
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''SELECT user_id,username,full_name,is_banned,numbers_sold,balance,withdrawn
                               FROM users WHERE username=? COLLATE NOCASE ORDER BY user_id LIMIT 2''', (term,)).fetchall()
        return dict(rows[0]) if len(rows) == 1 else None


def panel_format_search(rows, heading="نتیجه جستجو"):
    if not rows:
        return "🔎 کاربری پیدا نشد."
    out = [f"🔎 <b>{heading} ({min(len(rows), 12)})</b>"]
    for u in rows[:12]:
        status = "🚫 مسدود" if u.get('is_banned') else "✅ فعال"
        username = ('@' + escape(u['username'])) if u.get('username') else (
            "ندارد" if u.get('username') == '' else "هنوز دریافت نشده")
        name = escape(u.get('full_name') or '—')
        started = (datetime.fromtimestamp(u['first_started_at'], timezone.utc).strftime('%Y-%m-%d')
                   if u.get('first_started_at') else '—')
        out.append(f"\n👤 {name}\n🔗 نام کاربری: {username}\n🆔 <code>{u['user_id']}</code> · {status}\n"
                   f"🌐 زبان: {escape(u.get('language') or '—')} · 🕒 شروع: {started}\n"
                   f"📦 فروش: {u['numbers_sold']} · 💰 موجودی: {display_usd(u['balance'])} USD · "
                   f"💸 برداشت‌شده: {display_usd(u['withdrawn'])} USD")
    return "\n".join(out)


def panel_users_kb(page, total_pages):
    navigation = []
    if page > 0:
        navigation.append(btn("⬅️ قبلی", f"panel:users:{page - 1}".encode(), "🔙"))
    if page + 1 < total_pages:
        navigation.append(btn("بعدی ➡️", f"panel:users:{page + 1}".encode(), "➡️"))
    rows = [navigation] if navigation else []
    rows.append([btn("🔙 بازگشت به پنل", b"panel:home", "🔙")])
    return rows


async def panel_refresh_missing_profiles(users):
    
    slots = asyncio.Semaphore(3)

    async def refresh(user):
        if user.get('username') is not None:
            return
        async with slots:
            try:
                sender = await asyncio.wait_for(bot.get_entity(user['user_id']), timeout=3)
                if (getattr(sender, 'id', None) != user['user_id']
                        or getattr(sender, 'min', False) or not hasattr(sender, 'username')):
                    return
                username = sender.username or ''
                full_name = ' '.join(part for part in (
                    getattr(sender, 'first_name', None), getattr(sender, 'last_name', None)) if part)
                updated = await asyncio.to_thread(user_store.ensure_user, DB_PATH, user['user_id'],
                                                 username=username, full_name=full_name or None)
                user.update(username=updated['username'], full_name=updated['full_name'])
            except Exception as exc:
                                                                             
                                                                       
                log.debug('Could not backfill user-list profile %s (%s)',
                          user['user_id'], type(exc).__name__)

    await asyncio.gather(*(refresh(user) for user in users))


async def panel_show_users(uid, page=0):
    users, total, page, pages = await asyncio.to_thread(user_store.list_users, DB_PATH, page, 10)
    await panel_refresh_missing_profiles(users)
    heading = f"لیست کاربران · صفحه {page + 1}/{pages}"
    text = (panel_format_search(users, heading) if users else f"👥 <b>{heading}</b>\n\nهنوز کاربری ثبت نشده.")
    await set_ui(uid, text, buttons=panel_users_kb(page, pages))


async def panel_handle_input(event, action):
    uid = event.sender_id
    text = (event.raw_text or '').strip()
    if action == 'search':
        rows = await asyncio.to_thread(user_store.search_users, DB_PATH, text.removeprefix('@'))
        await notify_send(uid, panel_format_search(rows))
        PANEL_STATE.pop(uid, None)
    elif action in ('ban', 'unban', 'message_target'):
        target = await asyncio.to_thread(panel_resolve_user, text)
        if not target:
            await notify_send(uid, "❌ کاربر پیدا نشد یا نام کاربری دقیق و یکتا نیست. شناسه عددی یا نام کاربری دقیق را بفرست.")
            return
        if target['user_id'] in ADMIN_IDS and action in ('ban', 'unban'):
            await notify_send(uid, "❌ تغییر وضعیت ادمین مجاز نیست.")
            PANEL_STATE.pop(uid, None)
            return
        if action == 'ban':
            updated = await asyncio.to_thread(user_store.ban_user, DB_PATH, target['user_id'])
            PANEL_STATE.pop(uid, None)
            await notify_send(uid, f"🚫 کاربر <code>{target['user_id']}</code> مسدود شد.")
        elif action == 'unban':
            updated = await asyncio.to_thread(user_store.unban_user, DB_PATH, target['user_id'])
            PANEL_STATE.pop(uid, None)
            await notify_send(uid, f"✅ مسدودی کاربر <code>{target['user_id']}</code> برداشته شد.")
        else:
            PANEL_STATE[uid] = {'action': 'message_body', 'target': target['user_id']}
            await notify_send(uid, f"✉️ متن یا فایل پیام برای <code>{target['user_id']}</code> را بفرست.")
    elif action in ('broadcast', 'message_body'):
        targets = ([r[0] for r in await asyncio.to_thread(lambda: _panel_recipient_ids(action == 'broadcast'))]
                   if action == 'broadcast' else [PANEL_STATE[uid]['target']])
        PANEL_STATE.pop(uid, None)
        source = event.message
        text_body = source.message or ''
        entities = source.entities or []
        media = source.media
        sent = failed = 0
        for target in targets:
            try:
                if media:
                    await bot.send_file(target, media, caption=text_body,
                                        formatting_entities=entities, parse_mode=None)
                else:
                    await bot.send_message(target, text_body, formatting_entities=entities,
                                           parse_mode=None, link_preview=False)
                sent += 1
            except errors.FloodWaitError as exc:
                await asyncio.sleep(exc.seconds)
                try:
                    if media:
                        await bot.send_file(target, media, caption=text_body,
                                            formatting_entities=entities, parse_mode=None)
                    else:
                        await bot.send_message(target, text_body, formatting_entities=entities,
                                               parse_mode=None, link_preview=False)
                    sent += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
        await notify_send(uid, f"📬 تمام شد.\n✅ ارسال موفق: {sent}\n❌ ناموفق: {failed}")


def _panel_recipient_ids(exclude_banned=True):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        if exclude_banned:
            return conn.execute('SELECT user_id FROM users WHERE is_banned=0 ORDER BY user_id').fetchall()
        return conn.execute('SELECT user_id FROM users ORDER BY user_id').fetchall()


async def panel_show_stats(uid):
    def read():
        with closing(sqlite3.connect(DB_PATH)) as conn:
            return (conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM accounts WHERE session_string IS NOT NULL AND session_string != ''").fetchone()[0],
                    conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM accounts WHERE status='sold'").fetchone()[0],
                    conn.execute('SELECT COUNT(*) FROM users WHERE is_banned=1').fetchone()[0])
    users, stored_sessions, all_time_sessions, completed_sales, banned = await asyncio.to_thread(read)
    await notify_send(uid, f"📊 <b>آمار</b>\n\n👥 کاربران ثبت‌شده: <b>{users}</b>\n"
                           f"🔐 سشن‌های ذخیره‌شده: <b>{stored_sessions}</b>\n"
                           f"🗂 کل سشن‌های ثبت‌شده: <b>{all_time_sessions}</b>\n"
                           f"📈 فروش‌های تکمیل‌شده: <b>{completed_sales}</b>\n🚫 کاربران مسدود: <b>{banned}</b>")


async def user_is_blocked(uid):
    if uid in ADMIN_IDS:
        return False
    profile = await asyncio.to_thread(user_store.get_user, DB_PATH, uid)
    if profile and profile.get('is_banned'):
        await notify_send(uid, "🚫 دسترسی شما به این ربات مسدود شده است.")
        return True
    return False


async def sync_admin_command_menu(client, uid):
    
    if uid not in ADMIN_IDS:
        return
    from configure_commands import DESCRIPTIONS
    peer = await client.get_input_entity(uid)
    scope = tl_types.BotCommandScopePeer(peer=peer)
    names = ("start", "language", "cancel", "price", "panel")
    for language, descriptions in DESCRIPTIONS.items():
        commands = [tl_types.BotCommand(command=name, description=description)
                    for name, description in zip(names, descriptions)]
        if not await client(functions.bots.SetBotCommandsRequest(
                scope=scope, lang_code=language, commands=commands), flood_sleep_threshold=0):
            raise RuntimeError("Telegram did not confirm the admin command menu")
        actual = await client(functions.bots.GetBotCommandsRequest(
            scope=scope, lang_code=language), flood_sleep_threshold=0)
        if [(c.command, c.description) for c in actual] != [(c.command, c.description) for c in commands]:
            raise RuntimeError("Admin command menu read-back did not match")
    log.info("Admin command menus saved and verified for %s", uid)


def register(client: TelegramClient):
    global bot
    bot = client

    @client.on(events.NewMessage(pattern=r"^/panel(?:@\w+)?(?:\s|$)"))
    async def _panel(event):
        if not event.is_private or event.sender_id not in ADMIN_IDS:
            return
        await refresh_event_profile(event)
        PANEL_STATE.pop(event.sender_id, None)
        await panel_menu(event.sender_id)

    @client.on(events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s|$)"))
    async def _start(event):
        if not event.is_private:
            return
        uid = event.sender_id
        profile = await asyncio.to_thread(user_store.ensure_user, DB_PATH, uid, True)
        if uid not in ADMIN_IDS and profile.get('is_banned'):
            await notify_send(uid, "🚫 دسترسی شما به این ربات مسدود شده است.")
            return
        SUPPORT_STATE.pop(uid, None)
        sender = getattr(event, 'sender', None)
        if sender is None or getattr(sender, 'min', False):
            try:
                sender = await event.get_sender()
            except Exception:
                log.warning('Could not retrieve sender profile for user %s', uid)
        await refresh_event_profile(event, sender)
        i18n.LANGUAGE.set(profile.get("language") or "fa")
        await reset_state(uid, cancel_pending=False)
        PRICE_STATE.pop(uid, None)
        STATE[uid] = {"ui_msg": None}
        if not profile.get("language"):
            await show_language_picker(uid)
        else:
            await show_welcome(uid, sender)
        if uid in ADMIN_IDS:
            try:
                await sync_admin_command_menu(client, uid)
            except Exception:
                log.exception("Could not refresh admin command menus for %s", uid)

    @client.on(events.NewMessage(pattern=r"^/(cancel|reset)$"))
    async def _cancel(event):
        if not event.is_private:
            return
        uid = event.sender_id
        if uid in ADMIN_IDS and PANEL_STATE.pop(uid, None):
            await notify_send(uid, "🛑 عملیات پنل لغو شد.")
            return
        pending_support = SUPPORT_STATE.pop(uid, None)
        if pending_support:
            if pending_support['role'] == 'user':
                await user_language(uid)
                await notify_send(uid, tr('support_cancelled'))
            else:
                await notify_send(uid, f"ارسال پاسخ به تیکت #{pending_support['ticket_id']} لغو شد.")
            return
        if await user_is_blocked(uid):
            return
        await refresh_event_profile(event)
        await asyncio.to_thread(pending_session_store.cancel_seller, DB_PATH, uid)
        await reset_state(uid)
        PRICE_STATE.pop(uid, None)
        STATE[uid] = {"ui_msg": None}
        if not await require_language(uid):
            return
        await ui_send(uid, tr("cancelled"), buttons=main_kb())

    @client.on(events.NewMessage(pattern=r"^/language$"))
    async def _language(event):
        if not event.is_private:
            return
        uid = event.sender_id
        if await user_is_blocked(uid):
            return
        await refresh_event_profile(event)
        await user_language(uid)
        if STATE.get(uid, {}).get("step") or STATE.get(uid, {}).get("busy"):
            await bot.send_message(uid, tr("language_busy"), parse_mode=None)
            return
        PRICE_STATE.pop(uid, None)
        await show_language_picker(uid)

    @client.on(events.NewMessage(pattern=r"^/price$"))
    async def _price(event):
        if not event.is_private:
            return
        uid = event.sender_id
        if await user_is_blocked(uid):
            return
        await refresh_event_profile(event)
        if not await require_language(uid):
            return
        if STATE.get(uid, {}).get("step") in (STEP_WITHDRAW_AMOUNT, STEP_WITHDRAW_WALLET):
            await bot.send_message(uid, tr("withdraw_flow_busy"), parse_mode=None)
            return
        if uid not in ADMIN_IDS:
            await ui_send(uid, tr("admin_only"),
                          buttons=main_kb())
            return
        await show_price_panel(uid, None, 0)

    @client.on(events.CallbackQuery())
    async def _callback(event):
        if not event.is_private:
            return
        data = (event.data or b"").decode(errors="ignore")
        uid = event.sender_id
        await refresh_event_profile(event)
        if data.startswith("withdraw:paid:"):
            if uid not in ADMIN_IDS:
                await ack(event, "⛔️ فقط ادمین می‌تونه پرداخت رو تأیید کنه.", True)
                return
            request_id = data.removeprefix("withdraw:paid:")
            if not request_id.isascii() or not request_id.isdigit() or len(request_id) > 18:
                await ack(event, "درخواست نامعتبره.", True)
                return
            try:
                status, request = await asyncio.to_thread(withdrawal_store.mark_paid, DB_PATH, int(request_id), uid)
            except Exception:
                log.exception("Failed to mark withdrawal paid, request %s", request_id)
                await ack(event, "خطا در ثبت پرداخت. دوباره تلاش کن.", True)
                return
            if status != "paid":
                await ack(event, "درخواست پیدا نشد یا قابل پرداخت نیست.", True)
                return
            await ack(event, "✅ پرداخت ثبت شد.", True)
            try:
                await event.edit(buttons=None)
            except Exception as exc:
                log.warning("Unable to remove paid button for withdrawal %s: %s", request_id, type(exc).__name__)
            asyncio.create_task(notify_withdrawals_safely())
            return
        if data.startswith("panel:"):
            if uid not in ADMIN_IDS:
                await ack(event, "⛔️ فقط ادمین می‌تونه پنل رو استفاده کنه.", True)
                return
            action = data.partition(":")[2]
            if action == 'home':
                await ack(event)
                STATE.setdefault(uid, {})['ui_msg'] = event.message_id
                await panel_menu(uid, edit=True)
                return
            if action == 'users' or action.startswith('users:'):
                raw_page = action.split(':', 1)[1] if ':' in action else '0'
                if not raw_page.isascii() or not raw_page.isdigit() or len(raw_page) > 6:
                    await ack(event, "شماره صفحه نامعتبر است.", True)
                    return
                await ack(event)
                STATE.setdefault(uid, {})['ui_msg'] = event.message_id
                await panel_show_users(uid, int(raw_page))
                return
            actions = {'search': '🔎 عبارت جستجو (نام، نام کاربری یا شناسه) را بفرست.',
                       'ban': '🚫 شناسه یا نام کاربری دقیق کاربر را برای مسدودسازی بفرست.',
                       'unban': '✅ شناسه یا نام کاربری دقیق کاربر را برای رفع مسدودی بفرست.',
                       'message': '📨 شناسه یا نام کاربری دقیق کاربر را بفرست.',
                       'broadcast': '📢 پیام همگانی را بفرست؛ متن، عکس، ویدیو، فایل یا صوت همراه با کپشن پشتیبانی می‌شود.'}
            if action == 'stats':
                await ack(event)
                await panel_show_stats(uid)
                return
            if action not in actions:
                await ack(event, "گزینه نامعتبر است.", True)
                return
            PANEL_STATE[uid] = {'action': 'message_target' if action == 'message' else action}
            await ack(event)
            await notify_send(uid, actions[action])
            return
        if data.startswith("support:"):
            _, action, raw_id = (data.split(":", 2) + [''])[:3]
            if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 18:
                await ack(event, "تیکت نامعتبر است.", True)
                return
            ticket_id = int(raw_id)
            if action == 'admin_reply':
                if uid not in ADMIN_IDS:
                    await ack(event, "فقط ادمین می‌تواند به تیکت پاسخ بدهد.", True)
                    return
                ticket = await asyncio.to_thread(_support_get_ticket, ticket_id)
                if not ticket or ticket['status'] != 'open':
                    await ack(event, "تیکت پیدا نشد یا بسته شده است.", True)
                    return
                PANEL_STATE.pop(uid, None); PRICE_STATE.pop(uid, None)
                await ack(event)
                await support_prompt(uid, ticket_id, 'admin')
                return
            if action == 'user_reply':
                if await user_is_blocked(uid):
                    await ack(event, "دسترسی مسدود است.", True)
                    return
                ticket = await asyncio.to_thread(_support_get_ticket, ticket_id, uid)
                if not ticket or ticket['status'] != 'open':
                    await ack(event, "این تیکت برای شما در دسترس نیست یا بسته شده است.", True)
                    return
                await user_language(uid)
                await ack(event)
                await support_prompt(uid, ticket_id, 'user')
                return
            await ack(event, "گزینه پشتیبانی نامعتبر است.", True)
            return
        if await user_is_blocked(uid):
            await ack(event, "دسترسی مسدود است.", True)
            return
        language = await user_language(uid)
        if data.startswith("lang:"):
            selected = data.partition(":")[2]
            if selected not in i18n.LANGUAGES:
                await ack(event, tr("invalid_language"), True)
                return
            if STATE.get(uid, {}).get("step") or STATE.get(uid, {}).get("busy"):
                await ack(event, tr("language_busy"), True)
                return
            await asyncio.to_thread(user_store.set_language, DB_PATH, uid, selected)
            i18n.LANGUAGE.set(selected)
            PRICE_STATE.pop(uid, None)
            STATE[uid] = {"ui_msg": event.message_id}
            await ack(event)
            await show_welcome(uid, await event.get_sender())
            return
        if not language:
            await ack(event, tr("choose_language_first"), True)
            await show_language_picker(uid)
            return
        if data.startswith("region:"):
            if uid not in ADMIN_IDS: await ack(event,tr("admin_panel_only"),True); return
            ps=PRICE_STATE.get(uid)
            if not ps or ps.get("ui_msg") != event.message_id: await ack(event,"پنل منقضی شده؛ /price رو بزن.",True); return
            if data == "region:list":
                ps.pop("target", None)
                await ack(event); await show_region_panel(uid,event); return
            if data == "region:back": await ack(event); await show_price_panel(uid,event.message_id,ps.get("page",0),query=ps.get("query","")); return
            if data.startswith("region:page:"):
                part = data.rsplit(":", 1)[-1]
                if not part.isascii() or not part.isdigit():
                    await ack(event, "صفحه نامعتبره.", True); return
                ps["region_page"] = int(part)
                await ack(event); await show_region_panel(uid, event); return
            if data.startswith("region:toggle:"):
                iso=data.rsplit(":",1)[-1]
                if iso not in COUNTRIES: await ack(event,"کشور نامعتبر است.",True); return
                current=await disabled_regions(); await set_region_disabled(iso,iso not in current); await ack(event)
                if ps.get("target")==iso: await price_prompt(uid,iso)
                else: await show_region_panel(uid,event)
                return
        if data.startswith("price:"):
            if uid not in ADMIN_IDS:
                await ack(event, tr("admin_panel_only"), True)
                return
            await handle_price_callback(uid, event, data)
            return

                                                                                
                                                                         
        st = STATE.setdefault(uid, {})
        if not st.get("ui_msg"):
            st["ui_msg"] = event.message_id

        if data == "menu:info":
            await set_ui(uid, tr("info"), buttons=back_kb())
            await ack(event)
        elif data == "menu:countries":
            await show_country_list(uid); await ack(event)
        elif data == "menu:profile":
            await show_profile(uid)
            await ack(event)
        elif data == "menu:support":
            if st.get("step") or st.get("busy"):
                await ack(event, tr('support_busy'), True)
                return
            await ack(event)
            await support_prompt(uid, None, 'user')
        elif data == "menu:withdraw":
            if st.get("step") or st.get("busy"):
                await ack(event, tr("withdraw_flow_busy"), True)
                return
            PRICE_STATE.pop(uid, None)
            await ack(event)
            await show_withdrawal_page(uid)
        elif data == "withdraw:request":
            if st.get("step") or st.get("busy"):
                await ack(event, tr("withdraw_flow_busy"), True)
                return
            await ack(event)
            await start_withdrawal(uid)
        elif data == "home":
            await reset_state(uid, cancel_pending=False)
            STATE[uid] = {"ui_msg": event.message_id}
            await show_welcome(uid, await event.get_sender())
            await ack(event)
        elif data == "menu:sell":
            await start_sell(uid, event)
            await ack(event)
        elif data == "cancel":
            await asyncio.to_thread(pending_session_store.cancel_seller, DB_PATH, uid)
            await reset_state(uid)
            STATE[uid] = {"ui_msg": event.message_id}
            await show_welcome(uid, await event.get_sender())
            await ack(event)
        elif data.startswith("code:"):
            await handle_code_digit(uid, event, data.split(":", 1)[1])
        elif data == "check:done":
            await check_logout(uid, event)
        else:
            await ack(event)

    @client.on(events.NewMessage())
    async def _text(event):
        if not event.is_private:
            return
        uid = event.sender_id
        await refresh_event_profile(event)
        if (event.raw_text or "").startswith("/") and uid not in SUPPORT_STATE:
            return
        if await user_is_blocked(uid):
            return
        if uid in SUPPORT_STATE:
            if (event.raw_text or "").startswith("/"):
                return
            if SUPPORT_STATE[uid]['role'] == 'user':
                await user_language(uid)
            await support_handle_input(event, SUPPORT_STATE[uid])
            return
        if uid in ADMIN_IDS and uid in PANEL_STATE:
            action = PANEL_STATE[uid]['action']
            await panel_handle_input(event, action)
            return
        if not await require_language(uid):
            return
        if uid in ADMIN_IDS and (PRICE_STATE.get(uid, {}).get("target") or PRICE_STATE.get(uid, {}).get("searching")):
            await handle_price_input(uid, event)
            return
        st = STATE.get(uid)
        if not st:
            return
        step = st.get("step")

        if step == STEP_PHONE:
            await handle_phone(uid, event.raw_text or "")
        elif step == STEP_CODE:
                                                              
            digits = re.sub(r"\D", "", event.raw_text or "")
            if not digits:
                await set_ui(uid, code_text(st.get("phone", "-"), st.get("code", ""), st.get("sale_quote")), buttons=code_kb())
                return
            st["code"] = digits[:6]
            try:
                await event.delete()
            except Exception:
                pass
            if not st.get("busy"):
                st["busy"] = True
                try:
                    await set_ui(uid, tr("checking_code"))
                    await submit_code(uid)
                finally:
                    st["busy"] = False
        elif step == STEP_2FA:
            try:
                await event.delete()                                            
            except Exception:
                pass
            await handle_2fa(uid, event.raw_text or "")
        elif step == STEP_WITHDRAW_AMOUNT:
            await handle_withdraw_amount(uid, event.raw_text or "")
        elif step == STEP_WITHDRAW_WALLET:
            await handle_withdraw_wallet(uid, event.raw_text or "")


async def main():
    if not API_ID or not API_HASH or not BOT_TOKEN:
        raise SystemExit("set API_ID, API_HASH and BOT_TOKEN env vars")

    secure_store.require_key()
    init_db()
    premium_state_load()
    client = TelegramClient("seller_bot", API_ID, API_HASH, device_model=DEVICE_MODEL)
    register(client)
    await client.start(bot_token=BOT_TOKEN)
    me = await client.get_me()
    if PREMIUM_ENABLED:
        await load_premium_emoji(client)
        log.info("coloured buttons: %s | premium emoji ids: %d | telethon %s",
                 "ON" if _STYLE_OK else "OFF (Telethon too old)", len(PREMIUM_EMOJI),
                 getattr(__import__("telethon"), "__version__", "?"))
    else:
        log.info("premium emoji disabled by %s", EMOJI_STATE_FILE)
    log.info("bot @%s is up (db=%s)", me.username, DB_PATH)
    rate_task = asyncio.create_task(refresh_rates_forever(), name="hourly-usd-rate")
    withdrawal_task = asyncio.create_task(withdrawal_notification_loop(), name="withdrawal-outbox")
    sale_task = asyncio.create_task(sale_notification_loop(), name="sale-outbox")
    pending_task = asyncio.create_task(pending_session_loop(), name="pending-session-cleanup")
    bridge_server = await bridge.start_from_env(DB_PATH, API_ID, API_HASH, secure_store.decrypt)
    try:
        await client.run_until_disconnected()
    finally:
        bridge.shutdown(bridge_server)
        for task in (rate_task, withdrawal_task, sale_task, pending_task):
            task.cancel()
        await asyncio.gather(rate_task, withdrawal_task, sale_task, pending_task, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as exc:
        log.warning("stopped: %s", exc)
