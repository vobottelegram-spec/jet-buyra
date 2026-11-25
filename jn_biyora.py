"""Panel 2 provider: the BIYORA inventory, reached through the signed bridge.

Stdlib transport (app/bridge_client.py) run in a worker thread, so no new dependency.
Every response is signature-verified; plain http is refused except for localhost.
"""
import asyncio
import logging
from bridge_client import BridgeClient, BridgeError

log = logging.getLogger('biyora')


class BiyoraError(Exception):
    def __init__(self, code, status=0):
        super().__init__(f'{status}:{code}')
        self.code, self.status = code, status


class Biyora:
    def __init__(self, base='', key_id='jetnumber', secret='', cafile=''):
        self.client = None
        if base and secret:
            try:
                self.client = BridgeClient(base, key_id, secret, cafile=cafile or None)
            except ValueError as exc:
                log.error('BIYORA bridge disabled: %s', exc)

    @property
    def enabled(self):
        return self.client is not None

    async def _call(self, path, payload=None):
        if not self.client:
            raise BiyoraError('not_configured')
        try:
            return await asyncio.to_thread(self.client.call, path, payload)
        except BridgeError as e:
            raise BiyoraError(e.code or 'error', e.status) from None
        except OSError:
            raise BiyoraError('unreachable') from None

    async def stock(self):
        return (await self._call('/v1/stock')).get('regions', {})

    async def reserve(self, region, idem_key):
        return await self._call('/v1/reserve', {'region': region, 'idempotency_key': idem_key})

    async def code(self, order_id):
        try:
            return await self._call('/v1/code', {'order_id': order_id})
        except BiyoraError as e:
            if e.code in ('slow_down', 'code_calls_exhausted'):
                return {'code': None}
            raise

    async def complete(self, order_id):
        return await self._call('/v1/complete', {'order_id': order_id})

    async def release(self, order_id):
        return await self._call('/v1/release', {'order_id': order_id})
