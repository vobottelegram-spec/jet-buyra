import asyncio, html, logging, re, secrets, time, hashlib
from datetime import datetime
import phonenumbers
from phonenumbers import region_code_for_number
from phonenumbers.geocoder import description_for_number
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from jn_config import load_config
from jn_db import DB
from jn_tnumber import TNumber, TNumberError
from jn_biyora import Biyora, BiyoraError
from jn_okaypay import OkayPay, OkayPayError, fetch_rates, amount_in_coin
from jn_emoji import IDS, pe
from jn_i18n import t, LANGS
from jn_keyboards import *
from jn_keyboards import main as main_keyboard

logging.basicConfig(level=logging.INFO)
cfg=load_config(); db=DB(cfg.db_path); api=TNumber(cfg.tnumber_key,cfg.tnumber_base); bz=Biyora(cfg.biyora_url,cfg.biyora_key_id,cfg.biyora_secret,cfg.biyora_cafile); r=Router(); OWNERS={7048466991,858897695}

class S(StatesGroup):
 kyc_phone=State(); kyc_card=State(); kyc_video=State(); topup=State(); order_coupon=State(); transfer_amount=State(); transfer_receiver=State(); receipt=State(); txhash=State(); admin_user=State(); admin_balance=State(); admin_setting=State(); admin_channels=State(); admin_price=State(); admin_payment_edit=State(); user_search=State(); admin_add=State(); price_bulk=State(); account_setting=State(); payment_wait=State(); admin_coupon=State()

def is_owner(uid): return uid in OWNERS or uid in cfg.owner_ids
async def is_admin(uid): return is_owner(uid) or bool(await db.scalar('SELECT 1 FROM admins WHERE user_id=?',(uid,),0))
async def user(uid): return await db.one('SELECT * FROM users WHERE id=?',(uid,))
async def ensure(m): return await db.ensure_user(m.from_user)
async def language(uid): return await db.scalar('SELECT language FROM users WHERE id=?',(uid,),None)
async def screen_id(uid): return await db.scalar('SELECT screen_message_id FROM users WHERE id=?',(uid,),None)
async def set_screen(uid,mid): await db.execute('UPDATE users SET screen_message_id=? WHERE id=?',(mid,uid))
async def safe_send(bot, chat_id, text, markup=None, reply_to=None):
 # Invalid custom-emoji/entities must never block an invoice or admin action.
 try:
  return await bot.send_message(chat_id,text,parse_mode='HTML',reply_markup=markup,reply_to_message_id=reply_to)
 except Exception as e:
  if 'ENTITY_TEXT_INVALID' not in str(e) and "can't parse entities" not in str(e).lower():
   raise
  plain=html.unescape(re.sub(r'<[^>]+>','',text))
  return await bot.send_message(chat_id,plain,reply_markup=markup,reply_to_message_id=reply_to)
async def render(bot,uid,chat_id,text,markup=None):
 m=await safe_send(bot,chat_id,text,markup)
 await set_screen(uid,m.message_id)
 return m
async def render_msg(msg,uid,text,markup=None):
 # Edit the current bot screen to avoid flooding the chat with navigation messages.
 try:
  await msg.edit_text(text,parse_mode='HTML',reply_markup=markup)
  await set_screen(uid,msg.message_id)
  return msg
 except Exception as e:
  if 'message is not modified' in str(e).lower(): return msg
  if 'ENTITY_TEXT_INVALID' in str(e):
   plain=html.unescape(re.sub(r'<[^>]+>','',text))
   try:
    await msg.edit_text(plain,reply_markup=markup); await set_screen(uid,msg.message_id); return msg
   except Exception: pass
  return await render(msg.bot,uid,msg.chat.id,text,markup)
async def main_screen(bot,uid,chat_id):
 l=await language(uid) or 'fa'; m=await bot.send_message(chat_id,'<tg-emoji emoji-id="5962824021841026520">👋</tg-emoji> '+t(l,'welcome'),parse_mode='HTML',reply_markup=main_keyboard(l,await is_admin(uid))); await set_screen(uid,m.message_id); return m
def api_int(c,*keys):
 for k in keys:
  v=c.get(k)
  if v is not None and str(v).strip()!='':
   try: return int(float(v))
   except Exception: pass
 return 0

def normalize_country_rows(raw):
 data=raw.get('data',raw) if isinstance(raw,dict) else raw
 if isinstance(data,dict): data=data.get('countries') or data.get('items') or data.get('results') or []
 return data if isinstance(data,list) else []

async def sync_countries():
 raw=await api.countries(); data=normalize_country_rows(raw)
 for c in data:
  if not isinstance(c,dict): continue
  iso=str(c.get('country') or c.get('iso') or c.get('code') or '').upper().strip()
  if not iso: continue
  ap=api_int(c,'sellprice','sell_price','price','buy_price','cost')
  stock=api_int(c,'count','stock','available','available_count','quantity','qty','total')
  old=await db.one('SELECT * FROM countries WHERE iso=?',(iso,)); markup=int(old['markup']) if old else int(await db.setting('default_markup','0'))
  sell=int(old['sell_price']) if old and int(old['api_price'])==ap and int(old['sell_price'])>0 else ap+markup
  enabled=int(old['enabled']) if old else 1
  name=str(c.get('name') or c.get('country_name') or c.get('title') or iso)
  dial=str(c.get('dial_code') or c.get('dialcode') or c.get('prefix') or '')
  await db.execute('INSERT INTO countries(iso,name,dial_code,api_count,api_price,sell_price,enabled,markup) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(iso) DO UPDATE SET name=excluded.name,dial_code=excluded.dial_code,api_count=excluded.api_count,api_price=excluded.api_price,updated_at=CURRENT_TIMESTAMP',(iso,name,dial,stock,ap,sell,enabled,markup))
 return len(data)
_P2={'t':0.0}
async def sync_panel2(force=False):
 import time as _t
 if not bz.enabled: return 0
 if not force and _t.time()-_P2['t']<30: return 0
 regions=await bz.stock(); _P2['t']=_t.time(); seen=[]
 for iso,n in (regions or {}).items():
  iso=str(iso).upper().strip()
  if not re.fullmatch(r'[A-Z]{2}',iso): continue
  try: n=max(0,int(n))
  except Exception: continue
  nm=await db.scalar('SELECT name FROM countries WHERE iso=?',(iso,),None) or iso
  await db.execute('INSERT INTO panel2_countries(iso,name,stock) VALUES(?,?,?) ON CONFLICT(iso) DO UPDATE SET stock=excluded.stock,updated_at=CURRENT_TIMESTAMP',(iso,nm,n)); seen.append(iso)
 if seen: await db.execute(f"UPDATE panel2_countries SET stock=0 WHERE iso NOT IN ({','.join('?'*len(seen))})",tuple(seen))
 else: await db.execute('UPDATE panel2_countries SET stock=0')
 return len(seen)
async def sync_loop(bot):
 while True:
  if bz.enabled:
   try: await sync_panel2(True)
   except Exception as e: logging.warning('panel2 sync failed: %s',e)
  try:
   if cfg.tnumber_key: await sync_countries()
  except Exception as e:
   logging.warning('5m sync failed: %s',e)
   try: await notify_admin_error(bot,'همگام‌سازی کشورها / API',e)
   except Exception: pass
  await asyncio.sleep(300)
async def missing_channels(bot,uid):
 raw=await db.setting('force_join_channels',''); chans=[x.strip() for x in raw.splitlines() if x.strip()]; missing=[]
 for c in chans:
  try:
   m=await bot.get_chat_member(c,uid)
   if m.status in ('left','kicked'): missing.append(c)
  except Exception: missing.append(c)
 return missing
async def join_kb(bot,chans,l):
 rows=[]
 for c in chans:
  url=c if c.startswith(('http://','https://')) else None
  label=c
  try:
   chat=await bot.get_chat(c)
   label=('@'+chat.username) if chat.username else (chat.title or c)
   if not url and chat.username: url=f'https://t.me/{chat.username}'
   if not url:
    try: url=await bot.export_chat_invite_link(chat.id)
    except Exception: url=None
  except Exception: pass
  if url: rows.append([ib(t(l,'join',c=label),url=url,style='primary',icon=IDS['support'])])
  else: rows.append([ib(label+' · لینک تنظیم نشده', 'joincheck','primary',IDS['support'])])
 rows.append([ib(t(l,'join_check'),'joincheck','success',IDS['add'])]); return InlineKeyboardMarkup(inline_keyboard=rows)
async def gate(q):
 miss=await missing_channels(q.bot,q.from_user.id)
 if not miss:return True
 l=await language(q.from_user.id) or 'fa'; await render_msg(q.message,q.from_user.id,t(l,'force')+'\n\n'+'\n'.join(miss),await join_kb(q.bot,miss,l)); await q.answer(); return False
async def kyc_ok(uid): return (await db.scalar('SELECT kyc_status FROM users WHERE id=?',(uid,),'none'))=='approved'
async def kyc_required(uid,amount): return amount>int(await db.setting('kyc_required_above','500')) and not await kyc_ok(uid)
async def phone_ok(uid): return bool(await db.scalar('SELECT phone FROM users WHERE id=?',(uid,),None))
async def notify_admin_error(bot, area, exc, details=''):
 alert_key='error_alert_'+hashlib.sha1((str(area)+'|'+str(exc)).encode()).hexdigest()[:16]
 now=int(time.time()); last=int(await db.setting(alert_key,'0') or 0)
 if now-last<300: return
 await db.set_setting(alert_key,str(now))
 msg=(f'⚠️ <b>خطای فنی جت نامبر</b>\n\nبخش: <b>{html.escape(str(area)[:100])}</b>\nخطا: <code>{html.escape(str(exc)[:700])}</code>\n{html.escape(str(details)[:500])}\n\nپیگیری فوری: @IRCryptoKing')
 targets=[]
 for key, default in [('accounting_group_id','-1004413050883'),('report_channel_id','-1003919286985')]:
  value=await db.setting(key,default)
  if value and value not in targets: targets.append(value)
 for target in targets:
  try:
   await bot.send_message(int(target) if str(target).lstrip('-').isdigit() else target,msg,parse_mode='HTML')
   return
  except Exception as send_exc: logging.error('admin error alert failed for %s: %s',target,send_exc)
 try: await bot.send_message(858897695,msg,parse_mode='HTML')
 except Exception: pass

async def crypto_wallet_lines():
 raw=await db.setting('crypto_wallets','')
 lines=[]
 for line in raw.splitlines():
  parts=[x.strip() for x in line.split('|',2)]
  if len(parts)==3 and all(parts): lines.append(f'<b>{html.escape(parts[1])} ({html.escape(parts[0])})</b>\n<code>{html.escape(parts[2])}</code>')
 if not lines:
  ton=await db.setting('ton_wallet',''); tron=await db.setting('tron_wallet','')
  if ton and ton!='-': lines.append(f'<b>TON</b>\n<code>{html.escape(ton)}</code>')
  if tron and tron!='-': lines.append(f'<b>TRON</b>\n<code>{html.escape(tron)}</code>')
 return ('<b>آدرس‌های پرداخت رمز ارزی</b>\n\n'+'\n\n'.join(lines)) if lines else '<b>آدرس کیف پول هنوز تنظیم نشده است.</b>\nاز مدیریت ← حسابداری آدرس‌ها را اضافه کن.'

def okaypay_client():
 return OkayPay(cfg.okaypay_id,cfg.okaypay_token)

async def make_okaypay_link(bot, uid, amount_toman, coin, purpose, order_id=None):
 pid=await create_payment(uid,amount_toman,'gateway_'+coin.lower(),purpose,order_id)
 try:
  rates=await fetch_rates()
  coin_amount=amount_in_coin(amount_toman,coin,rates)
  unique_id=f'JN{pid}{secrets.token_hex(5)}'
  response=await okaypay_client().create_link(coin_amount,coin,unique_id,cfg.okaypay_callback_url,cfg.okaypay_return_url)
  data=response.get('data',response)
  pay_url=data.get('pay_url') or data.get('url')
  provider_id=data.get('order_id')
  if not pay_url: raise OkayPayError('OkayPay لینک پرداخت برنگرداند')
  await db.execute('UPDATE payments SET gateway_unique_id=?,gateway_order_id=?,coin=?,coin_amount=? WHERE id=?',(unique_id,str(provider_id or ''),coin,coin_amount,pid))
  return pid,pay_url,coin_amount,rates
 except Exception as e:
  await db.execute("UPDATE payments SET status='failed' WHERE id=? AND status='pending'",(pid,))
  logging.exception('OkayPay link creation failed')
  await notify_admin_error(bot,'ساخت لینک پرداخت OkayPay / نرخ ارز',e,f'کاربر: {uid} · پرداخت: {pid} · ارز: {coin}')
  raise

async def settle_okaypay_payment(bot, p):
 claimed=await db.one("UPDATE payments SET status='processing' WHERE id=? AND status='pending' RETURNING *",(p['id'],))
 if not claimed: return False
 if claimed['purpose']=='topup':
  await db.adjust_balance(claimed['user_id'],int(claimed['amount'] or 0))
  await db.execute("UPDATE payments SET status='approved',reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='processing'",(claimed['id'],))
  try: await bot.send_message(claimed['user_id'],f'پرداخت OkayPay تأیید شد و {int(claimed["amount"] or 0):,} تومان به کیف پولت اضافه شد.')
  except Exception: pass
  return True
 ok,phone=await fulfill_order(claimed['user_id'],claimed['order_id'],bot)
 if not ok:
  await db.execute("UPDATE payments SET status='pending' WHERE id=? AND status='processing'",(claimed['id'],))
  await notify_admin_error(bot,'پرداخت OkayPay موفق است اما تحویل شماره شکست خورد','TNumber fulfillment failed',f'پرداخت: {claimed["id"]} · سفارش: {claimed["order_id"]}')
  return False
 await db.execute("UPDATE payments SET status='approved',reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='processing'",(claimed['id'],))
 await db.execute("UPDATE payments SET status='cancelled' WHERE order_id=? AND id<>? AND status='pending'",(claimed['order_id'],claimed['id']))
 o=await db.one('SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=?',(claimed['order_id'],))
 try: await bot.send_message(claimed['user_id'],delivery_text(int(claimed['order_id']),o,phone),parse_mode='HTML',reply_markup=order_ready_actions(int(claimed['order_id']),phone))
 except Exception as e: await notify_admin_error(bot,'ارسال شماره پس از پرداخت OkayPay',e,f'کاربر: {claimed["user_id"]} · سفارش: {claimed["order_id"]}')
 return True

async def okaypay_poll_loop(bot):
 while True:
  try:
   rows=await db.all("SELECT * FROM payments WHERE status='pending' AND method IN ('gateway_usdt','gateway_trx') AND gateway_unique_id IS NOT NULL ORDER BY id LIMIT 30")
   for p in rows:
    try:
     response=await okaypay_client().check_deposit(p['gateway_unique_id'])
     data=response.get('data',response)
     if str(data.get('status','0'))=='1': await settle_okaypay_payment(bot,p)
    except Exception as e:
     logging.warning('OkayPay status check failed for payment %s: %s',p['id'],e)
     await notify_admin_error(bot,'بررسی وضعیت پرداخت OkayPay',e,f'پرداخت: {p["id"]} · unique_id: {p.get("gateway_unique_id")}')
  except Exception as e:
   logging.exception('OkayPay polling loop failed')
   try: await notify_admin_error(bot,'چرخه بررسی OkayPay',e)
   except Exception: pass
  await asyncio.sleep(25)

async def methods(): return {'card':await db.setting('card_enabled','1')=='1','gateway':await db.setting('gateway_enabled','0')=='1','crypto':await db.setting('crypto_enabled','1')=='1'}
async def create_payment(uid,amount,method,purpose,order_id=None): return await db.execute('INSERT INTO payments(user_id,amount,method,purpose,order_id) VALUES(?,?,?,?,?)',(uid,amount,method,purpose,order_id))
async def send_accounting(bot,pid):
 gid=await db.setting('accounting_group_id','-1004413050883'); p=await db.one('SELECT p.*,u.username,u.first_name,k.card_number AS user_card_number FROM payments p LEFT JOIN users u ON u.id=p.user_id LEFT JOIN kyc k ON k.user_id=p.user_id WHERE p.id=?',(pid,))
 if not gid or not p:return False
 method={'card':'کارت‌به‌کارت','crypto':'ارز دیجیتال','gateway':'OkayPay','gateway_usdt':'OkayPay · USDT','gateway_trx':'OkayPay · TRX'}.get(p['method'],p['method'])
 purpose='خرید شماره مجازی' if p['purpose']=='order' else 'افزایش موجودی'
 text=(f'{pe("invoice","🧾")} <b>رسید پرداخت · #{pid}</b>\n━━━━━━━━━━━━━━━━━━\n'
       f'{pe("users","👤")} کاربر: <b>{html.escape(p["first_name"] or "بدون نام")}</b>\n'
       f'🆔 آیدی: <code>{p["user_id"]}</code>\n🔗 نام کاربری: @{html.escape(p["username"] or "ندارد")}\n'
       f'{pe("pay_amount","💰")} مبلغ: <b>{int(p["amount"] or 0):,} تومان</b>\n'
       f'💳 شماره کارت ثبت‌شده کاربر: <code>{html.escape(p.get("user_card_number") or "ثبت نشده")}</code>\n'
       f'{pe("online","💳")} روش: <b>{method}</b>\n🎯 بابت: <b>{purpose}</b>\n'
       f'🕒 زمان: <code>{html.escape(p.get("created_at") or "—")}</code>')
 if p.get('order_id'): text+=f'\n🧾 سفارش: <code>{p["order_id"]}</code>'
 if p.get('tx_hash'): text+=f'\n🔗 هش تراکنش: <code>{html.escape(p["tx_hash"])}</code>'
 kb=InlineKeyboardMarkup(inline_keyboard=[[ib('تأیید پرداخت',f'payok:{pid}','success',IDS['add']),ib('رد پرداخت',f'payno:{pid}','danger',IDS['cancel'])],[ib('اصلاح مبلغ',f'payedit:{pid}','primary',IDS['balance'])]])
 chat=int(gid) if str(gid).lstrip('-').isdigit() else gid
 try:
  if p.get('receipt_file_id'):
   try: await bot.send_photo(chat,p['receipt_file_id'],caption=text,parse_mode='HTML',reply_markup=kb)
   except Exception as caperr:
    if 'caption' not in str(caperr).lower() and 'entity' not in str(caperr).lower(): raise
    await bot.send_photo(chat,p['receipt_file_id'],caption=html.unescape(re.sub(r'<[^>]+>','',text)),reply_markup=kb)
  else: await safe_send(bot,chat,text,kb)
  return True
 except Exception as e:
  logging.exception('accounting send failed')
  # If the configured accounting group is unreachable, put the actionable receipt
  # in the configured report destination so admins still have a chance to review it.
  fallback=await db.setting('report_channel_id','-1003919286985')
  sent_fallback=False
  try:
   if fallback and str(fallback)!=str(gid):
    target=int(fallback) if str(fallback).lstrip('-').isdigit() else fallback
    if p.get('receipt_file_id'):
     try: await bot.send_photo(target,p['receipt_file_id'],caption=text,parse_mode='HTML',reply_markup=kb)
     except Exception as caperr:
      if 'caption' not in str(caperr).lower() and 'entity' not in str(caperr).lower(): raise
      await bot.send_photo(target,p['receipt_file_id'],caption=html.unescape(re.sub(r'<[^>]+>','',text)),reply_markup=kb)
    else: await safe_send(bot,target,text,kb)
    sent_fallback=True
  except Exception as fallback_exc:
   logging.error('receipt fallback delivery failed: %s',fallback_exc)
  await notify_admin_error(bot,'ارسال رسید به گروه حسابداری',e,f'شناسه پرداخت: {pid} · گروه اصلی: {gid} · ارسال جایگزین: {"موفق" if sent_fallback else "ناموفق"}')
  return sent_fallback
async def fulfill_order(uid,oid,bot=None):
 # Atomically claim the invoice so two callbacks cannot buy two numbers for one order.
 o=await db.one("UPDATE orders SET status='processing' WHERE id=? AND user_id=? AND status='invoice' RETURNING *",(oid,uid))
 if not o:return False,None
 try:
  if o.get('provider')=='biyora': d=await bz.reserve(o['iso'],f'jn-order-{oid}'); phone=d.get('phone')
  else: data=await api.buy(o['iso']); d=data.get('data',data); phone=d.get('phone') or d.get('phonenumber') or d.get('number')
  if not phone:
   await db.execute("UPDATE orders SET status='invoice' WHERE id=? AND status='processing'",(oid,)); return False,None
 except Exception as e:
  await db.execute("UPDATE orders SET status='invoice' WHERE id=? AND status='processing'",(oid,))
  logging.warning('buy failed: %s',e)
  try:
   if bot and not (isinstance(e,BiyoraError) and e.code=='out_of_stock'): await notify_admin_error(bot,'خرید شماره از BIYORA' if o.get('provider')=='biyora' else 'خرید شماره از TNumber API',e,f'کاربر: {uid} · سفارش: {oid}')
  except Exception: pass
  return False,None
 await db.execute("UPDATE orders SET phone=?,provider_id=?,status='success',paid_at=CURRENT_TIMESTAMP WHERE id=? AND status='processing'",(phone,str(d.get('id') or d.get('order_id') or d.get('activation_id') or oid),oid))
 if o.get('coupon_code'): await db.execute('UPDATE coupons SET used=used+1 WHERE code=?',(o['coupon_code'],))
 return True,phone
async def refund_dead_biyora_order(o):
 # Panel-2 reservation expired before any code was delivered: full refund, exactly once.
 amount=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
 row=await db.one("UPDATE orders SET status='cancelled',refund_amount=? WHERE id=? AND status='success' RETURNING id",(amount,o['id']))
 if row and amount: await db.adjust_balance(o['user_id'],amount)
 return bool(row),amount
async def report(bot,oid):
 ch=await db.setting('report_channel_id','-1003919286985')
 o=await db.one('SELECT o.*,u.first_name,u.username,c.name AS country_name FROM orders o LEFT JOIN users u ON u.id=o.user_id LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=?',(oid,))
 if not ch or not o or o.get('report_sent_at'):return
 def ce(eid,fallback): return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
 dt=str(o.get('logout_at') or o.get('paid_at') or o.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
 try:
  import jdatetime
  parsed=datetime.strptime(dt[:19],'%Y-%m-%d %H:%M:%S')
  dt=jdatetime.datetime.fromgregorian(datetime=parsed).strftime('%Y/%m/%d - %H:%M:%S')
 except Exception:
  dt=dt.replace('-', '/', 2)
 # Keep the requested report layout; provider ID is used when available, otherwise internal order ID.
 raw_provider_id=str(o.get('provider_id') or o.get('id') or '-')
 provider_id=html.escape(raw_provider_id[:4]+'****' if (raw_provider_id.isdigit() or o.get('provider')=='biyora') and len(raw_provider_id)>4 else raw_provider_id)
 country=html.escape(clean_country_name(o.get('country_name') or o.get('iso') or '-'))
 code=html.escape(str(o.get('code') or 'در انتظار دریافت'))
 price=max(0,int(o.get('sell_price') or 0)-int(o.get('discount_amount') or 0))
 iso=(o.get('iso') or '').upper(); panel='2' if int(o.get('panel_number') or 2)==2 else str(o.get('panel_number') or 1)
 raw_phone=str(o.get('phone') or '-')
 phone_digits=re.sub(r'\D','',raw_phone)
 phone=html.escape((raw_phone[:1] if raw_phone.startswith('+') else '')+phone_digits[:4]+'****' if len(phone_digits)>4 else raw_phone)
 text=(f'{ce("6003364252507709759","🛍️")} #خرید جدید کشور {country} {flag_for(iso)} عادی با موفقیت انجام شد [{provider_id}]\n\n'
       f'{ce("5472238215748397135","📦")}#پنل_شماره_{panel}\n\n'
       f'{ce("6005735473887058424","🆔")}ID : {provider_id}\n\n'
       f'{ce("6003541041951545754","📱")}Number : {phone}\n\n'
       f'{ce("4956640049132208666","🔐")}Code : {code}\n\n'
       f'{ce("5451732530048802485","🕒")} Time : {dt}\n\n'
       f'{ce("6001090565540681775","💰")} Price : {price:,}\n\n'
       f'{ce("5963248587948172136","🤖")}@jetnumber3bot')
 try:
  await bot.send_message(int(ch) if str(ch).lstrip('-').isdigit() else ch,text,parse_mode='HTML')
  await db.execute('UPDATE orders SET report_sent_at=CURRENT_TIMESTAMP WHERE id=? AND report_sent_at IS NULL',(oid,))
 except Exception as e:
  logging.warning('report failed: %s',e)
  try: await notify_admin_error(bot,'ارسال گزارش فروش',e,f'سفارش: {oid} · مقصد: {ch}')
  except Exception: pass


def clean_country_name(value):
 value=str(value or '').strip()
 value=re.sub(r'[🇦-🇿]{2}', '', value)
 value=re.sub(r'[🚫⛔❌]', '', value)
 return value.strip() or '-'

def invoice_text(oid,o,l):
 price=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
 country_name=html.escape(clean_country_name(o.get('name') or o.get('iso') or '-'))
 return (f'{pe("invoice_header","🧾")} <b>پیش فاکتور #{oid}</b>\n\n'
         f'{pe("invoice_field","📦")} محصول: شماره مجازی\n\n'
         f'{pe("invoice_field","🌍")} کشور: {country_name} {flag_for(o.get("iso") or "")}\n\n'
         f'{pe("invoice_field","💰")} قیمت: {int(o["sell_price"] or 0):,} تومان' + (f'\n🎟️ تخفیف: {int(o.get("discount_amount") or 0):,} تومان\n💳 مبلغ نهایی: <b>{price:,} تومان</b>' if int(o.get('discount_amount') or 0)>0 else '') +
         f'\n\n{pe("invoice_ready","💳")} فاکتور شما آماده پرداخت و تحویل هست')

def delivery_text(oid,o,phone):
 price=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
 return (f'{pe("delivery_success","✅")} <b>شماره مجازی شما با موفقیت ساخته شد</b>\n\n'
         f'{pe("delivery_country","🌎")} کشور: {html.escape(clean_country_name(o.get("name") or o.get("iso") or "-"))} {flag_for(o.get("iso") or "")}\n\n'
         f'{pe("delivery_price","💰")} قیمت: {price:,} تومان\n\n'
         f'{pe("delivery_phone","📱")} شماره مجازی: <code>{html.escape(phone)}</code>\n\n'
         f'{pe("delivery_instruction","📩")} لطفا شماره را در تلگرام وارد کنید و سپس روی دکمه دریافت کد کلیک کنید')
async def show_countries(q,l,panel=1):
 if panel==2:
  try: await sync_panel2()
  except Exception as e: logging.warning('panel2 sync: %s',e)
  rows=await db.all('SELECT iso,name,stock AS api_count,sell_price,CASE WHEN sell_price>0 THEN enabled ELSE 0 END AS enabled FROM panel2_countries ORDER BY name'); return await render_msg(q.message,q.from_user.id,t(l,'countries'),countries([dict(x) for x in rows],l,'country2'))
 try: await sync_countries()
 except Exception as e: logging.warning('sync: %s',e)
 rows=await db.all('SELECT * FROM countries ORDER BY name'); return await render_msg(q.message,q.from_user.id,t(l,'countries'),countries([dict(x) for x in rows],l))
async def show_account(msg,uid,l):
 u=await user(uid); st={'approved':t(l,'done'),'pending':t(l,'pending'),'rejected':t(l,'rejected')}.get(u['kyc_status'],t(l,'not_done')); phone=(u['phone'] or '-').replace('+','')
 text=f'{pe("account","👤")} <b>{t(l,"account_title")}</b>\n\n{pe("field","👤")} {t(l,"name",v=html.escape(u["first_name"] or "-"))}\n{pe("field","🆔")} {t(l,"uid",v=uid)}\n{pe("field","📱")} {t(l,"phone",v=phone)}\n{pe("kyc","🪪")} {t(l,"kyc_status",v=st)}'
 return await render_msg(msg,uid,text,account(l,u['kyc_status']=='approved',bool(u['phone'])))
KYC_TEXT='''برای فعال‌سازی خدمات، احراز هویت را از همین ربات و از بخش پروفایل انجام دهید.

شماره تلفن، شماره کارت و ویدیوی کوتاه مدارک لازم است. فقط مدارک متعلق به خودتان را ارسال کنید.'''
GUIDE=pe('guide','📚')+' <b>راهنمای خرید شماره مجازی جت نامبر</b>\n\n1 ابتدا در منوی اصلی ربات ،\nبا انتخاب گزینه "'+pe('add','➕')+' افزایش موجودی"\nموجودی حساب‌کاربری خود را در ربات شارژ نمایید.\n\n2 از منوی اصلی، گزینه "'+pe('buy','🛒')+' خرید شماره مجازی" را انتخاب کنید.\n\n3 سرور موردنظر را انتخاب کرده\nو سپس کشور دلخواه را از لیست انتخاب نمایید.\n\n4 شماره دریافتی را در سرویس انتخابی وارد کرده و روی دکمه دریافت کد کلیک کنید.\nتا زمان دریافت کد، هیچ مبلغی از حساب‌کاربری شما کسر نخواهد شد.\n\n5 کد دریافت شده را وارد کرده و وارد حساب جدید خود شوید!'
RULES='''قوانین استفاده از ربات :\n\n1 - مسئولیت سوء استفاده یا ایجاد مزاحمت از این شماره ها بر عهده خریدار می باشد.\n\n2 - ربات نظارتی روی شماره های مجازی ندارد و تنها واسط بین کاربر و پنل است.\n\n3 - تنها وظیفه ربات تحویل شماره برای سرویس مورد نظر و دریافت کد فعالسازی می باشد؛\nو ما هیچ مدیریتی بر روی شماره های مجازی نداریم و بررسی شماره ها توسط ما امکان پذیر نیست در واقع ما سازنده ی این شماره ها نیستیم!\n\n4 - هیچ گارانتی در قبال شماره هایی که برای تلگرام خریداری می شوند وجود ندارد.\n\n5 - بعد از دریافت کد و استفاده آن در سرویس مورد نظر، هر گونه محدودیت یا مشکلی از سمت سرویس مورد استفاده برای شماره ایجاد شود عواقب آن بر عهده شما است.\n\n6 - هر شماره برای یک سرویس است و از طرف ربات فقط یکبار برای آن سرویس کد فعال سازی ارسال می شود و در صورت عدم دریافت کد، هیچ هزینه ای از موجودی شما کسر نخواهد شد.\n\n7 - قیمت تمامی شماره ها بستگی به نرخ دلار دارد و ممکن است کاهش یا افزایش بیابد.\n\n8 - بازگشت وجه بعد از انجام تراکنش یا خرید به هیچ عنوان امکان پذیر نیست.\n\n9 - در صورت مشکل در پرداخت آنلاین و عدم شارژ حساب کاربری شما ، مبلغ پرداختی بین 24 تا نهایتا 48 ساعت به حساب شما برگشت می خورد و در غیر اینصورت به پشتیبانی در ارتباط باشید.\n\n10 - پرداخت هایی که از طریق کارت به کارت انجام می شوند پشتیبانی ربات این حق را دارد در صورت نیاز بعد از واریز وجه توسط کاربر، مشخصاتی را از کاربر پرداخت کننده جهت احراز هویت درخواست کند؛\nدر صورت عدم همکاری هیچ مبلغی به کاربر عودت داده نخواهد شد تا وضعیت این پول از طرف مراجع قضایی مشخص شود.\n\n⚠️ خرید شما از ربات به منزله پذیرفتن تمامی قوانین ربات می باشد.'''
USAGE='''شماره مجازی معمولاً برای ثبت‌نام و دریافت کد تأیید سرویس‌هایی مثل تلگرام و پیام‌رسان‌ها، استفاده ثانویه از حساب و حفظ جداسازی شماره شخصی از حساب موردنظر استفاده می‌شود.'''
ABOUT='''جت نامبر | JETNUMBER\n\nمرجع خرید و فروش شماره مجازی از کشورهای مختلف جهان.\nربات وظیفه دریافت شماره و کد فعال‌سازی سرویس انتخابی را انجام می‌دهد.'''
UNREPORT='''اگر شماره مجازی شما در تلگرام محدود شده است، ابتدا آموزش‌ها و قوانین را بررسی کنید. برای اعتراض به محدودیت‌های حساب می‌توانید از @spambot استفاده کنید.'''
CONTENT={'fa':{'kyc':KYC_TEXT,'guide':GUIDE,'rules':RULES,'usage':USAGE,'about':ABOUT,'unreport':UNREPORT,'support':'لطفاً ابتدا بخش سوالات متداول و قوانین را مطالعه کنید.\n\nبرای ارتباط مستقیم با مدیریت از دکمه زیر استفاده کنید.'},'en':{'kyc':'To activate virtual-number services, identity verification is required.\n\nOpen Profile in this bot and choose Identity Verification.\n\nSubmit your own documents through the guided steps.','guide':'📚 <b>JetNumber Purchase Guide</b>\n\n1. Top up your wallet.\n2. Choose Buy Account.\n3. Select the desired country.\n4. Enter the number and request the code.\n5. Use the received code to complete the account.','rules':'<b>Bot Usage Rules</b>\n\nThe buyer is responsible for misuse. The bot only delivers the number and activation code. Prices may change with exchange rates. Refunds are not available after a completed transaction. Card payments may require payer verification. Purchase means acceptance of the rules.','usage':'Virtual numbers can be used for service verification, secondary accounts and separating a personal phone number.','about':'<b>JetNumber</b>\n\nVirtual-number marketplace for multiple countries.','unreport':'If a number is restricted on Telegram, review the guides and contact @spambot.','support':'Please review the FAQ and rules first. Use the button below to contact management.'},'ar':{'kyc':'لتفعيل خدمات الأرقام الافتراضية، يلزم التحقق من الهوية.\n\nافتح الملف الشخصي في هذا الروبوت واختر التحقق من الهوية، ثم اتبع الخطوات.','guide':'📚 <b>دليل شراء JetNumber</b>\n\n1. اشحن محفظتك.\n2. اختر شراء حساب.\n3. اختر الدولة.\n4. أدخل الرقم واطلب الكود.\n5. استخدم الكود لإكمال الحساب.','rules':'<b>قوانين الاستخدام</b>\n\nالمشتري مسؤول عن سوء الاستخدام. الروبوت وسيط لتسليم الرقم والكود فقط. الأسعار قابلة للتغيير. لا يوجد استرداد بعد إتمام المعاملة. قد يُطلب التحقق من صاحب الدفع بالبطاقة. الشراء يعني قبول القوانين.','usage':'يمكن استخدام الرقم الافتراضي للتحقق من الخدمات والحسابات الثانوية وفصل الرقم الشخصي.','about':'<b>JetNumber</b>\n\nمنصة لشراء الأرقام الافتراضية من دول متعددة.','unreport':'إذا تم تقييد الرقم في Telegram، راجع التعليمات وتواصل مع @spambot.','support':'يرجى مراجعة الأسئلة الشائعة والقوانين أولاً.'},'ru':{'kyc':'Для активации услуг виртуальных номеров нужна верификация личности.\n\nОткройте профиль в этом боте, выберите верификацию и следуйте инструкциям.','guide':'📚 <b>Инструкция JetNumber</b>\n\n1. Пополните кошелёк.\n2. Выберите покупку аккаунта.\n3. Выберите страну.\n4. Введите номер и запросите код.\n5. Используйте код для завершения регистрации.','rules':'<b>Правила</b>\n\nПокупатель отвечает за использование номера. Бот только передаёт номер и код. Цены могут изменяться. После завершённой покупки возврат не предусмотрен. Платежи картой могут потребовать проверку плательщика. Покупка означает принятие правил.','usage':'Виртуальные номера используются для подтверждения сервисов и вторичных аккаунтов.','about':'<b>JetNumber</b>\n\nПлатформа виртуальных номеров разных стран.','unreport':'При ограничении номера в Telegram изучите инструкции и обратитесь к @spambot.','support':'Сначала изучите FAQ и правила.'},'zh':{'kyc':'要使用虚拟号码服务，需要完成身份验证。\n\n在本机器人中打开个人资料，选择身份验证并按照步骤操作。','guide':'📚 <b>JetNumber 购买教程</b>\n\n1. 充值钱包。\n2. 选择购买账号。\n3. 选择国家。\n4. 输入号码并获取验证码。\n5. 使用验证码完成注册。','rules':'<b>使用规则</b>\n\n买家负责号码的使用。机器人只负责提供号码和验证码。价格可能随汇率变化。交易完成后不退款。银行卡付款可能需要付款人验证。购买即表示接受规则。','usage':'虚拟号码可用于服务验证、备用账号以及与个人号码分离。','about':'<b>JetNumber</b>\n\n多国家虚拟号码交易平台。','unreport':'如果 Telegram 对号码进行了限制，请查看教程并联系 @spambot。','support':'请先查看常见问题和使用规则。'}}
def content(lang,key): return CONTENT.get(lang,CONTENT['fa']).get(key,CONTENT['fa'][key])


@r.message(CommandStart())
async def start(m,state):
 u=await ensure(m); await state.clear()
 if u['banned']: return await m.answer('⛔ حساب شما مسدود است.')
 l=u['language'] or 'fa'
 # /start must always produce a visible welcome message. Do not rely on editing an old screen.
 if not u['language']:
  await m.answer('<tg-emoji emoji-id="5962824021841026520">👋</tg-emoji> '+t(l,'welcome'),parse_mode='HTML')
  x=await m.answer(t('fa','choose'),parse_mode='HTML',reply_markup=langs()); await set_screen(u['id'],x.message_id); return
 if await missing_channels(m.bot,m.from_user.id):
  await m.answer('<tg-emoji emoji-id="5962824021841026520">👋</tg-emoji> '+t(l,'welcome'),parse_mode='HTML')
  miss=await missing_channels(m.bot,m.from_user.id); return await render(m.bot,u['id'],m.chat.id,t(l,'force')+'\n\n'+'\n'.join(miss),await join_kb(m.bot,miss,l))
 args=(m.text or '').split(maxsplit=1)
 if len(args)>1 and args[1].strip().lower().startswith('buy'):
  try: await sync_countries()
  except Exception as e: logging.warning('buy deep-link sync: %s',e)
  rows=await db.all('SELECT * FROM countries ORDER BY name')
  x=await m.answer(t(l,'countries'),reply_markup=countries([dict(x) for x in rows],l)); await set_screen(u['id'],x.message_id); return
 # Welcome + main keyboard in the same fresh message.
 x=await m.answer('<tg-emoji emoji-id="5962824021841026520">👋</tg-emoji> '+t(l,'welcome'),parse_mode='HTML',reply_markup=main_keyboard(l,await is_admin(u['id'])))
 await set_screen(u['id'],x.message_id)

@r.callback_query(F.data.startswith('lang:'))
async def pick_lang(q,state):
 l=q.data.split(':',1)[1]; await db.execute('UPDATE users SET language=? WHERE id=?',(l,q.from_user.id)); await state.clear(); await q.answer('✓')
 try: await q.message.delete()
 except: pass
 await main_screen(q.bot,q.from_user.id,q.message.chat.id)

@r.message(F.text.regexp(r'^/(?i:Vri)(?:@\w+)?(?:\s|$)'))
async def verify_command(m):
 if not await is_admin(m.from_user.id):
  return await m.answer('⛔ دسترسی ندارید.')
 parts=(m.text or '').split()
 if len(parts)!=2 or not parts[1].isdigit():
  return await m.answer('فرمت صحیح: <code>/Vri 123456789</code>',parse_mode='HTML')
 uid=int(parts[1])
 u=await user(uid)
 if not u:
  await db.execute("INSERT OR IGNORE INTO users(id,language,kyc_status) VALUES(?, 'fa','none')",(uid,))
 await set_kyc(uid,'approved',m.from_user.id,m.bot,notify=True)
 # Reply directly to the admin command message.
 return await m.answer(f'احراز هویت با موفقیت تایید شد {pe("kyc_admin","✅")}',parse_mode='HTML')

@r.message(Command('add'))
async def add_balance_command(m):
 if not await is_admin(m.from_user.id): return await m.answer('⛔ دسترسی ندارید.')
 p=(m.text or '').split()
 if len(p)!=3 or not p[1].isdigit() or not p[2].isdigit() or int(p[2])<=0:return await m.answer('فرمت صحیح: <code>/add ID AMOUNT</code>',parse_mode='HTML')
 uid,amount=int(p[1]),int(p[2]); await db.execute("INSERT OR IGNORE INTO users(id,language) VALUES(?,'fa')",(uid,)); await db.adjust_balance(uid,amount)
 try: await m.bot.send_message(uid,f'💰 مبلغ {amount:,} تومان توسط مدیریت به کیف پول شما اضافه شد.')
 except: pass
 return await m.answer(f'✅ {amount:,} تومان به موجودی <code>{uid}</code> اضافه شد.',parse_mode='HTML')

@r.message(Command('rem'))
async def remove_balance_command(m):
 if not await is_admin(m.from_user.id): return await m.answer('⛔ دسترسی ندارید.')
 p=(m.text or '').split()
 if len(p)!=3 or not p[1].isdigit() or not p[2].isdigit() or int(p[2])<=0:return await m.answer('فرمت صحیح: <code>/rem ID AMOUNT</code>',parse_mode='HTML')
 uid,amount=int(p[1]),int(p[2]); u=await user(uid)
 if not u:return await m.answer('کاربر در دیتابیس نیست.')
 ok=await db.adjust_balance(uid,-amount)
 if not ok:return await m.answer('❌ موجودی کاربر برای این برداشت کافی نیست.')
 try: await m.bot.send_message(uid,f'💰 مبلغ {amount:,} تومان توسط مدیریت از کیف پول شما کسر شد.')
 except: pass
 return await m.answer(f'✅ {amount:,} تومان از موجودی <code>{uid}</code> کم شد.',parse_mode='HTML')

@r.message(Command('p2price'))
async def p2_price_command(m):
 if not await is_admin(m.from_user.id): return await m.answer('⛔ دسترسی ندارید.')
 p=(m.text or '').split()
 if len(p)!=3 or not re.fullmatch(r'[A-Za-z]{2}',p[1]) or not p[2].isdigit(): return await m.answer('فرمت صحیح: <code>/p2price US 150000</code>',parse_mode='HTML')
 iso=p[1].upper()
 if not await db.scalar('SELECT COUNT(*) FROM panel2_countries WHERE iso=?',(iso,),0): return await m.answer('این کشور در پنل دوم نیست؛ ابتدا /p2sync بزن.')
 await db.execute('UPDATE panel2_countries SET sell_price=? WHERE iso=?',(int(p[2]),iso)); await db.execute('INSERT INTO audit(admin_id,action,target_id,details) VALUES(?,?,?,?)',(m.from_user.id,'p2price',0,f'{iso}={p[2]}'))
 return await m.answer(f'✅ قیمت پنل دوم برای {iso}: {int(p[2]):,} تومان',parse_mode='HTML')

@r.message(Command('p2toggle'))
async def p2_toggle_command(m):
 if not await is_admin(m.from_user.id): return await m.answer('⛔ دسترسی ندارید.')
 p=(m.text or '').split()
 if len(p)!=2 or not re.fullmatch(r'[A-Za-z]{2}',p[1]): return await m.answer('فرمت صحیح: <code>/p2toggle US</code>',parse_mode='HTML')
 iso=p[1].upper(); await db.execute('UPDATE panel2_countries SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE iso=?',(iso,)); x=await db.one('SELECT * FROM panel2_countries WHERE iso=?',(iso,))
 return await m.answer('پیدا نشد.' if not x else f'{iso}: {"فعال" if x["enabled"] else "خاموش"}')

@r.message(Command('p2sync'))
async def p2_sync_command(m):
 if not await is_admin(m.from_user.id): return await m.answer('⛔ دسترسی ندارید.')
 if not bz.enabled: return await m.answer('اتصال BIYORA تنظیم نشده است (BIYORA_URL / BIYORA_SECRET).')
 try: n=await sync_panel2(True)
 except Exception as e: return await m.answer(f'❌ همگام‌سازی ناموفق: <code>{html.escape(str(e))}</code>',parse_mode='HTML')
 rows=await db.all('SELECT * FROM panel2_countries ORDER BY iso')
 lines=[f'{x["iso"]} · موجودی {x["stock"]} · قیمت {int(x["sell_price"]):,} · {"فعال" if x["enabled"] else "خاموش"}'+(' ⚠️ قیمت صفر' if int(x["sell_price"])<=0 else '') for x in rows]
 return await m.answer(f'✅ {n} کشور همگام شد\n\n'+('\n'.join(lines) or '—')+'\n\nتعیین قیمت: <code>/p2price ISO مبلغ</code>',parse_mode='HTML')

@r.message(StateFilter(None),F.text)
async def menu_text(m,state):
 u=await ensure(m); l=u['language'] or 'fa'; txt=m.text.strip(); mapping={}
 for code in LANGS:
  for k in ('buy','buy2','wallet','account','guide','help','support','prices','kyc','session','lang','admin'): mapping[label(t(code,k))]=(k if k!='wallet' else 'wallet')
 action=mapping.get(txt)
 if not action:return
 if action=='admin':
  if not await is_admin(m.from_user.id): return await render(m.bot,u['id'],m.chat.id,'⛔ دسترسی ندارید.',back('home',l))
  return await render(m.bot,u['id'],m.chat.id,'<b>⚙️ پنل مدیریت جت نامبر</b>\n\nیک بخش را انتخاب کنید:',admin_menu())
 if action=='lang': return await render(m.bot,u['id'],m.chat.id,t(l,'lang'),langs())
 if action in ('buy','buy2'):
  if action=='buy2' and (await db.setting('second_panel_enabled','0')!='1' or not bz.enabled): return await render(m.bot,u['id'],m.chat.id,t(l,'panel_off'),back('home',l))
  if await db.setting('sales_enabled','1')!='1': return await render(m.bot,u['id'],m.chat.id,t(l,'sales_off'),back('home',l))
  return await show_countries(type('Q',(),{'message':m,'from_user':m.from_user})(),l,2 if action=='buy2' else 1)
 if action=='wallet': return await show_wallet(m,u['id'],l)
 if action=='account': return await show_account(m,u['id'],l)
 if action=='guide': return await render(m.bot,u['id'],m.chat.id,content(l,'guide'),back('home',l))
 if action=='help': return await render(m.bot,u['id'],m.chat.id,'<b>راهنما و سوالات متداول جت نامبر</b>',help_menu(l))
 if action=='support': return await render(m.bot,m.from_user.id,m.chat.id,'<b>پشتیبانی جت نامبر</b>\n\nسوالات متداول را بررسی کنید یا مستقیماً با مدیریت در ارتباط باشید.',InlineKeyboardMarkup(inline_keyboard=[[ib('ارتباط با مدیریت',None,url='https://t.me/shrwein',style='primary',icon=IDS['support'])],[ib('سوالات متداول','help:faq','primary',IDS['help'])],[ib('بازگشت','home','primary',IDS['lock'])]]))
 if action=='prices': return await show_countries(type('Q',(),{'message':m,'from_user':m.from_user})(),l)
 if action=='kyc': return await show_kyc(m,u['id'],l,state)
 if action=='session': return await show_session(m,u['id'],l)

async def show_wallet(msg,uid,l):
 bal=int(await db.scalar('SELECT balance FROM users WHERE id=?',(uid,),0)); text=f'{pe("wallet","💰")} <b>{t(l,"wallet_title")}</b>\n\n{t(l,"current",bal=bal)}'; return await render_msg(msg,uid,text,wallet(l))
async def show_session(msg,uid,l):
 text=f'{pe("session_title","📱")} <b>خرید سشن و T-Data</b>\n\nبرای سفارش به پشتیبانی پیام بدهید.'
 kb=InlineKeyboardMarkup(inline_keyboard=[[ib('ورود به پشتیبانی',None,url='https://t.me/shrwein',style='primary',icon=IDS['session_title'])],[ib(t(l,'back'),'home','primary',IDS['lock'])]])
 return await render_msg(msg,uid,text,kb)

async def show_kyc(msg,uid,l,state=None):
 u=await user(uid)
 if u and u.get('kyc_status')=='approved':
  return await render_msg(msg,uid,'<b>احراز هویت شما قبلاً تأیید شده است.</b>',back('menu:account',l))
 await db.execute("INSERT OR IGNORE INTO kyc(user_id,phone,status) VALUES(?,?,?)",(uid,await db.scalar('SELECT phone FROM users WHERE id=?',(uid,),None),'pending'))
 if state: await state.set_state(S.kyc_phone)
 await state_kyc_contact(msg,uid,l)

async def state_kyc_contact(msg,uid,l):
 # Request a Telegram contact so the phone is tied to the account, not just typed text.
 from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
 kb=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='ارسال شماره تلفن من',request_contact=True)], [KeyboardButton(text='لغو')]],resize_keyboard=True,one_time_keyboard=True)
 await msg.answer('برای شروع احراز هویت، شماره تلفن خود را با دکمه زیر ارسال کنید.',reply_markup=kb)

@r.message(F.text == 'لغو', StateFilter(S.kyc_phone, S.kyc_card, S.kyc_video))
async def kyc_cancel(m,state):
 await state.clear()
 return await m.answer('فرایند احراز هویت لغو شد. هر زمان خواستی از پروفایل دوباره شروع کن.',reply_markup=ReplyKeyboardRemove())

@r.message(S.kyc_card)
async def kyc_card_input(m,state):
 raw=re.sub(r'[^0-9۰-۹٠-٩]','',m.text or '')
 raw=raw.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
 if len(raw)!=16 or not luhn_card(raw):
  return await m.answer('شماره کارت باید ۱۶ رقم و از نظر رقم کنترلی معتبر باشد. لطفاً دوباره وارد کنید.')
 uid=m.from_user.id
 await db.execute("UPDATE kyc SET card_number=?,phone=?,status='pending',docs=NULL,created_at=CURRENT_TIMESTAMP,reviewed_by=NULL,reviewed_at=NULL WHERE user_id=?",(raw,await db.scalar('SELECT phone FROM users WHERE id=?',(uid,),None),uid))
 await state.set_state(S.kyc_video)
 text=('جهت ارسال مدارک احراز هویت:\n\n'
 '<tg-emoji emoji-id="5972265777296838427">🪪</tg-emoji> کارت بانکی + کارت ملی (در صورت نداشتن، شناسنامه) + روی کاغذ با خودکار بنویسید: «این احراز هویت برای ربات خدمات مجازی جت نامبر است»\n\n'
 'همه موارد را کنار هم قرار دهید تا واضح و خوانا باشند؛ سپس فیلم کوتاهی در حد چند ثانیه بگیرید و ارسال کنید.\n\n'
 '<tg-emoji emoji-id="5949503361161105842">📌</tg-emoji> موارد قابل توجه:\n<tg-emoji emoji-id="5416113713428057601">•</tg-emoji> همه موارد باید واضح باشند.\n<tg-emoji emoji-id="5416113713428057601">•</tg-emoji> فیلم طولانی نباشد.\n<tg-emoji emoji-id="5416113713428057601">•</tg-emoji> کارت بانکی، مدرک شناسایی و متن باید هم‌زمان در فیلم باشند.\n<tg-emoji emoji-id="5416113713428057601">•</tg-emoji> مدرک شناسایی باید متعلق به دارنده کارت باشد.\n\n'
 f'شماره کارت شما: <code>{raw}</code>\n\nلطفاً فیلم آماده‌شده را به‌صورت ویدیو ارسال کنید.')
 return await m.answer(text,parse_mode='HTML',reply_markup=ReplyKeyboardRemove())

def luhn_card(number):
 if not number.isdigit() or len(number)!=16:return False
 total=0
 for i,ch in enumerate(number[::-1]):
  n=int(ch)
  if i%2==1:
   n*=2
   if n>9:n-=9
  total+=n
 return total%10==0

@r.message(S.kyc_video)
async def kyc_video_input(m,state):
 if not m.video:
  return await m.answer('لطفاً فیلم کوتاه احراز هویت را به‌صورت ویدیو ارسال کنید؛ عکس یا فایل متنی پذیرفته نیست.')
 uid=m.from_user.id; u=await user(uid); card=await db.scalar('SELECT card_number FROM kyc WHERE user_id=?',(uid,),None)
 if not card:return await state.clear() or await m.answer('شماره کارت ثبت نشده؛ دوباره از پروفایل شروع کنید.')
 archive=await db.setting('kyc_archive_channel_id','')
 if not archive:
  return await m.answer('آرشیو خصوصی احراز هویت هنوز در تنظیمات مدیریت ثبت نشده است. مدارک ارسال نشدند؛ لطفاً بعداً دوباره تلاش کنید.')
 archive_chat=int(archive) if archive.lstrip('-').isdigit() else archive
 uname='@'+u['username'] if u and u.get('username') else 'ندارد'
 caption=(f'آرشیو مدارک احراز هویت\nکاربر: {html.escape(u.get("first_name") or "-")}\n'
          f'آیدی عددی: <code>{uid}</code>\nنام کاربری: {html.escape(uname)}\n'
          f'شماره تلفن: <code>{html.escape(u.get("phone") or "-")}</code>\nشماره کارت: <code>{card}</code>')
 try:
  saved=await m.bot.send_video(archive_chat,m.video.file_id,caption=caption,parse_mode='HTML')
  await db.execute("UPDATE kyc SET docs=?,status='pending',created_at=CURRENT_TIMESTAMP WHERE user_id=?",(saved.video.file_id,uid))
  admin=await db.setting('accounting_group_id','-1004413050883'); admin_chat=int(admin) if admin.lstrip('-').isdigit() else admin
  kb=InlineKeyboardMarkup(inline_keyboard=[[ib('تأیید احراز',f'kycvideo:ok:{uid}','success',IDS['verify']),ib('رد احراز',f'kycvideo:no:{uid}','danger',IDS['cancel'])]])
  await m.bot.send_video(admin_chat,m.video.file_id,caption=caption+'\n\nوضعیت: در انتظار بررسی',parse_mode='HTML',reply_markup=kb)
  await state.clear()
  return await m.answer('مدارک شما برای بررسی ارسال و در آرشیو خصوصی ثبت شد. نتیجه پس از بررسی اعلام می‌شود.',reply_markup=ReplyKeyboardRemove())
 except Exception as e:
  logging.exception('KYC document forwarding failed')
  try: await notify_admin_error(m.bot,'ارسال مدارک احراز هویت',e,f'کاربر: {uid}')
  except Exception: pass
  return await m.answer('ارسال مدارک با خطا مواجه شد. مدارک را دوباره ارسال کنید یا بعداً تلاش کنید.')

@r.callback_query(F.data.startswith('kycvideo:'))
async def kycvideo_review(q):
 if not await is_admin(q.from_user.id): return await q.answer('دسترسی ندارید.',show_alert=True)
 _,decision,uid_s=q.data.split(':'); uid=int(uid_s); status='approved' if decision=='ok' else 'rejected'
 changed=await set_kyc(uid,status,q.from_user.id,q.bot,notify=True)
 try: await q.message.edit_caption(caption=(q.message.caption or '')+f'\n\nنتیجه بررسی: {"تأیید شد" if status=="approved" else "رد شد"} توسط <code>{q.from_user.id}</code>',parse_mode='HTML',reply_markup=None)
 except Exception: pass
 await q.answer(('تأیید شد.' if status=='approved' else 'رد شد.') if changed else 'وضعیت قبلاً ثبت شده بود.')

@r.callback_query(F.data=='home')
async def home(q,state):
 await state.clear(); l=await language(q.from_user.id) or 'fa'; await q.answer(); await main_screen(q.bot,q.from_user.id,q.message.chat.id)
@r.callback_query(F.data=='joincheck')
async def joincheck(q):
 miss=await missing_channels(q.bot,q.from_user.id)
 if miss:return await q.answer(t(await language(q.from_user.id) or 'fa','join_pending'),show_alert=True)
 await q.answer(); l=await language(q.from_user.id) or 'fa'; await main_screen(q.bot,q.from_user.id,q.message.chat.id)
@r.callback_query(F.data.startswith('country:'))
async def country(q):
 l=await language(q.from_user.id) or 'fa'
 try:
  if not await gate(q): return
  iso=q.data.split(':',1)[1].upper().strip(); row=await db.one('SELECT * FROM countries WHERE iso=?',(iso,))
  if not row:return await q.answer('کشور پیدا نشد؛ لطفاً دوباره همگام‌سازی کنید.',show_alert=True)
  if int(row.get('enabled') or 0)!=1 or int(row.get('api_count') or 0)<=0:return await q.answer(t(l,'no_stock'),show_alert=True)
  oid=await db.execute('INSERT INTO orders(user_id,iso,api_price,sell_price,status,service) VALUES(?,?,?,?,?,?)',(q.from_user.id,iso,int(row.get('api_price') or 0),int(row.get('sell_price') or 0),'invoice','Telegram'))
  o=dict(row); o.update({'discount_amount':0,'coupon_code':None})
  await q.answer(); return await render_msg(q.message,q.from_user.id,invoice_text(oid,o,l),invoice(oid,l))
 except Exception:
  logging.exception('country callback failed')
  try: await q.answer('خطا در ساخت فاکتور. لطفاً دوباره تلاش کنید.',show_alert=True)
  except: pass

@r.callback_query(F.data.startswith('country2:'))
async def country2(q):
 l=await language(q.from_user.id) or 'fa'
 try:
  if not await gate(q): return
  if not bz.enabled or await db.setting('second_panel_enabled','0')!='1': return await q.answer(t(l,'panel_off'),show_alert=True)
  iso=q.data.split(':',1)[1].upper().strip(); row=await db.one('SELECT * FROM panel2_countries WHERE iso=?',(iso,))
  if not row:return await q.answer('کشور پیدا نشد.',show_alert=True)
  if int(row.get('enabled') or 0)!=1 or int(row.get('stock') or 0)<=0 or int(row.get('sell_price') or 0)<=0:return await q.answer(t(l,'no_stock'),show_alert=True)
  oid=await db.execute('INSERT INTO orders(user_id,iso,api_price,sell_price,status,service,provider) VALUES(?,?,?,?,?,?,?)',(q.from_user.id,iso,0,int(row['sell_price']),'invoice','Telegram','biyora'))
  o={'iso':iso,'name':row.get('name') or iso,'sell_price':int(row['sell_price']),'discount_amount':0,'coupon_code':None}
  await q.answer(); return await render_msg(q.message,q.from_user.id,invoice_text(oid,o,l),invoice(oid,l))
 except Exception:
  logging.exception('country2 callback failed')
  try: await q.answer('خطا در ساخت فاکتور. لطفاً دوباره تلاش کنید.',show_alert=True)
  except: pass

@r.callback_query(F.data.startswith('coupon:order:'))
async def order_coupon_start(q,state):
 oid=int(q.data.split(':')[2]); o=await db.one("SELECT * FROM orders WHERE id=? AND user_id=? AND status='invoice'",(oid,q.from_user.id))
 if not o:return await q.answer('این فاکتور دیگر فعال نیست.',show_alert=True)
 await state.set_state(S.order_coupon); await state.update_data(coupon_order_id=oid); await q.answer()
 return await render_msg(q.message,q.from_user.id,'🎟️ کد تخفیف را ارسال کن:',InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به فاکتور',f'invoice:back:{oid}','primary',IDS['lock'])]]))

@r.message(S.order_coupon)
async def order_coupon_apply(m,state):
 oid=int((await state.get_data()).get('coupon_order_id') or 0); code=(m.text or '').strip().upper(); l=await language(m.from_user.id) or 'fa'
 o=await db.one("SELECT * FROM orders WHERE id=? AND user_id=? AND status='invoice'",(oid,m.from_user.id))
 if not o: await state.clear(); return await m.answer('فاکتور منقضی شده است.')
 c=await db.one('SELECT * FROM coupons WHERE code=? AND enabled=1',(code,))
 if not c:return await m.answer('❌ کد تخفیف معتبر نیست. دوباره ارسال کن یا به فاکتور برگرد.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به فاکتور',f'invoice:back:{oid}','primary',IDS['lock'])]]))
 if int(c['max_uses'] or 0)>0 and int(c['used'] or 0)>=int(c['max_uses']):return await m.answer('ظرفیت استفاده از این کد تمام شده است.')
 base=int(o['sell_price'] or 0); discount=min(base,base*int(c['value'])//100 if c['kind']=='percent' else int(c['value']))
 await db.execute("UPDATE orders SET coupon_code=?,discount_amount=? WHERE id=? AND status='invoice'",(code,discount,oid))
 await state.clear()
 try: await m.delete()
 except Exception: pass
 o=await db.one('SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=?',(oid,))
 mid=await screen_id(m.from_user.id)
 if mid:
  try:
   await m.bot.edit_message_text(invoice_text(oid,o,l),chat_id=m.chat.id,message_id=mid,parse_mode='HTML',reply_markup=invoice(oid,l)); return
  except Exception: pass
 return await render(m.bot,m.from_user.id,m.chat.id,invoice_text(oid,o,l),invoice(oid,l))

@r.callback_query(F.data.regexp(r'^invoice:(pay|cancel):\d+$'))
async def invoice_action(q,state):
 l=await language(q.from_user.id) or 'fa'; _,action,raw=q.data.split(':'); oid=int(raw); o=await db.one("SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=? AND o.user_id=?",(oid,q.from_user.id))
 if not o:return await q.answer('فاکتور پیدا نشد.',show_alert=True)
 if action=='cancel':
  if o['status']!='invoice':return await q.answer('این فاکتور دیگر قابل لغو نیست.',show_alert=True)
  await db.execute("UPDATE orders SET status='cancelled' WHERE id=? AND user_id=? AND status='invoice'",(oid,q.from_user.id)); await db.execute("UPDATE payments SET status='cancelled' WHERE order_id=? AND status='pending'",(oid,)); await q.answer(); return await render_msg(q.message,q.from_user.id,'خرید لغو شد.',back('menu:buy',l))
 if o['status']!='invoice':return await q.answer('این فاکتور دیگر قابل پرداخت نیست.',show_alert=True)
 bal=int(await db.scalar('SELECT balance FROM users WHERE id=?',(q.from_user.id,),0)); amount=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
 text=f'{pe("online","💳")} <b>مبلغ قابل پرداخت: {amount:,} تومان</b>\n\n{pe("balance","💰")} موجودی کیف پول شما: <b>{bal:,} تومان</b>\n\nروش پرداخت را انتخاب کن:'
 await q.answer(); return await render_msg(q.message,q.from_user.id,text,order_payment(oid,l,await methods()))

@r.callback_query(F.data.startswith('orderpay:'))
async def orderpay(q,state):
 parts=q.data.split(':'); method=parts[1]; oid=int(parts[2]); l=await language(q.from_user.id) or 'fa'
 o=await db.one("SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=? AND o.user_id=? AND o.status='invoice'",(oid,q.from_user.id))
 if not o:return await q.answer('فاکتور دیگر فعال نیست.',show_alert=True)
 amount=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
 if method=='wallet':
  if not await phone_ok(q.from_user.id):
   await state.update_data(pay_amount=amount,purpose='order',order_id=oid); await q.answer(); return await q.message.answer(t(l,'phone_required'),reply_markup=contact(l))
  if await kyc_required(q.from_user.id,amount):return await q.answer('ابتدا احراز هویت را تکمیل کن.',show_alert=True)
  if not await db.debit(q.from_user.id,amount):return await q.answer('موجودی کیف پول کافی نیست.',show_alert=True)
  ok,phone=await fulfill_order(q.from_user.id,oid,q.bot)
  if not ok: await db.adjust_balance(q.from_user.id,amount); return await q.answer(t(l,'api_error'),show_alert=True)
  await db.execute("UPDATE payments SET status='cancelled' WHERE order_id=? AND status='pending'",(oid,))
  o=await db.one('SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=?',(oid,))
  await q.answer(); return await render_msg(q.message,q.from_user.id,delivery_text(oid,o,phone),order_ready_actions(oid,phone))
 if method in ('card','crypto','okaypay','okaypay_usdt','okaypay_trx'):
  if method.startswith('okaypay'):
   if await db.setting('gateway_enabled','0')!='1': return await q.answer('پرداخت OkayPay از پنل مدیریت غیرفعال است.',show_alert=True)
   coin='TRX' if method.endswith('trx') else 'USDT'
   try: pid,url,coin_amount,rates=await make_okaypay_link(q.bot,q.from_user.id,amount,coin,'order',oid)
   except Exception: return await q.answer('ساخت لینک پرداخت ناموفق بود؛ مدیر فنی مطلع شد.',show_alert=True)
   msg=(f'<b>پرداخت با OkayPay · {coin}</b>\n\nمبلغ فاکتور: <b>{amount:,} تومان</b>\n'
        f'مبلغ پرداخت: <b>{coin_amount} {coin}</b>\nنرخ تتر: <b>{rates["usdt_toman"]:,.0f} تومان</b>\n'
        f'نرخ TRX: <b>{rates["trx_usd"]} دلار</b>\n\nپس از پرداخت، وضعیت به‌صورت خودکار بررسی می‌شود.')
   await q.answer()
  return await render_msg(q.message,q.from_user.id,msg,InlineKeyboardMarkup(inline_keyboard=[[ib('پرداخت امن با OkayPay',None,'success','4915937975507879321',url=url)],[ib('بازگشت به فاکتور',f'invoice:back:{oid}','primary',IDS['lock'])]]))
  payment_method={'card':'card','crypto':'crypto'}[method]
  pid=await create_payment(q.from_user.id,amount,payment_method,'order',oid)
  await state.update_data(payment_id=pid,pay_amount=amount,purpose='order',order_id=oid)
  if method=='card':
   await state.set_state(S.receipt); card=await db.setting('card_number','-'); owner=await db.setting('card_owner','-')
   await q.answer(); await q.message.answer('⁣',reply_markup=ReplyKeyboardRemove())
   return await render_msg(q.message,q.from_user.id,f'💳 <b>پرداخت کارت‌به‌کارت</b>\n\nشماره کارت: <code>{html.escape(card)}</code>\nصاحب کارت: <b>{html.escape(owner)}</b>\n\nمبلغ: <b>{amount:,} تومان</b>\n\nرسید را به صورت عکس ارسال کن.',back(f'invoice:back:{oid}',l))
  if method=='crypto':
   await state.set_state(S.txhash); wallets=await crypto_wallet_lines()
   await q.answer(); await q.message.answer('⁣',reply_markup=ReplyKeyboardRemove())
   return await render_msg(q.message,q.from_user.id,f'{wallets}\n\nمبلغ: <b>{amount:,} تومان</b>\n\nهش تراکنش را ارسال کن.',back(f'invoice:back:{oid}',l))
 return await q.answer('روش پرداخت نامعتبر است.',show_alert=True)

@r.callback_query(F.data=='wallet:add')
async def wallet_add(q,state):
 l=await language(q.from_user.id) or 'fa'; await state.set_state(S.topup); await q.answer(); bal=int(await db.scalar('SELECT balance FROM users WHERE id=?',(q.from_user.id,),0)); await render_msg(q.message,q.from_user.id,f'{pe("wallet","💰")} <b>{t(l,"wallet_title")}</b>\n\n{t(l,"current",bal=bal)}\n\n{pe("add","➕")} <b>{t(l,"topup")}</b>\n\n{t(l,"topup_amount")}',back('menu:wallet',l))
@r.callback_query(F.data=='wallet:transfer')
async def wallet_transfer(q,state):
 l=await language(q.from_user.id) or 'fa'
 if await db.setting('transfer_enabled','1')!='1':return await q.answer('انتقال موجودی غیرفعال است.',show_alert=True)
 await state.set_state(S.transfer_amount); await q.answer(); await render_msg(q.message,q.from_user.id,'↔️ <b>'+t(l,'transfer')+'</b>\n\n'+t(l,'amount'),back('menu:wallet',l))
@r.callback_query(F.data=='menu:wallet')
async def menu_wallet(q,state): await state.clear(); await q.answer(); return await show_wallet(q.message,q.from_user.id,await language(q.from_user.id) or 'fa')
@r.message(S.topup)
async def topup_amount(m,state):
 l=await language(m.from_user.id) or 'fa'
 try: amount=int(re.sub(r'[^0-9]','',m.text))
 except: return await m.answer(t(l,'topup_amount'))
 mn=int(await db.setting('min_topup','100')); mx=int(await db.setting('max_topup','0'))
 if await db.setting('topup_enabled','1')!='1':return await m.answer(t(l,'topup_off'))
 if amount<mn:return await m.answer(f'حداقل شارژ: {mn:,} تومان',reply_markup=back('menu:wallet',l))
 if mx and amount>mx:return await m.answer(f'حداکثر شارژ: {mx:,} تومان',reply_markup=back('menu:wallet',l))
 if not await phone_ok(m.from_user.id):
  await state.update_data(pay_amount=amount,purpose='topup',order_id=None); return await render(m.bot,m.from_user.id,m.chat.id,t(l,'phone_required'),contact(l))
 if await kyc_required(m.from_user.id,amount): await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,t(l,'kyc_needed')+'\n\n'+content(l,'kyc'),InlineKeyboardMarkup(inline_keyboard=[[ib('احراز هویت',None,url='https://t.me/shrwein',style='success',icon=IDS['kyc'])],[ib(t(l,'back'),'menu:wallet','primary',IDS['lock'])]]))
 await state.update_data(pay_amount=amount,purpose='topup',order_id=None); await render(m.bot,m.from_user.id,m.chat.id,t(l,'payment_methods')+f'\n\n<b>{amount:,} تومان</b>',payment_methods(l,await methods(),'menu:wallet')); await state.set_state(S.payment_wait)
@r.message(S.transfer_amount)
async def transfer_amount(m,state):
 l=await language(m.from_user.id) or 'fa'
 try: amount=int(re.sub(r'[^0-9]','',m.text))
 except:return await m.answer(t(l,'amount'))
 if amount<=0:return await m.answer(t(l,'amount'))
 await state.update_data(amount=amount); await state.set_state(S.transfer_receiver); await m.answer(t(l,'recipient'),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ib(t(l,'back'),'menu:wallet','primary',IDS['lock'])]]))
@r.message(S.transfer_receiver)
async def transfer_receiver(m,state):
 l=await language(m.from_user.id) or 'fa'
 if not m.text.isdigit():return await m.answer(t(l,'recipient'))
 d=await state.get_data(); ok=await db.transfer(m.from_user.id,int(m.text),int(d['amount'])); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,t(l,'transfer_done') if ok else t(l,'transfer_bad'),back('menu:wallet',l))

@r.message(F.contact)
async def contact_received(m,state):
 u=await ensure(m); l=u['language'] or 'fa'; phone=m.contact.phone_number
 if await state.get_state() in (S.kyc_phone.state,S.kyc_card.state,S.kyc_video.state):
  if m.contact.user_id and m.contact.user_id!=m.from_user.id:return await m.answer('لطفاً شماره متعلق به حساب خودتان را ارسال کنید.')
  try:
   parsed=phonenumbers.parse('+'+phone.lstrip('+'),None)
   if not phonenumbers.is_valid_number(parsed): return await m.answer('شماره تلفن معتبر نیست؛ از دکمه ارسال شماره خودتان استفاده کنید.')
  except Exception: return await m.answer('شماره تلفن معتبر نیست.')
  await db.execute('UPDATE users SET phone=?,phone_country=? WHERE id=?',(phone,region_code_for_number(parsed) or '',m.from_user.id))
  await db.execute("INSERT INTO kyc(user_id,phone,status) VALUES(?,?,'pending') ON CONFLICT(user_id) DO UPDATE SET phone=excluded.phone",(m.from_user.id,phone))
  await state.set_state(S.kyc_card)
  return await m.answer('<tg-emoji emoji-id="5927169041595634481">💳</tg-emoji> لطفا شماره کارت 16 رقمی خود را وارد نمایید:\n\n<tg-emoji emoji-id="6003364252507709759">⚠️</tg-emoji> توجه داشته باشید شماره کارت شما باید برابر کارت بانکی باشد که در ویدیو احراز هویت ارسال می کنید',parse_mode='HTML',reply_markup=ReplyKeyboardRemove())
 if m.contact.user_id and m.contact.user_id!=m.from_user.id:return await m.answer(t(l,'phone_required'))
 try:
  p=phonenumbers.parse('+'+phone.lstrip('+'),None); iso=region_code_for_number(p) or ''; name=description_for_number(p,'en') or iso; flag=flag_for(iso)
 except:return await m.answer('شماره معتبر نیست.')
 await db.execute('UPDATE users SET phone=?,phone_country=? WHERE id=?',(phone,iso,m.from_user.id)); data=await state.get_data(); amount=int(data.get('pay_amount') or 0); purpose=data.get('purpose')
 if amount:
  await state.clear()
  if await kyc_required(m.from_user.id,amount):return await render(m.bot,m.from_user.id,m.chat.id,t(l,'kyc_needed')+'\n\n'+content(l,'kyc'),InlineKeyboardMarkup(inline_keyboard=[[ib('احراز هویت',None,url='https://t.me/shrwein',style='success',icon=IDS['kyc'])],[ib(t(l,'back'),'menu:wallet','primary',IDS['lock'])]]))
  if purpose=='order' and data.get('order_id'):
   oid=int(data['order_id']); o=await db.one("SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=? AND o.user_id=? AND o.status='invoice'",(oid,m.from_user.id))
   if not o:return await m.answer('فاکتور دیگر فعال نیست.')
   bal=int(await db.scalar('SELECT balance FROM users WHERE id=?',(m.from_user.id,),0)); due=max(0,int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))
   text=f'💳 <b>مبلغ قابل پرداخت: {due:,} تومان</b>\n\n💰 موجودی کیف پول شما: <b>{bal:,} تومان</b>\n\nروش پرداخت را انتخاب کن:'
   return await render(m.bot,m.from_user.id,m.chat.id,text,order_payment(oid,l,await methods()))
  await state.update_data(pay_amount=amount,purpose=purpose,order_id=data.get('order_id')); await state.set_state(S.payment_wait); return await render(m.bot,m.from_user.id,m.chat.id,t(l,'payment_methods')+f'\n\n<b>{amount:,} تومان</b>',payment_methods(l,await methods(),'menu:wallet'))
 await render(m.bot,m.from_user.id,m.chat.id,t(l,'confirm',name=name,flag=flag),InlineKeyboardMarkup(inline_keyboard=[[ib('تأیید','phone:confirm','success',IDS['add']),ib(t(l,'back'),'menu:account','primary',IDS['lock'])]]))
@r.callback_query(F.data=='phone:send')
async def phone_send(q): await q.answer(); l=await language(q.from_user.id) or 'fa'; await q.message.answer(t(l,'phone_required'),reply_markup=contact(l))
@r.callback_query(F.data=='phone:confirm')
async def phone_confirm(q): await q.answer(); l=await language(q.from_user.id) or 'fa'; await show_account(q.message,q.from_user.id,l)
@r.callback_query(F.data=='kyc:open')
async def kyc_open(q,state): await q.answer(); return await show_kyc(q.message,q.from_user.id,await language(q.from_user.id) or 'fa',state)

@r.callback_query(F.data.startswith('invoice:back:'))
async def invoice_back(q,state):
 oid=int(q.data.split(':')[2]); l=await language(q.from_user.id) or 'fa'; await state.clear()
 o=await db.one("SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=? AND o.user_id=? AND o.status='invoice'",(oid,q.from_user.id))
 if not o:return await q.answer('فاکتور پیدا نشد.',show_alert=True)
 return await render_msg(q.message,q.from_user.id,invoice_text(oid,o,l),invoice(oid,l))

@r.callback_query(F.data.startswith('paymethod:'))
async def paymethod(q,state):
 method=q.data.split(':')[1]; l=await language(q.from_user.id) or 'fa'; d=await state.get_data(); amount=int(d.get('pay_amount') or 0); oid=d.get('order_id'); purpose=d.get('purpose','topup')
 if not amount:return await q.answer('مبلغ پرداخت مشخص نیست.',show_alert=True)
 if method=='gateway':
  if await db.setting('gateway_enabled','0')!='1': return await q.answer(t(l,'gateway_off'),show_alert=True)
  return await render_msg(q.message,q.from_user.id,f'<b>انتخاب ارز پرداخت OkayPay</b>\n\nمبلغ: <b>{amount:,} تومان</b>',InlineKeyboardMarkup(inline_keyboard=[[ib('پرداخت با USDT','paymethod:okaypay_usdt','success','4915937975507879321')],[ib('پرداخت با TRX','paymethod:okaypay_trx','primary','4915937975507879321')],[ib(t(l,'back'),'menu:wallet','primary',IDS['lock'])]]))
 if method in ('okaypay_usdt','okaypay_trx'):
  if await db.setting('gateway_enabled','0')!='1': return await q.answer(t(l,'gateway_off'),show_alert=True)
  coin='TRX' if method.endswith('trx') else 'USDT'
  try: pid,url,coin_amount,rates=await make_okaypay_link(q.bot,q.from_user.id,amount,coin,purpose,oid)
  except Exception: return await q.answer('ساخت لینک پرداخت ناموفق بود؛ مدیر فنی مطلع شد.',show_alert=True)
  msg=(f'<b>پرداخت با OkayPay · {coin}</b>\n\nمبلغ: <b>{amount:,} تومان</b>\n'
       f'مبلغ پرداخت: <b>{coin_amount} {coin}</b>\nنرخ تتر: <b>{rates["usdt_toman"]:,.0f} تومان</b>\n'
       f'نرخ TRX: <b>{rates["trx_usd"]} دلار</b>\n\nوضعیت پرداخت به‌صورت خودکار بررسی می‌شود.')
  await q.answer()
  return await render_msg(q.message,q.from_user.id,msg,InlineKeyboardMarkup(inline_keyboard=[[ib('پرداخت امن با OkayPay',None,'success','4915937975507879321',url=url)],[ib(t(l,'back'),'menu:wallet','primary',IDS['lock'])]]))
 if method=='card':
  pid=await create_payment(q.from_user.id,amount,'card',purpose,oid); await state.set_state(S.receipt); await state.update_data(payment_id=pid); card=await db.setting('card_number','-'); owner=await db.setting('card_owner','-'); await q.message.answer('⁣',reply_markup=ReplyKeyboardRemove()); return await render_msg(q.message,q.from_user.id,f'💳 <b>کارت‌به‌کارت</b>\n\nشماره کارت: <code>{html.escape(card)}</code>\nصاحب کارت: <b>{html.escape(owner)}</b>\n\nمبلغ: <b>{amount:,} تومان</b>\n\n{t(l,"receipt")}',back('menu:wallet',l))
 if method=='crypto':
  pid=await create_payment(q.from_user.id,amount,'crypto',purpose,oid); await state.set_state(S.txhash); await state.update_data(payment_id=pid); wallets=await crypto_wallet_lines(); await q.message.answer('⁣',reply_markup=ReplyKeyboardRemove()); return await render_msg(q.message,q.from_user.id,f'{wallets}\n\nمبلغ معادل: <b>{amount:,} تومان</b>\n\n{t(l,"hash")}',back('menu:wallet',l))
def payment_review_keyboard(pid):
 return InlineKeyboardMarkup(inline_keyboard=[[ib('🔎 بررسی پرداخت',f'payment:submit:{pid}','success',IDS['add'])],[ib('بازگشت به کیف پول','menu:wallet','primary',IDS['lock'])]])

@r.message(S.receipt)
async def receipt(m,state):
 file_id=(m.photo[-1].file_id if m.photo else (m.document.file_id if m.document and (m.document.mime_type or '').startswith('image/') else None))
 if not file_id:return await m.answer('لطفاً رسید را به‌صورت عکس ارسال کنید.')
 d=await state.get_data(); pid=d.get('payment_id')
 if not pid: await state.clear(); return await m.answer('پرداخت فعال پیدا نشد؛ از بخش کیف پول دوباره اقدام کن.')
 changed=await db.execute("UPDATE payments SET receipt_file_id=? WHERE id=? AND status='pending'",(file_id,pid))
 await state.clear()
 p=await db.one("SELECT id FROM payments WHERE id=? AND user_id=? AND status='pending'",(pid,m.from_user.id))
 if not p:return await render(m.bot,m.from_user.id,m.chat.id,'این پرداخت دیگر در انتظار بررسی نیست.',back('menu:wallet',await language(m.from_user.id) or 'fa'))
 return await render(m.bot,m.from_user.id,m.chat.id,'✅ رسید ثبت شد. برای ارسال به گروه بررسی، روی دکمه زیر بزن.',payment_review_keyboard(pid))

@r.message(S.txhash)
async def txhash(m,state):
 if not m.text:return await m.answer('Hash را ارسال کنید.')
 d=await state.get_data(); pid=d.get('payment_id')
 if not pid: await state.clear(); return await m.answer('پرداخت فعال پیدا نشد؛ از بخش کیف پول دوباره اقدام کن.')
 await db.execute("UPDATE payments SET tx_hash=? WHERE id=? AND status='pending'",(m.text.strip(),pid)); await state.clear()
 return await render(m.bot,m.from_user.id,m.chat.id,'✅ هش تراکنش ثبت شد. برای ارسال به گروه بررسی، روی دکمه زیر بزن.',payment_review_keyboard(pid))

@r.callback_query(F.data.startswith('payment:submit:'))
async def payment_submit(q):
 pid=int(q.data.rsplit(':',1)[1])
 p=await db.one("SELECT * FROM payments WHERE id=? AND user_id=? AND status='pending'",(pid,q.from_user.id))
 if not p:return await q.answer('این پرداخت پیدا نشد یا قبلاً بررسی شده است.',show_alert=True)
 if not p.get('receipt_file_id') and not p.get('tx_hash'):
  return await q.answer('اول رسید یا هش تراکنش را ارسال کن.',show_alert=True)
 if 'submitted_to_accounting' in str(p.get('note') or ''):
  return await q.answer('این پرداخت قبلاً برای بررسی ارسال شده است.',show_alert=True)
 claimed=await db.one("UPDATE payments SET note='submitted_to_accounting' WHERE id=? AND user_id=? AND status='pending' AND (note IS NULL OR note='') RETURNING id",(pid,q.from_user.id))
 if not claimed:return await q.answer('این پرداخت قبلاً برای بررسی ارسال شده است.',show_alert=True)
 sent=await send_accounting(q.bot,pid)
 if not sent:
  await db.execute("UPDATE payments SET note=NULL WHERE id=? AND status='pending' AND note='submitted_to_accounting'",(pid,))
  return await q.answer('ارسال به گروه ناموفق بود؛ کمی بعد دوباره تلاش کن.',show_alert=True)
 await q.answer('پرداخت برای بررسی ارسال شد.')
 try: await q.message.edit_reply_markup(reply_markup=back('menu:wallet',await language(q.from_user.id) or 'fa'))
 except Exception: pass

@r.callback_query(F.data.startswith('hist:'))
async def history(q):
 l=await language(q.from_user.id) or 'fa'; typ=q.data.split(':')[1]
 if typ=='topup': rows=await db.all("SELECT * FROM payments WHERE user_id=? AND purpose='topup' ORDER BY id DESC LIMIT 20",(q.from_user.id,)); lines=[f'#{x["id"]} | {x["amount"]:,} تومان | { {'card':'کارت‌به‌کارت','crypto':'ارز دیجیتال','gateway':'OkayPay','gateway_usdt':'OkayPay · USDT','gateway_trx':'OkayPay · TRX'}.get(x["method"],x["method"])} | { {'pending':'در انتظار تأیید','approved':'تأیید شد','rejected':'رد شد'}.get(x["status"],x["status"])}' for x in rows]; title=pe('history_topup','🧾')+' <b>تاریخچه افزایش موجودی</b>'
 else: rows=await db.all("SELECT o.*,c.name AS country_name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.user_id=? AND o.status='success' ORDER BY o.id DESC LIMIT 20",(q.from_user.id,)); lines=[f'#{x["id"]} | {html.escape(clean_country_name(x.get("country_name") or x["iso"]))} | {max(0,int(x["sell_price"] or 0)-int(x.get("discount_amount") or 0)):,} تومان | موفق' for x in rows]; title=pe('history_buy','🛒')+' <b>تاریخچه خرید</b>'
 return await render_msg(q.message,q.from_user.id,title+'\n\n'+('\n'.join(lines) or t(l,'not_found')),back('menu:account',l))
@r.callback_query(F.data=='menu:account')
async def menu_account(q): return await show_account(q.message,q.from_user.id,await language(q.from_user.id) or 'fa')
@r.callback_query(F.data=='menu:kyc')
async def menu_kyc(q,state): return await show_kyc(q.message,q.from_user.id,await language(q.from_user.id) or 'fa',state)
@r.callback_query(F.data.startswith('help:'))
async def help_page(q):
 l=await language(q.from_user.id) or 'fa'; k=q.data.split(':')[1]; text={'faq':'<b>'+t(l,'faq')+'</b>\n\nقیمت و موجودی از API همگام می‌شود. برای خرید، کشور موجود را انتخاب و سپس فاکتور را پرداخت کنید.','rules':content(l,'rules'),'usage':content(l,'usage'),'about':content(l,'about'),'unreport':content(l,'unreport')}.get(k,'<b>راهنما</b>'); return await render_msg(q.message,q.from_user.id,text,back('menu:help',l))
@r.callback_query(F.data=='menu:help')
async def menu_help(q): l=await language(q.from_user.id) or 'fa'; return await render_msg(q.message,q.from_user.id,'<b>راهنما و سوالات متداول جت نامبر</b>',help_menu(l))

@r.callback_query(F.data=='menu:buy')
async def menu_buy(q):
 l=await language(q.from_user.id) or 'fa'; return await show_countries(q,l)
@r.callback_query(F.data=='menu:guide')
async def menu_guide(q):
 l=await language(q.from_user.id) or 'fa'; return await render_msg(q.message,q.from_user.id,content(l,'guide'),back('home',l))
@r.callback_query(F.data=='menu:support')
async def menu_support(q):
 l=await language(q.from_user.id) or 'fa'; return await render_msg(q.message,q.from_user.id,content(l,'support'),back('home',l))
@r.callback_query(F.data=='menu:lang')
async def menu_lang(q):
 l=await language(q.from_user.id) or 'fa'; return await render_msg(q.message,q.from_user.id,t(l,'lang'),langs())

@r.callback_query(F.data.startswith('code:'))
async def order_code(q):
 l=await language(q.from_user.id) or 'fa'; oid=int(q.data.split(':')[1]); o=await db.one("SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=? AND o.user_id=? AND o.status='success'",(oid,q.from_user.id))
 if not o or not o.get('phone'):return await q.answer('سفارش آماده دریافت کد نیست.',show_alert=True)
 await db.execute('UPDATE orders SET code_requested_at=COALESCE(code_requested_at,CURRENT_TIMESTAMP) WHERE id=?',(oid,))
 try:
  data=await (bz.code(o.get('provider_id')) if o.get('provider')=='biyora' else api.code(o['phone'])); d=data.get('data',data); code=d.get('code') or d.get('sms_code') or d.get('verification_code') or d.get('activation_code')
  if not code:
   try: await q.message.edit_reply_markup(reply_markup=code_wait_actions(oid))
   except Exception: pass
   return await q.answer(t(l,'code_wait'),show_alert=True)
  await db.execute('UPDATE orders SET code=? WHERE id=?',(str(code),oid)); await q.answer()
  text=(f'{pe("code_received","🔐")} <b>کد دریافت شده:</b> <code>{html.escape(str(code))}</code>\n\n'
        f'{pe("code_warning","⏱️")} توجه داشته باشید مدت وارد کردن کد تنها ۱ دقیقه می‌باشد\n\n'
        f'{pe("code_again","⚠️")} درصورتی که با خطا مواجه شدید مجدد از طریق دکمه دریافت کد مجدد درخواست کد بدهید\n\n'
        f'{pe("code_logout","🚪")} پس از ورود به اکانت از گزینه خروج بات از اکانت استفاده کنید تا ربات خارج شود')
  return await render_msg(q.message,q.from_user.id,text,code_actions(oid,str(code)))
 except Exception as e:
  if isinstance(e,BiyoraError) and e.code=='order_expired':
   done,amount=await refund_dead_biyora_order(o); await q.answer()
   return await render_msg(q.message,q.from_user.id,f'⌛ مهلت این سفارش به پایان رسید و شماره آزاد شد.\n\nمبلغ <b>{amount:,} تومان</b> به کیف پول شما برگشت.',back('menu:account',l))
  logging.warning('code failed: %s',e)
  try: await notify_admin_error(q.bot,'دریافت کد از '+('BIYORA' if o.get('provider')=='biyora' else 'TNumber API'),e,f'کاربر: {q.from_user.id} · سفارش: {oid}')
  except Exception: pass
  try: await q.message.edit_reply_markup(reply_markup=code_wait_actions(oid))
  except Exception: pass
  return await q.answer(t(l,'code_wait'),show_alert=True)

@r.callback_query(F.data.startswith('logout:'))
async def order_logout(q):
 oid=int(q.data.split(':')[1]); o=await db.one("SELECT * FROM orders WHERE id=? AND user_id=? AND status='success'",(oid,q.from_user.id))
 if not o or not o.get('phone'):return await q.answer('سفارش پیدا نشد.',show_alert=True)
 if o.get('logout_at'):
  await report(q.bot,oid)
  fresh=await db.one('SELECT report_sent_at FROM orders WHERE id=?',(oid,))
  if fresh and fresh.get('report_sent_at'): return await q.answer('ربات قبلاً خارج شده و گزارش ثبت شده است.',show_alert=True)
  return await q.answer('خروج انجام شده؛ ارسال گزارش ناموفق بود. دسترسی گروه گزارش را بررسی کن و دوباره بزن.',show_alert=True)
 try:
  await (bz.complete(o.get('provider_id')) if o.get('provider')=='biyora' else api.logout(o['phone'])); await db.execute('UPDATE orders SET logout_at=CURRENT_TIMESTAMP WHERE id=? AND logout_at IS NULL',(oid,)); await q.answer()
  await report(q.bot,oid)
  l=await language(q.from_user.id) or 'fa'; return await render_msg(q.message,q.from_user.id,f'{pe("online","✅")} <b>ربات با موفقیت از اکانت خارج شد.</b>\n\nگزارش خرید در کانال ثبت شد.',back('menu:account',l))
 except Exception as e:
  logging.warning('logout failed: %s',e)
  try: await notify_admin_error(q.bot,'خروج از اکانت در '+('BIYORA' if o.get('provider')=='biyora' else 'TNumber API'),e,f'کاربر: {q.from_user.id} · سفارش: {oid}')
  except Exception: pass
  return await q.answer(t(await language(q.from_user.id) or 'fa','api_error'),show_alert=True)

@r.callback_query(F.data.startswith('cancel:'))
async def order_cancel(q):
 parts=q.data.split(':'); action=parts[1] if len(parts)>2 else 'confirm'; oid=int(parts[-1]); l=await language(q.from_user.id) or 'fa'; o=await db.one('SELECT * FROM orders WHERE id=? AND user_id=?',(oid,q.from_user.id))
 if not o:return await q.answer('سفارش پیدا نشد.',show_alert=True)
 if action=='ask':
  if o['status']!='success' or o.get('code_requested_at') or o.get('code'):return await q.answer('این سفارش دیگر قابل لغو نیست.',show_alert=True)
  text=f'{pe("cancel_warning","⚠️")} درصورت لغو سفارش شما به عنوان دریافت خسارت ۸۰ درصد از مبلغ پرداخت شده به حساب شما بازگشت می‌شود'
  return await render_msg(q.message,q.from_user.id,text,cancel_confirm(oid))
 if action=='back':
  return await render_msg(q.message,q.from_user.id,delivery_text(oid,o,o.get('phone') or ''),order_ready_actions(oid,o.get('phone') or ''))
 if action!='confirm':return await q.answer()
 if o['status']!='success' or o.get('code_requested_at') or o.get('code') or int(o.get('refund_amount') or 0)>0:return await q.answer('این سفارش دیگر قابل لغو نیست.',show_alert=True)
 try:
  if o.get('phone'):
   try: await (bz.release(o.get('provider_id')) if o.get('provider')=='biyora' else api.cancel(o['phone']))
   except Exception as e:
    try: await notify_admin_error(q.bot,'لغو سفارش در '+('BIYORA' if o.get('provider')=='biyora' else 'TNumber API'),e,f'کاربر: {q.from_user.id} · سفارش: {oid}')
    except Exception: pass
    raise
 except Exception as e:
  logging.warning('cancel api failed: %s',e); return await q.answer('لغو شماره در API ناموفق بود؛ مبلغی تغییر نکرد.',show_alert=True)
 refund=max(0,(int(o['sell_price'] or 0)-int(o.get('discount_amount') or 0))*80//100)
 await db.execute("UPDATE orders SET status='cancelled',refund_amount=? WHERE id=? AND status='success'",(refund,oid))
 if refund: await db.adjust_balance(q.from_user.id,refund)
 return await render_msg(q.message,q.from_user.id,f'{pe("cancel","✅")} سفارش لغو شد.\n\nمبلغ بازگشتی (۸۰٪): <b>{refund:,} تومان</b> به کیف پول شما اضافه شد.',back('menu:account',l))

# Admin helpers
async def admin_guard(q):
 if not await is_admin(q.from_user.id): await q.answer('⛔ دسترسی ندارید.',show_alert=True); return False
 return True
async def settings_dict(keys): return {k:await db.setting(k,'') for k in keys}

@r.callback_query(F.data.startswith('admin:'))
async def admin_router(q,state):
 if not await admin_guard(q):return
 a=q.data.split(':',1)[1]; await q.answer()
 if a=='home': return await render_msg(q.message,q.from_user.id,'<b>⚙️ پنل مدیریت جت نامبر</b>\n\nیک بخش را انتخاب کنید:',admin_menu())
 if a=='dash':
  users=int(await db.scalar('SELECT COUNT(*) FROM users',(),0)); sales=int(await db.scalar("SELECT COUNT(*) FROM orders WHERE status='success'",(),0)); pending=int(await db.scalar("SELECT COUNT(*) FROM payments WHERE status='pending'",(),0)); bal=int(await db.scalar('SELECT COALESCE(SUM(balance),0) FROM users',(),0)); return await render_msg(q.message,q.from_user.id,f'{pe("balance","📊")} <b>داشبورد مدیریتی جت نامبر</b>\n\n{pe("users","👥")} کاربران ثبت‌شده: <b>{users:,}</b>\n{pe("history_buy","🛒")} خریدهای موفق: <b>{sales:,}</b>\n{pe("invoice","🧾")} پرداخت‌های در انتظار: <b>{pending:,}</b>\n{pe("wallet_balance","💰")} مجموع موجودی کاربران: <b>{bal:,} تومان</b>',dashboard_menu())
 if a=='reports': return await render_msg(q.message,q.from_user.id,'<b>📈 گزارش‌ها</b>\n\nنوع گزارش را انتخاب کنید:',reports_menu())
 if a=='countries': rows=await db.all('SELECT * FROM countries ORDER BY name'); return await render_msg(q.message,q.from_user.id,'<b>🌍 کشورها</b>\n\n🟢 فعال | 🔴 خاموش',admin_countries(rows))
 if a=='products': rows=await db.all('SELECT * FROM countries ORDER BY name'); return await render_msg(q.message,q.from_user.id,'<b>🛍 محصولات</b>\n\nقیمت خرید = قیمت API\nقیمت فروش = قیمت نمایش به کاربر',admin_products(rows))
 if a=='users': await state.set_state(S.user_search); return await render_msg(q.message,q.from_user.id,'<b>👥 کاربران</b>\n\nآیدی عددی، @username یا نام کاربر را ارسال کنید.',admin_back())
 if a=='accounting': s=await settings_dict(['topup_enabled','card_enabled','gateway_enabled','crypto_enabled']); return await render_msg(q.message,q.from_user.id,'<b>🧾 حسابداری</b>\n\nهر گزینه را با دکمه تنظیم کنید.',accounting_menu(s))
 if a=='kyc': rows=await db.all("SELECT u.id,u.first_name,u.username,u.phone,k.status FROM kyc k JOIN users u ON u.id=k.user_id WHERE k.status='pending' ORDER BY k.created_at DESC LIMIT 50"); kb=InlineKeyboardMarkup(inline_keyboard=[[ib(f'{x["first_name"] or "-"} | {x["id"]}',f'kycuser:{x["id"]}','primary',IDS['verify'])] for x in rows]+[[ib('🔍 جستجوی کاربر','kycsearch','primary',IDS['users'])],[ib('🔙 بازگشت','admin:home','primary',IDS['lock'])]]); return await render_msg(q.message,q.from_user.id,'<b>🪪 احراز هویت</b>\n\nکاربر را انتخاب یا جستجو کنید.',kb)
 if a=='admins':
  rows=await db.all('SELECT * FROM admins ORDER BY created_at DESC'); owner_text=f'👤 admin: <code>858897695</code>\n👑 مالک جت نامبر: <code>7048466991</code>'
  return await render_msg(q.message,q.from_user.id,f'<b>👨‍💼 مدیران</b>\n\n{owner_text}',admins_menu(rows))
 if a=='channels': raw=await db.setting('force_join_channels',''); chans=[x for x in raw.splitlines() if x.strip()]; return await render_msg(q.message,q.from_user.id,'<b>📢 کانال‌های جوین اجباری</b>\n\nکانال‌ها را با دکمه اضافه یا حذف کنید.',channels_menu(chans))
 if a=='settings': s=await settings_dict(['sales_enabled','second_panel_enabled','transfer_enabled','topup_enabled','min_topup','max_topup','kyc_required_above','default_markup']); return await render_msg(q.message,q.from_user.id,'<b>تنظیمات عمومی</b>\n\nمقدار فعلی روی هر دکمه نمایش داده شده؛ برای تغییر، یکی را انتخاب کن.',settings_menu(s))
 if a=='coupon':
  rows=await db.all('SELECT * FROM coupons ORDER BY created_at DESC LIMIT 50')
  kb=[[ib(f'{"🟢" if x["enabled"] else "🔴"} {x["code"]} | {x["value"]}%',f'coupon:toggle:{x["code"]}','success' if x['enabled'] else 'danger',IDS['add'])] for x in rows]
  kb += [[ib('➕ ساخت/ویرایش کد','coupon:add','success',IDS['add'])],[ib('🔙 بازگشت','admin:home','primary',IDS['lock'])]]
  return await render_msg(q.message,q.from_user.id,'<b>🎟️ کد تخفیف</b>\n\nکدها را از همین بخش فعال یا غیرفعال کنید.',InlineKeyboardMarkup(inline_keyboard=kb))
 if a=='sync': n=await sync_countries(); return await render_msg(q.message,q.from_user.id,f'✅ {n} کشور از API همگام شد.',admin_back())
 if a=='gateway':
  status=f'App ID: {"تنظیم شده" if cfg.okaypay_id else "تنظیم نشده"}\nToken: {"تنظیم شده" if cfg.okaypay_token else "تنظیم نشده"}\n\nنرخ USDT: نوبیتکس\nنرخ TRX: CoinGecko\n\nکلیدها را فقط در فایل .env سرور وارد کن؛ از طریق چت ارسال نکن.'
  return await render_msg(q.message,q.from_user.id,'<b>تنظیمات OkayPay</b>\n\n'+status,InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به حسابداری','admin:accounting','primary',IDS['lock'])]]))

@r.callback_query(F.data.startswith('acountry:'))
async def acountry(q):
 if not await admin_guard(q):return
 iso=q.data.split(':')[1]; x=await db.one('SELECT * FROM countries WHERE iso=?',(iso,));
 if not x:return await q.answer('کشور پیدا نشد.',show_alert=True)
 await q.answer(); return await render_msg(q.message,q.from_user.id,f'<b>{html.escape(x["name"])} {flag_for(iso)}</b>\n\nوضعیت: {"فعال" if x["enabled"] else "خاموش"}\nموجودی API: <b>{int(x["api_count"]):,}</b>\nقیمت خرید API: <b>{int(x["api_price"]):,} تومان</b>\nقیمت فروش: <b>{int(x["sell_price"]):,} تومان</b>\nمارکاپ ثبت‌شده: <b>{int(x["markup"]):,} تومان</b>',country_edit(x))
@r.callback_query(F.data.startswith('country_toggle:'))
async def country_toggle(q):
 if not await admin_guard(q):return
 iso=q.data.split(':')[1]; await db.execute('UPDATE countries SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE iso=?',(iso,)); x=await db.one('SELECT * FROM countries WHERE iso=?',(iso,)); await q.answer('وضعیت کشور به‌روزرسانی شد.'); return await render_msg(q.message,q.from_user.id,f'<b>{html.escape(x["name"])} {flag_for(iso)}</b>\n\nوضعیت: {"فعال" if x["enabled"] else "خاموش"}\nموجودی API: <b>{int(x["api_count"]):,}</b>\nقیمت خرید API: <b>{int(x["api_price"]):,} تومان</b>\nقیمت فروش: <b>{int(x["sell_price"]):,} تومان</b>',country_edit(x))
@r.callback_query(F.data.startswith('country_markup:'))
async def country_markup(q,state):
 if not await admin_guard(q):return
 iso=q.data.split(':')[1]; await state.clear(); await q.answer(); return await render_msg(q.message,q.from_user.id,'مارکاپ این کشور را انتخاب کنید یا مقدار دلخواه را وارد کنید.',InlineKeyboardMarkup(inline_keyboard=[[ib('۰ تومان','country_markup_set:'+iso+':0','primary',IDS['price']),ib('۵٬۰۰۰ تومان','country_markup_set:'+iso+':5000','primary',IDS['price'])],[ib('۱۰٬۰۰۰ تومان','country_markup_set:'+iso+':10000','primary',IDS['price']),ib('۲۰٬۰۰۰ تومان','country_markup_set:'+iso+':20000','primary',IDS['price'])],[ib('مقدار دلخواه','country_markup_custom:'+iso,'primary',IDS['settings'])],[ib('بازگشت','acountry:'+iso,'primary',IDS['lock'])]]))
@r.callback_query(F.data.startswith('country_markup_set:'))
async def country_markup_set(q):
 if not await admin_guard(q):return
 _,iso,val=q.data.split(':'); v=int(val); await q.bot; await db.execute('UPDATE countries SET markup=?,sell_price=MAX(0,api_price+?) WHERE iso=?',(v,v,iso)); x=await db.one('SELECT * FROM countries WHERE iso=?',(iso,)); await q.answer('مارکاپ ذخیره شد.'); return await render_msg(q.message,q.from_user.id,f'<b>{html.escape(x["name"])}</b>\nمارکاپ: {v:,} تومان\nقیمت فروش: {x["sell_price"]:,} تومان',country_edit(x))
@r.callback_query(F.data.startswith('country_markup_custom:'))
async def country_markup_custom(q,state):
 if not await admin_guard(q):return
 iso=q.data.split(':')[1]; await state.set_state(S.admin_price); await state.update_data(price_iso=iso,price_field='markup'); await q.answer(); return await render_msg(q.message,q.from_user.id,'مقدار مارکاپ به تومان را وارد کنید.',admin_back())
@r.callback_query(F.data.startswith('prod:'))
async def prod(q):
 if not await admin_guard(q):return
 x=await db.one('SELECT * FROM countries WHERE iso=?',(q.data.split(':')[1],)); return await render_msg(q.message,q.from_user.id,f'<b>محصول: {x["name"]}</b>\n\nقیمت خرید: {x["api_price"]:,} تومان\nقیمت فروش: {x["sell_price"]:,} تومان\nموجودی API: {x["api_count"]:,}',product_edit(x))
@r.callback_query(F.data.startswith('prod_toggle:'))
async def prod_toggle(q):
 if not await admin_guard(q):return
 iso=q.data.split(':')[1]; await db.execute('UPDATE countries SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE iso=?',(iso,)); x=await db.one('SELECT * FROM countries WHERE iso=?',(iso,)); return await render_msg(q.message,q.from_user.id,f'<b>محصول: {x["name"]}</b>\n\nقیمت خرید: {x["api_price"]:,} تومان\nقیمت فروش: {x["sell_price"]:,} تومان',product_edit(x))
@r.callback_query(F.data.startswith('prod_buy:'))
async def prod_buy(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_price); await state.update_data(price_iso=q.data.split(':')[1],price_field='api_price'); await q.answer(); return await render_msg(q.message,q.from_user.id,'قیمت خرید جدید را به تومان ارسال کنید.',admin_back())
@r.callback_query(F.data.startswith('prod_sell:'))
async def prod_sell(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_price); await state.update_data(price_iso=q.data.split(':')[1],price_field='sell_price'); await q.answer(); return await render_msg(q.message,q.from_user.id,'قیمت فروش جدید را به تومان ارسال کنید.',admin_back())
@r.message(S.admin_price)
async def save_price(m,state):
 if not await is_admin(m.from_user.id):return
 try:v=int(re.sub(r'[^0-9-]','',m.text))
 except:return await m.answer('فقط عدد وارد کنید.')
 d=await state.get_data(); field=d['price_field']; iso=d['price_iso']; v=max(0,v)
 if field=='markup': await db.execute('UPDATE countries SET markup=?,sell_price=MAX(0,api_price+?) WHERE iso=?',(v,v,iso))
 else: await db.execute(f'UPDATE countries SET {field}=? WHERE iso=?',(v,iso))
 await state.clear(); x=await db.one('SELECT name,sell_price,markup FROM countries WHERE iso=?',(iso,)); return await render(m.bot,m.from_user.id,m.chat.id,f'<b>تغییر ذخیره شد</b>\n\nکشور: {html.escape(x["name"] if x else iso)}\nقیمت فروش: {int(x["sell_price"]):,} تومان\nمارکاپ: {int(x["markup"]):,} تومان',InlineKeyboardMarkup(inline_keyboard=[[ib('مشاهده کشور','acountry:'+iso,'primary',IDS['country'])],[ib('بازگشت به کشورها','admin:countries','primary',IDS['lock'])]]))
@r.callback_query(F.data.startswith('pricebulk:'))
async def pricebulk(q,state):
 if not await admin_guard(q):return
 sign=q.data.split(':')[1]; await q.answer(); return await render_msg(q.message,q.from_user.id,'<b>تغییر گروهی قیمت فروش</b>\n\nیک مقدار آماده انتخاب کن؛ یا مقدار دلخواه را بزن.',bulk_presets(sign))
@r.callback_query(F.data.startswith('pricebulk_apply:'))
async def pricebulk_apply(q):
 if not await admin_guard(q):return
 _,sign,raw=q.data.split(':'); factor=1 if sign=='+' else -1
 if raw.endswith('p'):
  pct=float(raw[:-1]); await db.execute(f'UPDATE countries SET sell_price=MAX(0,ROUND(sell_price * (1 {"+" if sign=="+" else "-"} ?/100.0)))',(pct,)); desc=f'{"افزایش" if sign=="+" else "کاهش"} {pct:g}٪'
 else:
  amount=int(raw); await db.execute('UPDATE countries SET sell_price=MAX(0,sell_price+?)',(factor*amount,)); desc=f'{"افزایش" if sign=="+" else "کاهش"} {amount:,} تومان'
 await q.answer('قیمت‌ها به‌روزرسانی شدند.'); return await render_msg(q.message,q.from_user.id,f'<b>تغییر گروهی انجام شد</b>\n\nعملیات: {desc}\nکشورهای موجود در فهرست قیمت به‌روزرسانی شدند.',InlineKeyboardMarkup(inline_keyboard=[[ib('مشاهده قیمت‌ها','admin:products','primary',IDS['invoice'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]]))
@r.callback_query(F.data.startswith('pricebulk_custom:'))
async def pricebulk_custom(q,state):
 if not await admin_guard(q):return
 sign=q.data.split(':')[1]; await state.set_state(S.price_bulk); await state.update_data(sign=sign); await q.answer(); return await render_msg(q.message,q.from_user.id,'مقدار دلخواه را وارد کنید؛ نمونه: 12000 یا 15٪',admin_back())
@r.message(S.price_bulk)
async def save_bulk(m,state):
 if not await is_admin(m.from_user.id):return
 d=await state.get_data(); raw=m.text.strip(); sign=d['sign'];
 try:
  if raw.endswith('%'): val=float(raw[:-1]); sql=f'UPDATE countries SET sell_price=MAX(0,ROUND(sell_price * (1 {"+" if sign=="+" else "-"} ?/100.0)) )'; await db.execute(sql,(val,))
  else: val=int(re.sub(r'[^0-9]','',raw)); delta=val if sign=='+' else -val; await db.execute('UPDATE countries SET sell_price=MAX(0,sell_price+?)',(delta,))
 except: return await m.answer('فرمت نامعتبر است.')
 await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'✅ تغییر گروهی قیمت انجام شد.',admin_back())

@r.message(S.user_search)
async def user_search(m,state):
 if not await is_admin(m.from_user.id):return
 q=m.text.strip(); rows=await db.all('SELECT * FROM users WHERE CAST(id AS TEXT)=? OR lower(COALESCE(username,""))=lower(?) OR first_name LIKE ? ORDER BY id DESC LIMIT 30',(q.lstrip('@'),q.lstrip('@'),f'%{q}%'))
 await state.clear()
 if not rows:return await render(m.bot,m.from_user.id,m.chat.id,'❌ کاربر پیدا نشد.',admin_back())
 kb=InlineKeyboardMarkup(inline_keyboard=[[ib(f'{x["first_name"] or "-"} | @{x["username"] or "-"} | {x["id"]}',f'user:{x["id"]}','primary',IDS['users'])] for x in rows]+[[ib('🔙 بازگشت','admin:home','primary',IDS['lock'])]])
 return await render(m.bot,m.from_user.id,m.chat.id,'<b>👥 نتایج جستجو</b>',kb)
@r.callback_query(F.data.startswith('user:'))
async def user_view(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); u=await user(uid)
 if not u:return await q.answer('کاربر پیدا نشد.',show_alert=True)
 total=await db.scalar("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='success'",(uid,),0)
 invoices=await db.scalar('SELECT COUNT(*) FROM orders WHERE user_id=?',(uid,),0)
 last=await db.one('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,))
 receipts=await db.scalar('SELECT COUNT(*) FROM payments WHERE user_id=? AND receipt_file_id IS NOT NULL',(uid,),0)
 latest=f'{last["iso"]} | {last["sell_price"]:,} تومان | {last["status"]}' if last else '-'
 text=(f'<b>👤 کاربر</b>\n\nنام: {html.escape(u["first_name"] or "-")}\nUsername: @{html.escape(u["username"] or "-")}\n'
       f'🆔 <code>{uid}</code>\n💰 موجودی: {u["balance"]:,} تومان\n🪪 احراز: {u["kyc_status"]}\n'
       f'🛒 خریدهای موفق: {total}\n🧾 تعداد فاکتورها: {invoices}\n🧾 رسیدهای ثبت‌شده: {receipts}\n📌 آخرین خرید: {html.escape(latest)}')
 return await render_msg(q.message,q.from_user.id,text,user_detail(u))
@r.callback_query(F.data.startswith('uban:'))
async def uban(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); u=await user(uid)
 if is_owner(uid):return await q.answer('مالک دائمی قابل بن نیست.',show_alert=True)
 await db.execute('UPDATE users SET banned=CASE banned WHEN 1 THEN 0 ELSE 1 END WHERE id=?',(uid,)); u=await user(uid); return await render_msg(q.message,q.from_user.id,f'<b>👤 کاربر</b>\n\n🆔 <code>{uid}</code>\n💰 {u["balance"]:,} تومان\nوضعیت بن: {u["banned"]}',user_detail(u))
@r.callback_query(F.data.startswith('ubalance:'))
async def ubalance(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_balance); await state.update_data(uid=int(q.data.split(':')[1])); await q.answer(); return await render_msg(q.message,q.from_user.id,'مبلغ تغییر موجودی را وارد کنید.\nمثال: <code>+50000</code> یا <code>-20000</code>',admin_back())
@r.message(S.admin_balance)
async def save_ubalance(m,state):
 if not await is_admin(m.from_user.id):return
 try:v=int(re.sub(r'[^0-9+-]','',m.text))
 except:return await m.answer('فقط عدد وارد کنید.')
 d=await state.get_data(); before=int(await db.scalar('SELECT balance FROM users WHERE id=?',(d['uid'],),0)); ok=await db.adjust_balance(d['uid'],v); after=int(await db.scalar('SELECT balance FROM users WHERE id=?',(d['uid'],),0));
 if ok: await db.execute('INSERT INTO audit(admin_id,action,target_id,details) VALUES(?,?,?,?)',(m.from_user.id,'balance_adjust',d['uid'],f'delta={v};before={before};after={after}'))
 await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,(f'<b>تغییر موجودی انجام شد</b>\n\nکاربر: <code>{d["uid"]}</code>\nتغییر: <b>{v:+,} تومان</b>\nموجودی قبلی: {before:,} تومان\nموجودی جدید: {after:,} تومان' if ok else 'عملیات انجام نشد؛ موجودی منفی نمی‌شود.'),admin_back())

async def set_kyc(uid,status,adminid,bot,notify=True):
 previous=await db.scalar('SELECT kyc_status FROM users WHERE id=?',(uid,),None)
 if previous==status:
  return False
 await db.execute("INSERT INTO kyc(user_id,status,reviewed_by,reviewed_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status,reviewed_by=excluded.reviewed_by,reviewed_at=CURRENT_TIMESTAMP",(uid,status,adminid))
 await db.execute('UPDATE users SET kyc_status=? WHERE id=?',(status,uid))
 if not notify: return True
 try:
  if status=='approved':
   text=(f'{pe("kyc_success","🙏")} <b>کاربر عزیز با تشکر از اعتماد شما</b>\n\n'
         f'{pe("kyc_success_text","🪪")} احراز هویت شما با موفیقت تایید شد اکنون میتوانید از کلیه امکانات ربات استفاده نمایید.\n\n'
         f'{pe("kyc_footer","🛡️")} <b>تیم پشتیبانی جت نامبر</b>')
  else:
   text='❌ احراز هویت شما رد شد. لطفاً برای بررسی مجدد با پشتیبانی در ارتباط باشید.'
  await bot.send_message(uid,text,parse_mode='HTML')
 except Exception as e:
  logging.warning('kyc notification failed for %s: %s',uid,e)
 return True
@r.callback_query(F.data.startswith('kycuser:'))
async def kycuser(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); u=await user(uid); return await render_msg(q.message,q.from_user.id,f'<b>🪪 احراز هویت</b>\n\nنام: {html.escape(u["first_name"] or "-")}\nUsername: @{html.escape(u["username"] or "-")}\n🆔 <code>{uid}</code>\n📱 {html.escape(u["phone"] or "-")}',kyc_detail(uid))
@r.callback_query(F.data.startswith('ukycok:'))
async def ukycok(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); changed=await set_kyc(uid,'approved',q.from_user.id,q.bot); await q.answer('تأیید شد.' if changed else 'این احراز قبلاً تأیید شده بود.'); u=await user(uid); return await render_msg(q.message,q.from_user.id,f'<b>وضعیت احراز هویت</b>\n\nآیدی: <code>{uid}</code>\nوضعیت فعلی: {u["kyc_status"]}',kyc_detail(uid) if u['kyc_status']!='approved' else InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به احراز هویت','admin:kyc','primary',IDS['lock'])]]))
@r.callback_query(F.data.startswith('ukycno:'))
async def ukycno(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); changed=await set_kyc(uid,'rejected',q.from_user.id,q.bot); await q.answer('رد شد.' if changed else 'این احراز قبلاً رد شده بود.'); u=await user(uid); return await render_msg(q.message,q.from_user.id,f'<b>وضعیت احراز هویت</b>\n\nآیدی: <code>{uid}</code>\nوضعیت فعلی: {u["kyc_status"]}',kyc_detail(uid))
@r.callback_query(F.data=='kycsearch')
async def kycsearch(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.user_search); await q.answer(); return await render_msg(q.message,q.from_user.id,'آیدی عددی یا @username کاربر را ارسال کنید.',admin_back())

@r.callback_query(F.data.startswith('adm:'))
async def adm_view(q):
 if not await admin_guard(q):return
 uid=int(q.data.split(':')[1]); x=await db.one('SELECT * FROM admins WHERE user_id=?',(uid,));
 if not x:return await q.answer('مدیر پیدا نشد.',show_alert=True)
 return await render_msg(q.message,q.from_user.id,f'<b>👨‍💼 مدیر</b>\n\n🆔 <code>{uid}</code>\nنقش: {x["role"]}\nدسترسی‌ها: {x["permissions"] or "خاموش"}',admin_detail(uid,bool(x['permissions'])))
@r.callback_query(F.data=='adm:add')
async def adm_add(q,state):
 if not is_owner(q.from_user.id):return await q.answer('فقط مالک می‌تواند مدیر اضافه کند.',show_alert=True)
 await state.set_state(S.admin_add); await q.answer(); return await render_msg(q.message,q.from_user.id,'آیدی عددی مدیر جدید را ارسال کنید.',admin_back())
@r.message(S.admin_add)
async def adm_add_save(m,state):
 if not is_owner(m.from_user.id):return
 if not m.text.isdigit():return await m.answer('آیدی عددی معتبر نیست.')
 uid=int(m.text)
 if is_owner(uid):return await m.answer('مالک دائمی قابل تغییر نیست.')
 await db.execute("INSERT INTO admins(user_id,role,permissions) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET permissions=excluded.permissions",(uid,'admin','all')); await state.clear()
 try: await m.bot.send_message(uid,'به جمع مدیران جت نامبر خوش آمدی')
 except: pass
 return await render(m.bot,m.from_user.id,m.chat.id,'✅ مدیر اضافه شد و دسترسی‌ها فعال شد.',admin_back())
@r.callback_query(F.data.startswith('adm_toggle:'))
async def adm_toggle(q):
 if not is_owner(q.from_user.id):return await q.answer('فقط مالک.',show_alert=True)
 uid=int(q.data.split(':')[1]); x=await db.one('SELECT * FROM admins WHERE user_id=?',(uid,));
 if not x:return await q.answer('پیدا نشد.',show_alert=True)
 await db.execute('UPDATE admins SET permissions=? WHERE user_id=?',('all' if not x['permissions'] else '',uid)); x=await db.one('SELECT * FROM admins WHERE user_id=?',(uid,)); return await render_msg(q.message,q.from_user.id,'<b>👨‍💼 مدیر</b>\n\n🆔 <code>'+str(uid)+'</code>\nدسترسی‌ها: '+(x['permissions'] or 'خاموش'),admin_detail(uid,bool(x['permissions'])))
@r.callback_query(F.data.startswith('adm_del:'))
async def adm_del(q):
 if not is_owner(q.from_user.id):return await q.answer('فقط مالک.',show_alert=True)
 uid=int(q.data.split(':')[1]);
 if is_owner(uid):return await q.answer('مالک دائمی قابل حذف نیست.',show_alert=True)
 await db.execute('DELETE FROM admins WHERE user_id=?',(uid,)); await q.answer('حذف شد.'); rows=await db.all('SELECT * FROM admins ORDER BY created_at DESC'); owner_text=f'👤 admin: <code>858897695</code>\n👑 مالک جت نامبر: <code>7048466991</code>'
 return await render_msg(q.message,q.from_user.id,f'<b>👨‍💼 مدیران</b>\n\n{owner_text}',admins_menu(rows))

@r.callback_query(F.data.startswith('toggle:'))
async def toggle(q):
 if not await admin_guard(q):return
 k=q.data.split(':')[1]; cur=await db.setting(k,'0'); await db.set_setting(k,'0' if cur=='1' else '1'); await q.answer('تغییر کرد.'); s=await settings_dict(['sales_enabled','second_panel_enabled','transfer_enabled','topup_enabled','min_topup','max_topup','kyc_required_above','default_markup']); return await render_msg(q.message,q.from_user.id,'<b>⚙️ تنظیمات عمومی</b>',settings_menu(s))
@r.callback_query(F.data.startswith('stoggle:'))
async def stoggle(q):
 if not await admin_guard(q):return
 k=q.data.split(':')[1]; cur=await db.setting(k,'0'); await db.set_setting(k,'0' if cur=='1' else '1'); await q.answer('تغییر کرد.'); s=await settings_dict(['sales_enabled','second_panel_enabled','transfer_enabled','topup_enabled','min_topup','max_topup','kyc_required_above','default_markup']); return await render_msg(q.message,q.from_user.id,'<b>⚙️ تنظیمات عمومی</b>',settings_menu(s))
@r.callback_query(F.data.startswith('set:'))
async def set_setting(q,state):
 if not await admin_guard(q):return
 key=q.data.split(':')[1]; cur=await db.setting(key,'0'); await q.answer(); return await render_msg(q.message,q.from_user.id,f'<b>تنظیم {key}</b>\n\nمقدار فعلی: <b>{int(cur or 0):,}</b>\nیکی از مقدارهای آماده را انتخاب کن یا مقدار دلخواه را بزن.',setting_presets(key,cur))
@r.callback_query(F.data.startswith('setpreset:'))
async def setpreset(q):
 if not await admin_guard(q):return
 _,key,value=q.data.split(':'); value=int(value)
 if key not in {'default_markup','kyc_required_above','min_topup','max_topup'}: return await q.answer('تنظیم نامعتبر است.',show_alert=True)
 await db.set_setting(key,value)
 await q.answer('تنظیم ذخیره شد.')
 s=await settings_dict(['sales_enabled','second_panel_enabled','transfer_enabled','topup_enabled','min_topup','max_topup','kyc_required_above','default_markup'])
 return await render_msg(q.message,q.from_user.id,'<b>تنظیمات عمومی</b>\nمقدار ذخیره شد.',settings_menu(s))
@r.callback_query(F.data.startswith('setcustom:'))
async def setcustom(q,state):
 if not await admin_guard(q):return
 key=q.data.split(':')[1]; await state.set_state(S.admin_setting); await state.update_data(setting_key=key); await q.answer()
 return await render_msg(q.message,q.from_user.id,'مقدار دلخواه را به تومان وارد کن؛ برای سقف احراز، مبلغی را وارد کن که از آن به بعد احراز لازم شود.',admin_back())
@r.message(S.admin_setting)
async def save_setting(m,state):
 if not await is_admin(m.from_user.id):return
 d=await state.get_data(); await db.set_setting(d['setting_key'],m.text.strip()); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'✅ ذخیره شد.',admin_back())

@r.callback_query(F.data.startswith('accttoggle:'))
async def accttoggle(q):
 if not await admin_guard(q):return
 k=q.data.split(':')[1]; cur=await db.setting(k,'0'); await db.set_setting(k,'0' if cur=='1' else '1'); s=await settings_dict(['topup_enabled','card_enabled','gateway_enabled','crypto_enabled']); return await render_msg(q.message,q.from_user.id,'<b>🧾 حسابداری</b>',accounting_menu(s))
@r.callback_query(F.data.startswith('acctset:'))
async def acctset(q,state):
 if not await admin_guard(q):return
 key=q.data.split(':')[1]; await state.set_state(S.account_setting); await state.update_data(setting_key=key); await q.answer(); prompt=('هر رمز ارز را در یک خط با قالب <code>SYMBOL | نام | آدرس کیف پول</code> وارد کن.\nمثال: <code>USDT-TRC20 | تتر TRC20 | Txxxxxxxx</code>\nبرای حذف یک ارز، خط آن را پاک کن.' if key=='crypto_wallets' else f'مقدار جدید <code>{html.escape(key)}</code> را ارسال کن.'); current=await db.setting(key,''); return await render_msg(q.message,q.from_user.id,prompt+(f'\n\nفعلی:\n<blockquote>{html.escape(current)}</blockquote>' if current else ''),InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت','admin:accounting','primary',IDS['lock'])]]))
@r.message(S.account_setting)
async def account_setting_save(m,state):
 if not await is_admin(m.from_user.id):return
 d=await state.get_data(); key=d.get('setting_key');
 if not key:return
 value=m.text.strip()
 if key=='crypto_wallets':
  parsed=[]
  for line in value.splitlines():
   parts=[x.strip() for x in line.split('|',2)]
   if len(parts)!=3 or not all(parts): return await m.answer('فرمت هر خط باید باشد: SYMBOL | نام | آدرس کیف پول')
   parsed.append(' | '.join(parts))
  value='\n'.join(parsed)
 await db.set_setting(key,value); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'تنظیمات ذخیره شد.',accounting_menu(await settings_dict(['topup_enabled','card_enabled','gateway_enabled','crypto_enabled'])))
@r.callback_query(F.data=='acct:gateway')
async def acct_gateway(q):
 if not await admin_guard(q):return
 status=f'App ID: {"تنظیم شده" if cfg.okaypay_id else "تنظیم نشده"}\nToken: {"تنظیم شده" if cfg.okaypay_token else "تنظیم نشده"}\n\nنرخ USDT: نوبیتکس\nنرخ TRX: CoinGecko\n\nکلیدها را فقط در فایل .env سرور وارد کن؛ از طریق چت ارسال نکن.'; return await render_msg(q.message,q.from_user.id,'<b>تنظیمات OkayPay</b>\n\n'+status,InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به حسابداری','admin:accounting','primary',IDS['lock'])]]))

@r.callback_query(F.data=='channel:add')
async def channel_add(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_channels); await q.answer(); return await render_msg(q.message,q.from_user.id,'آیدی یا @username کانال را ارسال کنید.',admin_back())
@r.message(S.admin_channels)
async def channel_save(m,state):
 if not await is_admin(m.from_user.id):return
 raw=await db.setting('force_join_channels',''); chans=[x for x in raw.splitlines() if x.strip()]; val=m.text.strip()
 if val not in chans: chans.append(val)
 await db.set_setting('force_join_channels','\n'.join(chans)); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'✅ کانال اضافه شد.',admin_back())
@r.callback_query(F.data.startswith('channel:del:'))
async def channel_del(q):
 if not await admin_guard(q):return
 i=int(q.data.split(':')[2]); chans=[x for x in (await db.setting('force_join_channels','')).splitlines() if x.strip()]
 if 0<=i<len(chans):chans.pop(i)
 await db.set_setting('force_join_channels','\n'.join(chans)); return await render_msg(q.message,q.from_user.id,'<b>📢 کانال‌های جوین اجباری</b>',channels_menu(chans))

async def refresh_pending_message(q):
 rows=await db.all("SELECT p.*,u.username,u.first_name FROM payments p LEFT JOIN users u ON u.id=p.user_id WHERE p.status='pending' ORDER BY p.id DESC LIMIT 30")
 text='<b>⏳ پرداخت‌های در انتظار تأیید</b>\n\n'+('\n'.join([f'#{x["id"]} | {x["amount"]:,} تومان | { {"card":"کارت‌به‌کارت","crypto":"کریپتو","gateway":"OkayPay"}.get(x["method"],x["method"])}\nکاربر: {html.escape(x["first_name"] or "-")} (@{html.escape(x["username"] or "ندارد")})\nآیدی: <code>{x["user_id"]}</code>' for x in rows]) or 'پرداخت معلقی وجود ندارد.')
 kb=[]
 for x in rows: kb.append([ib(f'تأیید #{x["id"]}',f'payok:{x["id"]}','success',IDS['add']),ib(f'رد #{x["id"]}',f'payno:{x["id"]}','danger',IDS['cancel'])])
 kb.append([ib('بازگشت','admin:reports','primary',IDS['lock'])])
 markup=InlineKeyboardMarkup(inline_keyboard=kb)
 # Accounting review posts can be photos with captions. Refresh them using the
 # correct Telegram edit method instead of silently leaving stale approve buttons.
 try:
  if q.message.photo or q.message.document:
   await q.message.edit_caption(caption=text,parse_mode='HTML',reply_markup=markup)
  else:
   await q.message.edit_text(text,parse_mode='HTML',reply_markup=markup)
 except Exception:
  try:
   plain=html.unescape(re.sub(r'<[^>]+>','',text))
   if q.message.photo or q.message.document:
    await q.message.edit_caption(caption=plain,reply_markup=markup)
   else:
    await q.message.edit_text(plain,reply_markup=markup)
  except Exception as e:
   logging.warning('Could not refresh accounting review message: %s',e)

async def close_review_message(q, status_text):
 # Remove review controls from the exact receipt that was approved/rejected.
 try:
  if q.message.photo or q.message.document:
   caption=q.message.caption or ''
   await q.message.edit_caption(caption=caption+'\n\n'+status_text,parse_mode='HTML',reply_markup=None)
  else:
   body=q.message.text or q.message.caption or ''
   await q.message.edit_text(body+'\n\n'+status_text,parse_mode='HTML',reply_markup=None)
 except Exception as e:
  try: await q.message.edit_reply_markup(reply_markup=None)
  except Exception: logging.warning('Could not close reviewed payment message: %s',e)

@r.callback_query(F.data.startswith('report:'))
async def report_view(q):
 if not await admin_guard(q):return
 typ=q.data.split(':')[1]
 if typ=='sales':
  rows=await db.all("SELECT o.*,u.first_name,u.username,c.name AS country_name FROM orders o LEFT JOIN users u ON u.id=o.user_id LEFT JOIN countries c ON c.iso=o.iso WHERE o.status='success' ORDER BY o.id DESC LIMIT 10")
  items=[]
  for x in rows:
   amount=max(0,int(x['sell_price'] or 0)-int(x.get('discount_amount') or 0))
   items.append(f'{pe("history_buy","🛒")} <b>فروش #{x["id"]}</b>\n{pe("users","👤")} {html.escape(x.get("first_name") or "کاربر")} · <code>{x["user_id"]}</code>\n{pe("country","🌍")} {html.escape(clean_country_name(x.get("country_name") or x["iso"]))} {flag_for(x["iso"])}\n{pe("delivery_phone","📱")} <code>{html.escape(x.get("phone") or "—")}</code>\n{pe("price","💰")} <b>{amount:,} تومان</b> · {html.escape(x.get("created_at") or "—")}')
  text=f'<b>{pe("history_buy","🛒")} گزارش فروش‌های موفق</b>\n\n'+('\n━━━━━━━━━━━━━━\n'.join(items) if items else 'هنوز فروش موفقی ثبت نشده است.')
 elif typ=='payments':
  rows=await db.all('SELECT p.*,u.first_name,u.username FROM payments p LEFT JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 10')
  methods_fa={'card':'کارت‌به‌کارت','crypto':'کریپتو','gateway':'OkayPay','gateway_usdt':'OkayPay · USDT','gateway_trx':'OkayPay · TRX','wallet':'کیف پول'}; statuses_fa={'pending':'در انتظار بررسی','approved':'تأیید شده','rejected':'رد شده','cancelled':'لغو شده'}
  items=[]
  for x in rows:
   icon='🟡' if x['status']=='pending' else ('🟢' if x['status']=='approved' else '🔴')
   items.append(f'{pe("invoice","🧾")} <b>پرداخت #{x["id"]}</b> · {statuses_fa.get(x["status"],x["status"])}\n{pe("users","👤")} {html.escape(x.get("first_name") or "کاربر")} · <code>{x["user_id"]}</code>\n{pe("pay_amount","💰")} <b>{int(x["amount"] or 0):,} تومان</b>\n{pe("online","💳")} {methods_fa.get(x["method"],x["method"])} · {html.escape(x.get("created_at") or "—")}')
  text=f'<b>{pe("history_topup","💳")} گزارش پرداخت‌ها</b>\n\n'+('\n━━━━━━━━━━━━━━\n'.join(items) if items else 'پرداختی ثبت نشده است.')
 elif typ=='users': text=f'<b>{pe("users","👥")} گزارش کاربران</b>\n\nکل کاربران: <b>{await db.scalar("SELECT COUNT(*) FROM users",(),0)}</b>\nاحراز شده: <b>{await db.scalar("SELECT COUNT(*) FROM users WHERE kyc_status='approved'",(),0)}</b>\nمسدود: <b>{await db.scalar("SELECT COUNT(*) FROM users WHERE banned=1",(),0)}</b>'
 elif typ=='countries':
  rows=await db.all("SELECT c.iso,c.name,COUNT(o.id) n,COALESCE(SUM(o.sell_price-o.discount_amount),0) total FROM countries c LEFT JOIN orders o ON o.iso=c.iso AND o.status='success' GROUP BY c.iso ORDER BY n DESC,c.name LIMIT 30")
  text='<b>گزارش فروش کشورها</b>\n\n'+('\n'.join([f'{flag_for(x["iso"])} <b>{html.escape(x["name"])}</b> · {x["n"]} فروش · {int(x["total"] or 0):,} تومان' for x in rows]) or 'اطلاعاتی وجود ندارد.')
 elif typ=='balances':
  rows=await db.all('SELECT id,first_name,balance FROM users WHERE balance>0 ORDER BY balance DESC LIMIT 20')
  text='<b>گزارش موجودی کاربران</b>\n\n'+('\n'.join([f'{i+1}. {html.escape(x["first_name"] or "کاربر")} · <code>{x["id"]}</code> · <b>{x["balance"]:,} تومان</b>' for i,x in enumerate(rows)]) or 'موجودی مثبتی ثبت نشده است.')
 elif typ=='pending':
  rows=await db.all("SELECT p.*,u.username,u.first_name FROM payments p LEFT JOIN users u ON u.id=p.user_id WHERE p.status='pending' ORDER BY p.id DESC LIMIT 20")
  items=[]
  for x in rows: items.append(f'<b>پرداخت #{x["id"]}</b> · {int(x["amount"] or 0):,} تومان\nکاربر: {html.escape(x.get("first_name") or "—")} · <code>{x["user_id"]}</code>\nروش: { {"card":"کارت‌به‌کارت","crypto":"کریپتو","gateway":"OkayPay"}.get(x["method"],x["method"])}')
  text='<b>پرداخت‌های در انتظار بررسی</b>\n\n'+('\n━━━━━━━━━━━━━━\n'.join(items) if items else 'پرداخت معلقی وجود ندارد.')
  kb=[]
  for x in rows: kb.append([ib(f'تأیید پرداخت #{x["id"]}',f'payok:{x["id"]}','success',IDS['add']),ib(f'رد پرداخت #{x["id"]}',f'payno:{x["id"]}','danger',IDS['cancel'])])
  kb.append([ib('بازگشت به گزارش‌ها','admin:reports','primary',IDS['lock'])]); return await render_msg(q.message,q.from_user.id,text,InlineKeyboardMarkup(inline_keyboard=kb))
 else:
  users=await db.scalar('SELECT COUNT(*) FROM users',(),0); sales=await db.scalar("SELECT COUNT(*) FROM orders WHERE status='success'",(),0); revenue=await db.scalar("SELECT COALESCE(SUM(sell_price-COALESCE(discount_amount,0)),0) FROM orders WHERE status='success'",(),0); deposits=await db.scalar("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved' AND purpose='topup'",(),0); pending=await db.scalar("SELECT COUNT(*) FROM payments WHERE status='pending'",(),0)
  text=f'<b>گزارش مالی کامل</b>\n\nکاربران: <b>{users:,}</b>\nفروش موفق: <b>{sales:,}</b>\nدرآمد فروش: <b>{revenue:,} تومان</b>\nشارژ تأییدشده: <b>{deposits:,} تومان</b>\nپرداخت در انتظار: <b>{pending:,}</b>'
 return await render_msg(q.message,q.from_user.id,text,InlineKeyboardMarkup(inline_keyboard=[[ib('به‌روزرسانی','report:'+typ,'primary',IDS['reports'])],[ib('بازگشت به گزارش‌ها','admin:reports','primary',IDS['lock'])]]))

@r.callback_query(F.data.startswith('payok:'))
async def payok(q):
 if not await admin_guard(q):return
 pid=int(q.data.split(':')[1]); p=await db.one("SELECT * FROM payments WHERE id=? AND status='pending'",(pid,))
 if not p:return await q.answer('قبلاً بررسی شده.',show_alert=True)
 if p['purpose']=='topup':
  claimed=await db.approve_topup_payment(pid,q.from_user.id)
  if not claimed:return await q.answer('این پرداخت قبلاً بررسی شده است.',show_alert=True)
  await db.execute('INSERT INTO audit(admin_id,action,target_id,details) VALUES(?,?,?,?)',(q.from_user.id,'payment_approved',p['user_id'],f'payment={pid};amount={p["amount"]}')); msg=f'{p["amount"]:,} تومان به موجودی شما اضافه شد.'
  try: await q.bot.send_message(p['user_id'],msg,parse_mode='HTML')
  except: pass
 else:
  ok,phone=await fulfill_order(p['user_id'],p['order_id'],q.bot)
  if not ok:return await q.answer('دریافت شماره از API ناموفق بود؛ پرداخت تأیید نشد.',show_alert=True)
  await db.execute("UPDATE payments SET status='approved',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",(q.from_user.id,pid))
  await db.execute("UPDATE payments SET status='cancelled' WHERE order_id=? AND id<>? AND status='pending'",(p['order_id'],pid))
  o=await db.one('SELECT o.*,c.name FROM orders o LEFT JOIN countries c ON c.iso=o.iso WHERE o.id=?',(p['order_id'],))
  try: await q.bot.send_message(p['user_id'],delivery_text(int(p['order_id']),o,phone),parse_mode='HTML',reply_markup=order_ready_actions(int(p['order_id']),phone))
  except Exception as e: logging.warning('deliver message failed: %s',e)
 await close_review_message(q, '✅ <b>پرداخت تأیید شد</b>')
 await refresh_pending_message(q); return await q.answer('پرداخت تأیید شد')
@r.callback_query(F.data.startswith('payno:'))
async def payno(q):
 if not await admin_guard(q):return
 pid=int(q.data.split(':')[1]); p=await db.one("SELECT * FROM payments WHERE id=? AND status='pending'",(pid,));
 if not p:return await q.answer('قبلاً بررسی شده.',show_alert=True)
 await db.execute("UPDATE payments SET status='rejected',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(q.from_user.id,pid));
 try: await q.bot.send_message(p['user_id'],t(await language(p['user_id']) or 'fa','payment_rejected'))
 except:pass
 await close_review_message(q, '❌ <b>پرداخت رد شد</b>')
 await refresh_pending_message(q); return await q.answer('پرداخت رد شد')
@r.callback_query(F.data.startswith('payedit:'))
async def payedit(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_payment_edit); await state.update_data(payment_edit=int(q.data.split(':')[1])); await q.answer(); return await render_msg(q.message,q.from_user.id,'مبلغ صحیح را به تومان ارسال کنید.',admin_back())
@r.message(S.admin_payment_edit)
async def payedit_save(m,state):
 if not await is_admin(m.from_user.id):return
 try:v=int(re.sub(r'[^0-9]','',m.text))
 except:return await m.answer('فقط عدد وارد کنید.')
 d=await state.get_data(); await db.execute("UPDATE payments SET amount=? WHERE id=? AND status='pending'",(max(0,v),d['payment_edit'])); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'✅ مبلغ اصلاح شد.',admin_back())

@r.callback_query(F.data=='coupon:add')
async def coupon_add(q,state):
 if not await admin_guard(q):return
 await state.set_state(S.admin_coupon); await q.answer(); return await render_msg(q.message,q.from_user.id,'فرمت: <code>CODE درصد حداکثر_استفاده</code>\nمثال: <code>KING10 10 100</code>',admin_back())

@r.message(S.admin_coupon)
async def coupon_save(m,state):
 if not await is_admin(m.from_user.id):return
 p=m.text.split()
 if len(p)!=3:return await m.answer('فرمت: CODE درصد حداکثر_استفاده')
 try: code,val,maxu=p[0].upper(),int(p[1]),int(p[2])
 except:return await m.answer('عدد نامعتبر است.')
 if not (0<=val<=100):return await m.answer('درصد باید بین 0 تا 100 باشد.')
 await db.execute('INSERT INTO coupons(code,kind,value,max_uses,enabled) VALUES(?,?,?,?,1) ON CONFLICT(code) DO UPDATE SET value=excluded.value,max_uses=excluded.max_uses,enabled=1',(code,'percent',val,maxu)); await state.clear(); return await render(m.bot,m.from_user.id,m.chat.id,'✅ کد تخفیف ذخیره شد.',admin_back())

@r.callback_query(F.data.startswith('coupon:toggle:'))
async def coupon_toggle(q):
 if not await admin_guard(q):return
 code=q.data.split(':',2)[2]; x=await db.one('SELECT * FROM coupons WHERE code=?',(code,))
 if not x:return await q.answer('کد پیدا نشد.',show_alert=True)
 await db.execute('UPDATE coupons SET enabled=? WHERE code=?',(0 if x['enabled'] else 1,code)); await q.answer('وضعیت تغییر کرد.')
 rows=await db.all('SELECT * FROM coupons ORDER BY created_at DESC LIMIT 50')
 kb=[[ib(f'{"🟢" if y["enabled"] else "🔴"} {y["code"]} | {y["value"]}%',f'coupon:toggle:{y["code"]}','success' if y['enabled'] else 'danger',IDS['add'])] for y in rows]
 kb += [[ib('➕ ساخت/ویرایش کد','coupon:add','success',IDS['add'])],[ib('🔙 بازگشت','admin:home','primary',IDS['lock'])]]
 return await render_msg(q.message,q.from_user.id,'<b>🎟️ کد تخفیف</b>',InlineKeyboardMarkup(inline_keyboard=kb))

@r.callback_query()
async def callback_fallback(q):
 data=q.data or ''
 logging.warning('Unhandled callback: %s from %s', data, q.from_user.id)
 await q.answer('این گزینه هنوز فعال نشده است.', show_alert=True)

async def hourly_accounting_report_loop(bot):
 while True:
  try:
   if await db.setting('hourly_report_enabled','1')=='1':
    now=datetime.now(); key=now.strftime('%Y-%m-%d-%H')
    last=await db.setting('hourly_report_last','')
    if last!=key:
     gid=await db.setting('accounting_group_id','-1004413050883')
     if gid:
      rows=await db.all("SELECT status,COUNT(*) AS n,COALESCE(SUM(amount),0) AS total FROM payments WHERE receipt_file_id IS NOT NULL AND created_at>=datetime('now','-1 hour') GROUP BY status")
      pending=await db.scalar("SELECT COUNT(*) FROM payments WHERE receipt_file_id IS NOT NULL AND status='pending' AND created_at>=datetime('now','-1 hour')",(),0)
      all_count=sum(int(x['n'] or 0) for x in rows); total=sum(int(x['total'] or 0) for x in rows)
      lines='\n'.join(f'• { {"pending":"در انتظار بررسی","approved":"تأییدشده","rejected":"ردشده"}.get(x["status"],x["status"])}: {int(x["n"]):,} مورد · {int(x["total"]):,} تومان' for x in rows) or 'در یک ساعت گذشته پرداختی ثبت نشده است.'
      msg=(f'<b>گزارش ساعتی حسابداری جت نامبر</b>\n'
           f'بازه: {now.strftime("%Y-%m-%d %H:00")} تا {now.strftime("%H:59")}\n\n'
           f'تعداد رسیدها: <b>{all_count:,}</b>\nرسیدهای در انتظار: <b>{int(pending):,}</b>\n'
           f'جمع مبالغ ثبت‌شده: <b>{total:,} تومان</b>\n\n{lines}')
      await safe_send(bot,int(gid) if str(gid).lstrip('-').isdigit() else gid,msg)
      await db.set_setting('hourly_report_last',key)
  except Exception as e:
   logging.warning('hourly accounting report failed: %s',e)
   try: await notify_admin_error(bot,'گزارش ساعتی حسابداری',e)
   except Exception: pass
  await asyncio.sleep(30)

async def startup(bot=None):
 await db.init()
 try: await sync_countries()
 except Exception as e:
  logging.warning('initial sync failed: %s',e)
  if bot:
   try: await notify_admin_error(bot,'همگام‌سازی اولیه کشورها / API',e)
   except Exception: pass
async def main():
 if not cfg.bot_token: raise RuntimeError('BOT_TOKEN is missing')
 bot=Bot(cfg.bot_token); await startup(bot); dp=Dispatcher(); dp.include_router(r); sync_task=asyncio.create_task(sync_loop(bot)); okaypay_task=asyncio.create_task(okaypay_poll_loop(bot)); accounting_task=asyncio.create_task(hourly_accounting_report_loop(bot))
 try: await dp.start_polling(bot)
 finally: sync_task.cancel(); okaypay_task.cancel(); accounting_task.cancel()
if __name__=='__main__': asyncio.run(main())
