import hashlib, hmac, time, secrets, json
from decimal import Decimal, ROUND_UP
from urllib.parse import urlencode
import aiohttp

BASE = 'https://api.okaypay.me'

class OkayPayError(RuntimeError):
    pass

def _flat(obj, prefix=''):
    out={}
    if isinstance(obj, dict):
        for k,v in obj.items():
            key=f'{prefix}.{k}' if prefix else str(k)
            if isinstance(v,dict): out.update(_flat(v,key))
            elif v is None or v=='': continue
            elif isinstance(v,bool): out[key]='true' if v else 'false'
            else: out[key]=str(v)
    else: out[prefix]=str(obj)
    return out

def signature(payload, token):
    clean={k:v for k,v in _flat(payload).items() if k!='sign' and v is not None and v!=''}
    base='&'.join(f'{k}={clean[k]}' for k in sorted(clean))
    return hmac.new(token.encode(),base.encode(),hashlib.sha256).hexdigest().upper()

def verify(payload, token):
    got=payload.get('sign') if isinstance(payload,dict) else None
    return isinstance(got,str) and hmac.compare_digest(got.upper(),signature({k:v for k,v in payload.items() if k!='sign'},token))

class OkayPay:
    def __init__(self, app_id, token): self.app_id=app_id.strip(); self.token=token.strip()
    async def post(self,path,fields):
        if not self.app_id or not self.token: raise OkayPayError('OkayPay App ID/Token تنظیم نشده است')
        payload={'id':self.app_id,'timestamp':str(int(time.time())),'nonce':secrets.token_urlsafe(16),**fields}
        payload['sign']=signature(payload,self.token)
        timeout=aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BASE+path,data=payload,headers={'Accept':'application/json'}) as response:
                body=await response.text()
                try: data=json.loads(body)
                except Exception: raise OkayPayError(f'پاسخ نامعتبر از OkayPay (HTTP {response.status})')
                if response.status>=400 or not isinstance(data,dict): raise OkayPayError(f'خطای HTTP از OkayPay: {response.status}')
                if data.get('status')!='success': raise OkayPayError(str(data.get('message') or data.get('msg') or data.get('status') or 'خطای نامشخص OkayPay'))
                if not verify(data,self.token): raise OkayPayError('امضای پاسخ OkayPay معتبر نیست')
                return data
    async def create_link(self, amount, coin, unique_id, callback_url='', return_url=''):
        fields={'amount':str(amount),'coin':coin,'unique_id':unique_id,'name':'JetNumber'}
        if callback_url: fields['callback_url']=callback_url
        if return_url: fields['return_url']=return_url
        return await self.post('/shop/payLink',fields)
    async def check_deposit(self, unique_id):
        return await self.post('/shop/checkDeposit',{'unique_id':unique_id})

async def fetch_rates():
    """Returns Toman per USDT and TRX/USD, failing closed if either provider is unavailable."""
    timeout=aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get('https://apiv2.nobitex.ir/market/stats?srcCurrency=usdt&dstCurrency=rls') as r:
            if r.status != 200: raise OkayPayError(f'نرخ USDT از نوبیتکس دریافت نشد (HTTP {r.status})')
            usdt_data=await r.json(content_type=None)
        async with session.get('https://api.coingecko.com/api/v3/simple/price?ids=tron&vs_currencies=usd') as r:
            if r.status != 200: raise OkayPayError(f'نرخ TRX از CoinGecko دریافت نشد (HTTP {r.status})')
            trx_data=await r.json(content_type=None)
    stats=usdt_data.get('stats') if isinstance(usdt_data,dict) else None
    candidate=None
    if isinstance(stats,dict):
        for item in stats.values():
            if isinstance(item,dict):
                candidate=item.get('latest') or item.get('price') or item.get('lastTradePrice')
                if candidate: break
    if candidate is None and isinstance(usdt_data,dict): candidate=usdt_data.get('latest') or usdt_data.get('price')
    try:
        usdt_rial=Decimal(str(candidate)); trx_usd=Decimal(str(trx_data['tron']['usd']))
    except Exception: raise OkayPayError('ساختار نرخ دریافتی معتبر نیست؛ برای جلوگیری از مبلغ اشتباه پرداخت متوقف شد')
    if usdt_rial<=0 or trx_usd<=0: raise OkayPayError('نرخ ارز صفر یا منفی دریافت شد')
    return {'usdt_toman':usdt_rial/Decimal(10),'trx_usd':trx_usd,'source':'Nobitex + CoinGecko'}

def amount_in_coin(toman, coin, rates):
    toman=Decimal(str(int(toman)))
    if coin=='USDT': value=toman/rates['usdt_toman']
    elif coin=='TRX': value=toman/(rates['usdt_toman']*rates['trx_usd'])
    else: raise OkayPayError('ارز پرداخت پشتیبانی نمی‌شود')
    return str(value.quantize(Decimal('0.01'),rounding=ROUND_UP))
