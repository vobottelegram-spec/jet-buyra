"""Insert YOUR OWN test Telegram account into the stock so the bridge can be tested end to end
without waiting for the 24h seller hold. Never use it with accounts you don't own.

    python import_test_account.py            # prompts for phone + session string (hidden)

Create a session string for a spare test account once, locally:
    python - <<'PY'
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    with TelegramClient(StringSession(), API_ID, API_HASH) as c: print(c.session.save())
    PY
"""
import getpass, os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phonenumbers
import secure_store

db = os.getenv("DB_PATH", "accounts.db")
phone = input("Phone (+countrycode...): ").strip()
num = phonenumbers.parse(phone, None)
region = phonenumbers.region_code_for_number(num)
session = getpass.getpass("Session string (hidden): ").strip()
if not region or len(session) < 50:
    sys.exit("bad phone or session string")
with sqlite3.connect(db) as c:
    c.execute("INSERT INTO accounts(seller_id,phone,session_string,twofa,status,region,payout,created_at) "
              "VALUES(0,?,?,NULL,'sold',?,0,?)", (phone, secure_store.encrypt(session), region, int(time.time())))
print("imported", phone, "region", region)
