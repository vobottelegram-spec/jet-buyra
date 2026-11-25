

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass


_RAW_RE = re.compile(r"(0|-1):([0-9a-fA-F]{64})\Z")
_FRIENDLY_LENGTH = 36                                                     
_ALLOWED_TAGS = {0x11, 0x51}
_TEST_ONLY_BIT = 0x80


class TonAddressError(ValueError):
    pass


@dataclass(frozen=True)
class TonAddress:
    

    original: str
    canonical_raw: str


def _crc16_xmodem(data: bytes) -> int:
    
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _decode_friendly(value: str) -> bytes:
                                                                              
                                                                         
    if len(value) != 48:
        raise TonAddressError("user-friendly address must be 48 base64 characters")
    standard = re.fullmatch(r"[A-Za-z0-9+/]{48}", value) is not None
    urlsafe = re.fullmatch(r"[A-Za-z0-9_-]{48}", value) is not None
    if not (standard or urlsafe):
        raise TonAddressError("invalid base64 alphabet or padding")
    try:
        decoded = base64.b64decode(value, altchars=b"-_" if urlsafe and not standard else None, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TonAddressError("invalid base64 encoding") from exc
    if len(decoded) != _FRIENDLY_LENGTH:
        raise TonAddressError("invalid user-friendly payload length")
    return decoded


def validate_ton_address(value: str, *, allow_test_only: bool = False) -> TonAddress:
    
    if not isinstance(value, str):
        raise TonAddressError("address must be a string")
    raw = _RAW_RE.fullmatch(value)
    if raw:
        return TonAddress(value, f"{raw.group(1)}:{raw.group(2).lower()}")

    payload = _decode_friendly(value)
    tag = payload[0]
    test_only = bool(tag & _TEST_ONLY_BIT)
    if test_only:
        if not allow_test_only:
            raise TonAddressError("test-only address is not accepted")
        tag &= ~_TEST_ONLY_BIT
    if tag not in _ALLOWED_TAGS:
        raise TonAddressError("unsupported user-friendly address tag")

    expected_crc = _crc16_xmodem(payload[:-2])
    actual_crc = int.from_bytes(payload[-2:], "big")
    if actual_crc != expected_crc:
        raise TonAddressError("invalid user-friendly address checksum")

    wc_byte = payload[1]
    workchain = wc_byte if wc_byte < 0x80 else wc_byte - 0x100
    if workchain not in (0, -1):
        raise TonAddressError("unsupported workchain; only 0 and -1 are accepted")
    account_id = payload[2:34].hex()
    return TonAddress(value, f"{workchain}:{account_id}")
