import json
import aiohttp
from urllib.parse import quote

class TNumberError(Exception):
    pass

class TNumber:
    """TNumber API client for the documented v1 endpoints."""
    def __init__(self,key,base='https://b.tnumber.site'):
        self.key=key
        self.base=base.rstrip('/')

    async def _req(self,method,path,**kwargs):
        if not self.key:
            raise TNumberError('missing api key')
        headers=dict(kwargs.pop('headers',{}) or {})
        headers['X-API-Key']=self.key
        headers.setdefault('Accept','application/json')
        timeout=aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout,headers=headers) as s:
            async with s.request(method,self.base+path,**kwargs) as r:
                txt=await r.text()
                try: data=json.loads(txt)
                except Exception: data={'success':False,'error':txt}
                if r.status>=400 or (isinstance(data,dict) and data.get('success') is False):
                    raise TNumberError(f'{r.status}: {data}')
                return data

    async def countries(self):
        return await self._req('GET','/api/v1/buy/available-countries')

    async def balance(self):
        return await self._req('GET','/api/v1/account/balance')

    async def buy(self,iso):
        # Documented purchase endpoint: POST /api/v1/buy/account?country=ISO
        return await self._req('POST',f'/api/v1/buy/account?country={quote(str(iso).upper())}')

    async def code(self,phone):
        return await self._req('GET',f'/api/v1/account/code/{quote(str(phone),safe="+") }')

    async def cancel(self,phone):
        return await self._req('POST',f'/api/v1/order/cancel?phonenumber={quote(str(phone),safe="+") }')

    async def logout(self,phone):
        return await self._req('POST',f'/api/v1/account/logout?phonenumber={quote(str(phone),safe="+") }')
