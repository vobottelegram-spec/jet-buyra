import aiosqlite
from contextlib import asynccontextmanager
class DB:
 def __init__(self,path): self.path=path
 @asynccontextmanager
 async def conn(self):
  d=await aiosqlite.connect(self.path,timeout=30); d.row_factory=aiosqlite.Row
  try:
   await d.execute('PRAGMA journal_mode=WAL'); await d.execute('PRAGMA foreign_keys=ON'); yield d; await d.commit()
  finally: await d.close()
 async def init(self):
  async with self.conn() as d:
   await d.executescript('''
   CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,language TEXT,balance INTEGER NOT NULL DEFAULT 0,kyc_status TEXT NOT NULL DEFAULT 'none',phone TEXT,phone_country TEXT,banned INTEGER NOT NULL DEFAULT 0,screen_message_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
   CREATE TABLE IF NOT EXISTS countries(iso TEXT PRIMARY KEY,name TEXT,dial_code TEXT,api_count INTEGER DEFAULT 0,api_price INTEGER DEFAULT 0,sell_price INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1,markup INTEGER DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,iso TEXT,phone TEXT,api_price INTEGER,sell_price INTEGER,status TEXT,service TEXT DEFAULT 'Telegram',code TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,paid_at TEXT,coupon_code TEXT,discount_amount INTEGER DEFAULT 0,logout_at TEXT,refund_amount INTEGER DEFAULT 0,code_requested_at TEXT,report_sent_at TEXT);
   CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,method TEXT,status TEXT DEFAULT 'pending',receipt_file_id TEXT,tx_hash TEXT,note TEXT,purpose TEXT DEFAULT 'topup',order_id INTEGER,reviewed_by INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_at TEXT);
   CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_id INTEGER,receiver_id INTEGER,amount INTEGER,status TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS coupons(code TEXT PRIMARY KEY,kind TEXT,value INTEGER,max_uses INTEGER DEFAULT 0,used INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY,role TEXT DEFAULT 'admin',permissions TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS kyc(user_id INTEGER PRIMARY KEY,phone TEXT,card_number TEXT,docs TEXT,status TEXT DEFAULT 'pending',reviewed_by INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_at TEXT);
   CREATE TABLE IF NOT EXISTS panel2_countries(iso TEXT PRIMARY KEY,name TEXT,stock INTEGER NOT NULL DEFAULT 0,sell_price INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,admin_id INTEGER,action TEXT,target_id INTEGER,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id); CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
   ''')
   defaults={'sales_enabled':'1','second_panel_enabled':'0','topup_enabled':'1','card_enabled':'1','gateway_enabled':'0','crypto_enabled':'1','transfer_enabled':'1','min_topup':'100','max_topup':'0','kyc_required_above':'500','accounting_group_id':'-1004413050883','report_channel_id':'-1003919286985','card_number':'','card_owner':'','ton_wallet':'','tron_wallet':'','crypto_wallets':'','gateway_url':'','gateway_name':'OkayPay','gateway_merchant':'','report_buy_url':'','force_join_channels':'-1003919286985\n-1002090945431','default_markup':'0','kyc_archive_channel_id':'','hourly_report_enabled':'1'}
   for k,v in defaults.items(): await d.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
   # Ensure the requested admin ID is listed in the management panel.
   await d.execute("INSERT OR IGNORE INTO admins(user_id,role,permissions) VALUES(858897695,'admin','all')")
   for k,v in [('accounting_group_id','-1004413050883'),('report_channel_id','-1003919286985')]: await d.execute("UPDATE settings SET value=? WHERE key=? AND (value IS NULL OR value='')",(v,k))
   # Seed required report and main channels on existing installations if not configured yet.
   await d.execute("UPDATE settings SET value='-1003919286985\n-1002090945431' WHERE key='force_join_channels' AND (value IS NULL OR value='')")
   # Migrate installations still storing the retired group ID.
   await d.execute("UPDATE settings SET value='-1004413050883' WHERE key='accounting_group_id' AND value='-5319849950'")
   for table,col,typ in [('users','screen_message_id','INTEGER'),('orders','paid_at','TEXT'),('orders','coupon_code','TEXT'),('orders','discount_amount','INTEGER DEFAULT 0'),('orders','logout_at','TEXT'),('orders','refund_amount','INTEGER DEFAULT 0'),('orders','code_requested_at','TEXT'),('orders','report_sent_at','TEXT'),('payments','gateway_unique_id','TEXT'),('payments','gateway_order_id','TEXT'),('payments','coin','TEXT'),('payments','coin_amount','TEXT'),('kyc','card_number','TEXT'),('orders','provider_id','TEXT'),('orders','provider',"TEXT DEFAULT 'tnumber'")]:
    try: await d.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
    except Exception: pass
 async def execute(self,sql,args=(),fetch=False):
  async with self.conn() as d:
   c=await d.execute(sql,args); return await c.fetchall() if fetch else c.lastrowid
 async def one(self,sql,args=()):
  r=await self.execute(sql,args,True); return dict(r[0]) if r else None
 async def all(self,sql,args=()): return await self.execute(sql,args,True)
 async def scalar(self,sql,args=(),default=None):
  r=await self.one(sql,args); return default if not r else next(iter(r.values()))
 async def setting(self,k,default=''): return await self.scalar('SELECT value FROM settings WHERE key=?',(k,),default)
 async def set_setting(self,k,v): await self.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
 async def ensure_user(self,u):
  old=await self.one('SELECT * FROM users WHERE id=?',(u.id,))
  if old:
   await self.execute('UPDATE users SET username=?,first_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(u.username,u.first_name,u.id)); return await self.one('SELECT * FROM users WHERE id=?',(u.id,))
  await self.execute('INSERT INTO users(id,username,first_name) VALUES(?,?,?)',(u.id,u.username,u.first_name)); return await self.one('SELECT * FROM users WHERE id=?',(u.id,))
 async def adjust_balance(self,uid,delta):
  async with self.conn() as d:
   c=await d.execute('UPDATE users SET balance=balance+?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND balance+?>=0',(delta,uid,delta)); return c.rowcount==1
 async def approve_topup_payment(self,payment_id,admin_id):
  # Mark the payment and credit the wallet in one SQLite transaction.
  async with self.conn() as d:
   c=await d.execute("UPDATE payments SET status='approved',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending' AND purpose='topup' RETURNING user_id,amount",(admin_id,payment_id))
   row=await c.fetchone()
   if not row:return None
   uid,amount=int(row['user_id']),int(row['amount'] or 0)
   cur=await d.execute('UPDATE users SET balance=balance+?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(amount,uid))
   if cur.rowcount!=1: raise RuntimeError(f'User {uid} not found while approving topup {payment_id}')
   return {'user_id':uid,'amount':amount}
 async def debit(self,uid,amount): return await self.adjust_balance(uid,-abs(amount))
 async def transfer(self,sender,receiver,amount):
  if sender==receiver or amount<=0:return False
  async with self.conn() as d:
   c=await d.execute('UPDATE users SET balance=balance-? WHERE id=? AND balance>=?',(amount,sender,amount))
   if c.rowcount!=1:return False
   await d.execute('INSERT OR IGNORE INTO users(id,language) VALUES(?,?)',(receiver,'fa')); await d.execute('UPDATE users SET balance=balance+? WHERE id=?',(amount,receiver)); await d.execute('INSERT INTO transfers(sender_id,receiver_id,amount,status) VALUES(?,?,?,?)',(sender,receiver,amount,'success')); return True
