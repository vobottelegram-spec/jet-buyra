
from __future__ import annotations

import asyncio
import time
import pending_session_store as store
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest

_RETRY = 30 * 60


def _terminal(exc):
    description = (type(exc).__name__ + ' ' + str(getattr(exc, 'message', ''))).upper().replace('_', '')
    return any(name in description for name in (
        'AUTHKEYDUPLICATED', 'AUTHKEYUNREGISTERED', 'AUTHKEYINVALID',
        'USERDEACTIVATED', 'PHONENUMBERBANNED', 'SESSIONREVOKED',
        'SESSIONEXPIRED', 'USERIDINVALID', 'ACCOUNTDEACTIVATED'))


def _retry_delay(exc):
    name = type(exc).__name__.upper()
    seconds = getattr(exc, 'seconds', None)
    if 'FLOOD' in name and 'WAIT' in name and isinstance(seconds, (int, float)):
        return max(1, int(seconds) + 1)
    return _RETRY


def _auth_list(response):
    auths = getattr(response, 'authorizations', None)
    if not isinstance(auths, (list, tuple)):
        raise ValueError('Malformed authorization list')
    if any(getattr(auth, 'current', None) is not True
           and getattr(auth, 'current', None) is not False for auth in auths):
        raise ValueError('Malformed current flag')
    current = [auth for auth in auths if auth.current is True]
    if len(current) != 1 or not isinstance(getattr(current[0], 'hash', None), int):
        raise ValueError('Invalid current authorization')
    return current[0], auths


async def process_job(db_path, account_id, client, credit_callback, now=None):
    clock = (lambda: int(time.time())) if now is None else (lambda: int(now))
    job = await asyncio.to_thread(store.eligible_job, db_path, account_id, clock())
    if job is None:
        return 'skipped'

    async def eligible():
        current = await asyncio.to_thread(store.eligible_job, db_path, account_id, clock())
        return current if current and current.get('session_string') == job.get('session_string') else None

    async def finish(status, error=None):
        await asyncio.to_thread(store.finish, db_path, account_id, status=status, last_error=error)

    async def defer(exc=None, delay=None):
        await asyncio.to_thread(store.reschedule, db_path, account_id,
            clock() + (_retry_delay(exc) if delay is None else delay),
            type(exc).__name__ if exc is not None else 'AuthorizationStateUnverified')
        return 'deferred'

    try:
        me = await client.get_me()
        if me is None or getattr(me, 'id', None) != job['tg_user_id']:
            await finish('failed', 'IdentityMismatch')
            return 'failed'
        current, auths = _auth_list(await client(GetAuthorizationsRequest()))
        created = getattr(current, 'date_created', None)
        if created is None:
            return await defer()
        created = int(created.timestamp()) if hasattr(created, 'timestamp') else int(created)
        if created + 86400 > clock():
            return await defer(delay=created + 86400 - clock())
        others = [auth for auth in auths if auth.current is False]
        if any(not isinstance(getattr(auth, 'hash', None), int)
               or isinstance(auth.hash, bool) or auth.hash == 0
               or auth.hash == current.hash for auth in others):
            return await defer()
        for auth in others:
            if await eligible() is None:
                return 'skipped'
            if await client(ResetAuthorizationRequest(hash=auth.hash)) is not True:
                return await defer()
                                                                           
        verified_current, confirmed = _auth_list(await client(GetAuthorizationsRequest()))
        if verified_current.hash != current.hash or any(auth.current is not True for auth in confirmed):
            return await defer()
        if await eligible() is None:
            return 'skipped'
        status, audit = await credit_callback(account_id, job['seller_id'])
        if status in ('credited', 'already_credited') and audit:
            await finish('done')
            return 'done'
        if status == 'cancelled':
            return 'skipped'
        await finish('failed', 'Credit_' + str(status))
        return 'failed'
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if _terminal(exc):
            await finish('failed', type(exc).__name__)
            return 'failed'
        return await defer(exc)
