from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton,ReplyKeyboardMarkup,KeyboardButton,CopyTextButton
import unicodedata
from jn_emoji import IDS
from jn_i18n import LANGS,t

def ib(text,data=None,style='primary',icon=None,url=None):
 kw={'text':text,'style':style}
 if data is not None: kw['callback_data']=data
 if url: kw['url']=url
 if icon: kw['icon_custom_emoji_id']=icon
 return InlineKeyboardButton(**kw)
def label(text):
 for i,ch in enumerate(text):
  if unicodedata.category(ch)[0] in ('L','N'):
   return text[i:].strip()
 return text
def rb(text,style='primary',icon=None):
 kw={'text':label(text),'style':style}
 if icon: kw['icon_custom_emoji_id']=icon
 return KeyboardButton(**kw)
def main(lang,admin=False):
 rows=[[rb(t(lang,'buy'),'primary',IDS['buy']),rb(t(lang,'buy2'),'primary',IDS['buy'])],[rb(t(lang,'wallet'),'primary',IDS['topup']),rb(t(lang,'account'),'primary',IDS['account'])],[rb(t(lang,'guide'),'primary',IDS['guide']),rb(t(lang,'help'),'primary',IDS['help'])],[rb(t(lang,'support'),'primary',IDS['support']),rb(t(lang,'prices'),'primary',IDS['invoice'])],[rb(t(lang,'session'),'primary',IDS['support'])],[rb(t(lang,'lang'),'primary',IDS['field'])]]
 if admin: rows.append([rb(t(lang,'admin'),'danger',IDS['shield'])])
 return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)
def langs():
 items=list(LANGS.items()); return InlineKeyboardMarkup(inline_keyboard=[[ib(items[i][1],f'lang:{items[i][0]}'),ib(items[i+1][1],f'lang:{items[i+1][0]}')] if i+1<len(items) else [ib(items[i][1],f'lang:{items[i][0]}')] for i in range(0,len(items),2)])
def back(data='home',lang='fa'): return InlineKeyboardMarkup(inline_keyboard=[[ib(t(lang,'back'),data,'primary',IDS['lock'])]])
def wallet(lang): return InlineKeyboardMarkup(inline_keyboard=[[ib(t(lang,'topup'),'wallet:add','success',IDS['add']),ib(t(lang,'transfer'),'wallet:transfer','primary',IDS['transfer'])],[ib(t(lang,'back'),'home','primary',IDS['lock'])]])
def account(lang,verified=False,has_phone=False):
 rows=[]
 if not verified: rows.append([ib(t(lang,'kyc'),'menu:kyc','primary',IDS['kyc'])])
 if not has_phone: rows.append([ib(t(lang,'send_phone'),'phone:send','primary',IDS['field'])])
 rows.append([ib(t(lang,'back'),'home','primary',IDS['lock'])])
 rows.append([ib('تاریخچه افزایش موجودی','hist:topup','primary',IDS['history_topup']),ib('تاریخچه خرید','hist:buy','primary',IDS['history_buy'])])
 return InlineKeyboardMarkup(inline_keyboard=rows)
def contact(lang='fa'):
 return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(lang,'send_phone'),request_contact=True,style='primary',icon_custom_emoji_id=IDS['field'])],[KeyboardButton(text=t(lang,'back'),style='primary',icon_custom_emoji_id=IDS['lock'])]],resize_keyboard=True,one_time_keyboard=True)
def countries(rows,lang,prefix='country'):
 kb=[]
 for x in rows:
  flag=flag_for(x['iso']); ok=int(x['enabled'])==1 and int(x['api_count'])>0; style='success' if ok else 'danger'
  kb.append([ib(f'{x["name"]} {flag}',f'{prefix}:{x["iso"]}',style,IDS['country']),ib(f'{int(x["sell_price"]):,}',f'{prefix}:{x["iso"]}',style,IDS['price']),ib(f'{int(x["api_count"]):,}',f'{prefix}:{x["iso"]}',style,IDS['add'] if ok else IDS['lock'])])
 kb.append([ib(t(lang,'back'),'home','primary',IDS['lock'])]); return InlineKeyboardMarkup(inline_keyboard=kb)
def invoice(oid,lang): return InlineKeyboardMarkup(inline_keyboard=[[ib('🎟️ افزودن کد تخفیف',f'coupon:order:{oid}','primary','6003771449767107159')],[ib('💳 پرداخت و دریافت شماره',f'invoice:pay:{oid}','success','6003364252507709759')],[ib('لغو خرید',f'invoice:cancel:{oid}','danger','6006044243380935382')]])
def order_payment(oid,lang,methods):
 rows=[[ib('💰 پرداخت با کیف پول',f'orderpay:wallet:{oid}','success','5769403330761593044')]]
 if methods.get('card'): rows.append([ib('💳 پرداخت کارت به کارت',f'orderpay:card:{oid}','primary','5927169041595634481')])
 if methods.get('crypto'): rows.append([ib('💎 پرداخت با کریپتو',f'orderpay:crypto:{oid}','primary','5992430854909989581')])
 if methods.get('gateway'): rows.append([ib('OkayPay · USDT',f'orderpay:okaypay_usdt:{oid}','success','4915937975507879321'),ib('OkayPay · TRX',f'orderpay:okaypay_trx:{oid}','primary','4915937975507879321')])
 rows.append([ib('🔙 بازگشت به فاکتور',f'invoice:back:{oid}','primary',IDS['lock'])])
 return InlineKeyboardMarkup(inline_keyboard=rows)
def order_ready_actions(oid,phone):
 return InlineKeyboardMarkup(inline_keyboard=[[ib('دریافت کد تایید',f'code:{oid}','success','5884510167986343350')],[ib('لغو سفارش',f'cancel:ask:{oid}','danger','5872829476143894491'),InlineKeyboardButton(text='کپی شماره',copy_text=CopyTextButton(text=phone),style='primary',icon_custom_emoji_id='5915993536691442745')]])
def code_wait_actions(oid): return InlineKeyboardMarkup(inline_keyboard=[[ib('دریافت کد تایید',f'code:{oid}','success','5884510167986343350')],[ib('خروج ربات از اکانت',f'logout:{oid}','primary','5931415565955503486')]])
def code_actions(oid,code):
 return InlineKeyboardMarkup(inline_keyboard=[[ib('دریافت کد تایید',f'code:{oid}','success','5884510167986343350')],[ib('خروج ربات از اکانت',f'logout:{oid}','primary','5931415565955503486'),InlineKeyboardButton(text='کپی کد تایید',copy_text=CopyTextButton(text=code),style='primary',icon_custom_emoji_id='5915993536691442745')]])
def cancel_confirm(oid):
 return InlineKeyboardMarkup(inline_keyboard=[[ib('تأیید لغو سفارش',f'cancel:confirm:{oid}','danger','5872829476143894491')],[ib('بازگشت به سفارش',f'cancel:back:{oid}','primary',IDS['lock'])]])
def payment_methods(lang,methods,backdata='home'):
 rows=[]
 if methods.get('card'): rows.append([ib(t(lang,'card'),'paymethod:card','primary',IDS['toman'])])
 if methods.get('gateway'): rows.append([ib('پرداخت با OkayPay','paymethod:gateway','primary','4915937975507879321')])
 if methods.get('crypto'): rows.append([ib(t(lang,'crypto'),'paymethod:crypto','success',IDS['ton'])])
 rows.append([ib(t(lang,'back'),backdata,'primary',IDS['lock'])]); return InlineKeyboardMarkup(inline_keyboard=rows)
def order_actions(oid,lang): return InlineKeyboardMarkup(inline_keyboard=[[ib(t(lang,'code'),f'code:{oid}','success',IDS['add']),ib(t(lang,'logout'),f'logout:{oid}','primary',IDS['lock'])],[ib(t(lang,'order_cancel'),f'cancel:{oid}','danger',IDS['cancel'])]])
def help_menu(lang): return InlineKeyboardMarkup(inline_keyboard=[[ib('سوالات متداول','help:faq','primary',IDS['help']),ib('قوانین استفاده','help:rules','primary',IDS['rules'])],[ib('کاربرد شماره مجازی','help:usage','primary',IDS['field']),ib('درباره ربات','help:about','primary',IDS['field'])],[ib('رفع ریپورت','help:unreport','primary',IDS['lock'])],[ib(t(lang,'back'),'home','primary',IDS['lock'])]])
def admin_menu():
 return InlineKeyboardMarkup(inline_keyboard=[[ib('داشبورد','admin:dash','primary',IDS['balance']),ib('گزارش‌ها','admin:reports','primary',IDS['reports'])],[ib('محصولات','admin:products','primary',IDS['invoice']),ib('کشورها','admin:countries','primary',IDS['country'])],[ib('کاربران','admin:users','primary',IDS['users']),ib('حسابداری','admin:accounting','primary',IDS['toman'])],[ib('احراز هویت','admin:kyc','primary',IDS['verify']),ib('مدیران','admin:admins','primary',IDS['admins'])],[ib('جوین اجباری','admin:channels','primary',IDS['channels']),ib('تنظیمات','admin:settings','primary',IDS['settings'])],[ib('کد تخفیف','admin:coupon','primary',IDS['add']),ib('همگام‌سازی API','admin:sync','primary',IDS['country'])],[ib('منوی اصلی','home','primary',IDS['lock'])]])
def admin_back(): return InlineKeyboardMarkup(inline_keyboard=[[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]])
def dashboard_menu(): return InlineKeyboardMarkup(inline_keyboard=[[ib('مدیریت کاربران','admin:users','primary',IDS['users']),ib('پرداخت‌های در انتظار','report:pending','primary',IDS['invoice'])],[ib('گزارش فروش','report:sales','primary',IDS['history_buy']),ib('گزارش پرداخت','report:payments','primary',IDS['history_topup'])],[ib('حسابداری','admin:accounting','primary',IDS['toman']),ib('کشورها و قیمت‌ها','admin:countries','primary',IDS['country'])],[ib('به‌روزرسانی آمار','admin:dash','success',IDS['reports'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]])
def admin_countries(rows):
 kb=[]
 for x in rows:
  on=int(x['enabled']); stock=int(x['api_count']); status='فعال' if on and stock else ('خاموش' if not on else 'بدون موجودی')
  kb.append([ib(f'{x["name"]} · {x["iso"]} · {x["sell_price"]:,} تومان · موجودی {stock:,} · {status}',f'acountry:{x["iso"]}','success' if on and stock>0 else 'danger',IDS['country'])])
 kb += [[ib('همگام‌سازی از API','admin:sync','primary',IDS['country'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]]; return InlineKeyboardMarkup(inline_keyboard=kb)
def country_edit(x):
 status='غیرفعال کردن' if x['enabled'] else 'فعال کردن'
 return InlineKeyboardMarkup(inline_keyboard=[[ib(status,'country_toggle:'+x['iso'],'danger' if x['enabled'] else 'success',IDS['country'])],[ib('ویرایش قیمت فروش','prod_sell:'+x['iso'],'primary',IDS['price']),ib('ویرایش قیمت خرید','prod_buy:'+x['iso'],'primary',IDS['toman'])],[ib('تنظیم مارکاپ کشور','country_markup:'+x['iso'],'primary',IDS['balance'])],[ib('بازگشت به کشورها','admin:countries','primary',IDS['lock'])]])
def admin_products(rows):
 kb=[]
 for x in rows: kb.append([ib(f'{x["name"]} · {x["iso"]} · خرید {x["api_price"]:,} · فروش {x["sell_price"]:,}',f'prod:{x["iso"]}','success' if x['enabled'] else 'danger',IDS['invoice'])])
 kb += [[ib('افزایش گروهی','pricebulk:+','success',IDS['add']),ib('کاهش گروهی','pricebulk:-','danger',IDS['cancel'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]]; return InlineKeyboardMarkup(inline_keyboard=kb)
def product_edit(x): return InlineKeyboardMarkup(inline_keyboard=[[ib('فعال' if x['enabled'] else 'خاموش',f'prod_toggle:{x["iso"]}','success' if x['enabled'] else 'danger',IDS['country'])],[ib('قیمت خرید','prod_buy:'+x['iso'],'primary',IDS['toman']),ib('قیمت فروش','prod_sell:'+x['iso'],'primary',IDS['price'])],[ib('بازگشت به محصولات','admin:products','primary',IDS['lock'])]])
def bulk_presets(sign):
 rows=[]
 for amount,label in [('1000','۱٬۰۰۰'),('5000','۵٬۰۰۰'),('10000','۱۰٬۰۰۰'),('50000','۵۰٬۰۰۰')]: rows.append([ib(('افزایش ' if sign=='+' else 'کاهش ')+label+' تومان',f'pricebulk_apply:{sign}:{amount}','success' if sign=='+' else 'danger',IDS['add'] if sign=='+' else IDS['cancel'])])
 for pct in ('5','10','20'): rows.append([ib(('افزایش ' if sign=='+' else 'کاهش ')+pct+'٪',f'pricebulk_apply:{sign}:{pct}p','success' if sign=='+' else 'danger',IDS['price'])])
 rows += [[ib('مقدار دلخواه','pricebulk_custom:'+sign,'primary',IDS['settings'])],[ib('بازگشت به محصولات','admin:products','primary',IDS['lock'])]]
 return InlineKeyboardMarkup(inline_keyboard=rows)
def reports_menu(): return InlineKeyboardMarkup(inline_keyboard=[[ib('فروش‌ها','report:sales','primary',IDS['history_buy']),ib('پرداخت‌ها','report:payments','primary',IDS['history_topup'])],[ib('کاربران','report:users','primary',IDS['users']),ib('فروش کشورها','report:countries','primary',IDS['country'])],[ib('موجودی‌ها','report:balances','primary',IDS['balance']),ib('در انتظار بررسی','report:pending','primary',IDS['invoice'])],[ib('گزارش مالی کامل','report:all','success',IDS['reports'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]])
def toggle_button(k,label,s,icon): return ib(('فعال · ' if s.get(k)=='1' else 'خاموش · ')+label,f'toggle:{k}','success' if s.get(k)=='1' else 'danger',icon)
def accounting_menu(s): return InlineKeyboardMarkup(inline_keyboard=[[ib(('فعال · ' if s.get('topup_enabled')=='1' else 'خاموش · ')+'شارژ کیف پول','accttoggle:topup_enabled','success' if s.get('topup_enabled')=='1' else 'danger',IDS['wallet']),ib(('فعال · ' if s.get('card_enabled')=='1' else 'خاموش · ')+'کارت‌به‌کارت','accttoggle:card_enabled','success' if s.get('card_enabled')=='1' else 'danger',IDS['toman'])],[ib(('فعال · ' if s.get('gateway_enabled')=='1' else 'خاموش · ')+'OkayPay','accttoggle:gateway_enabled','success' if s.get('gateway_enabled')=='1' else 'danger',IDS['online']),ib(('فعال · ' if s.get('crypto_enabled')=='1' else 'خاموش · ')+'کریپتو','accttoggle:crypto_enabled','success' if s.get('crypto_enabled')=='1' else 'danger',IDS['ton'])],[ib('شماره کارت','acctset:card_number','primary',IDS['toman']),ib('صاحب کارت','acctset:card_owner','primary',IDS['account'])],[ib('کیف TON','acctset:ton_wallet','primary',IDS['ton']),ib('کیف TRON','acctset:tron_wallet','primary',IDS['tron'])],[ib('مدیریت کیف‌پول‌های بیشتر','acctset:crypto_wallets','primary',IDS['ton'])],[ib('گروه حسابداری','acctset:accounting_group_id','primary',IDS['users']),ib('کانال گزارش فروش','acctset:report_channel_id','primary',IDS['reports'])],[ib('کانال خصوصی آرشیو احراز','acctset:kyc_archive_channel_id','primary',IDS['verify'])],[ib('تنظیمات درگاه','acct:gateway','primary',IDS['online'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]])
def settings_menu(s): return InlineKeyboardMarkup(inline_keyboard=[[toggle_button('sales_enabled','فروش',s,IDS['buy']),toggle_button('second_panel_enabled','پنل دوم',s,IDS['buy'])],[toggle_button('transfer_enabled','انتقال موجودی',s,IDS['transfer']),toggle_button('topup_enabled','شارژ',s,IDS['wallet'])],[ib(f"حداقل شارژ · {int(s.get('min_topup','0')):,}",'set:min_topup','primary',IDS['toman']),ib(f"حداکثر شارژ · {int(s.get('max_topup','0')):,}",'set:max_topup','primary',IDS['toman'])],[ib(f"سقف احراز · {int(s.get('kyc_required_above','0')):,}",'set:kyc_required_above','primary',IDS['kyc']),ib(f"مارکاپ · {int(s.get('default_markup','0')):,}",'set:default_markup','primary',IDS['price'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]])
def setting_presets(key,current):
 opts={'default_markup':[0,1000,5000,10000,20000,50000],'kyc_required_above':[0,500,1000,5000,10000,50000],'min_topup':[0,1000,5000,10000,50000,100000],'max_topup':[0,50000,100000,500000,1000000,5000000]}
 labels={'default_markup':'مارکاپ پیش‌فرض','kyc_required_above':'سقف احراز هویت','min_topup':'حداقل شارژ','max_topup':'حداکثر شارژ'}
 rows=[]; values=opts.get(key,[])
 for i in range(0,len(values),2): rows.append([ib(f'{values[i]:,} تومان'+(' ✓' if str(values[i])==str(current) else ''),f'setpreset:{key}:{values[i]}','success' if str(values[i])==str(current) else 'primary',IDS['price']),ib(f'{values[i+1]:,} تومان'+(' ✓' if str(values[i+1])==str(current) else ''),f'setpreset:{key}:{values[i+1]}','success' if str(values[i+1])==str(current) else 'primary',IDS['price'])])
 rows += [[ib('مقدار دلخواه','setcustom:'+key,'primary',IDS['settings'])],[ib('بازگشت به تنظیمات','admin:settings','primary',IDS['lock'])]]
 return InlineKeyboardMarkup(inline_keyboard=rows)
def channels_menu(chans):
 rows=[[ib('افزودن کانال','channel:add','success',IDS['add'])]]
 for i,c in enumerate(chans): rows.append([ib(c,f'channel:del:{i}','danger',IDS['cancel'])])
 rows.append([ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]); return InlineKeyboardMarkup(inline_keyboard=rows)
def admins_menu(rows):
 kb=[]
 for x in rows: kb.append([ib(f'{x["user_id"]} · {x["role"]} · {"فعال" if x["permissions"] else "خاموش"}',f'adm:{x["user_id"]}','primary',IDS['admins'])])
 kb += [[ib('افزودن مدیر','adm:add','success',IDS['add'])],[ib('بازگشت به پنل','admin:home','primary',IDS['lock'])]]; return InlineKeyboardMarkup(inline_keyboard=kb)
def admin_detail(uid,enabled): return InlineKeyboardMarkup(inline_keyboard=[[ib('دسترسی‌ها فعال' if enabled else 'دسترسی‌ها خاموش',f'adm_toggle:{uid}','success' if enabled else 'danger',IDS['admins'])],[ib('حذف مدیر',f'adm_del:{uid}','danger',IDS['cancel'])],[ib('بازگشت به مدیران','admin:admins','primary',IDS['lock'])]])
def user_detail(u): return InlineKeyboardMarkup(inline_keyboard=[[ib('تغییر موجودی',f'ubalance:{u["id"]}','primary',IDS['balance']),ib('رفع مسدودی' if u['banned'] else 'مسدودسازی',f'uban:{u["id"]}','danger',IDS['cancel'])],[ib('تأیید احراز',f'ukycok:{u["id"]}','success',IDS['verify']),ib('رد احراز',f'ukycno:{u["id"]}','danger',IDS['cancel'])],[ib('بازگشت به کاربران','admin:users','primary',IDS['lock'])]])
def kyc_detail(uid): return InlineKeyboardMarkup(inline_keyboard=[[ib('تأیید احراز',f'ukycok:{uid}','success',IDS['verify']),ib('رد احراز',f'ukycno:{uid}','danger',IDS['cancel'])],[ib('بازگشت به احراز هویت','admin:kyc','primary',IDS['lock'])]])
def flag_for(iso):
 iso=(iso or '').upper(); return ''.join(chr(127397+ord(c)) for c in iso) if len(iso)==2 and iso.isalpha() else '🌐'
