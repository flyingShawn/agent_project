from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from agent_backend.core.config import get_settings

_HEADER_USER = "x-external-user"
_HEADER_TS = "x-external-ts"
_HEADER_SIGN = "x-external-sign"
_HEADER_NAME = "x-external-name"


@dataclass(frozen=True)
class ExternalIdentity:
    user_id: str
    display_name: str
    ts: int | None = None
    sign: str | None = None


def _pick_request_value(request: Request, header_name: str, query_name: str, allow_query: bool = False) -> str:
    value = request.headers.get(header_name, "").strip()
    if value:
        return value
    if allow_query:
        return request.query_params.get(query_name, "").strip()
    return ""


def _build_signature(user_id: str, ts: int, secret: str) -> str:
    payload = f"{user_id}|{ts}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def resolve_external_identity(request: Request, allow_query: bool = False) -> ExternalIdentity:
    """统一解析外部入口身份；未配置 secret 时回退到本地 admin 兼容模式。"""
    settings = get_settings().misc
    secret = settings.external_entry_secret.strip()

    user_id = _pick_request_value(request, _HEADER_USER, "user", allow_query)
    display_name = _pick_request_value(request, _HEADER_NAME, "name", allow_query)

    if not secret:
        fallback_user = (
            user_id
            or request.query_params.get("user_id", "").strip()
            or request.query_params.get("lognum", "").strip()
            or "admin"
        )
        return ExternalIdentity(
            user_id=fallback_user,
            display_name=display_name or fallback_user,
        )

    ts_raw = _pick_request_value(request, _HEADER_TS, "ts", allow_query)
    sign = _pick_request_value(request, _HEADER_SIGN, "sign", allow_query)

    if not user_id or not ts_raw or not sign:
        raise HTTPException(status_code=401, detail="缺少外部身份签名参数")

    try:
        ts = int(ts_raw)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="外部身份时间戳无效") from exc

    if abs(int(time.time()) - ts) > settings.external_entry_ttl_seconds:
        raise HTTPException(status_code=401, detail="外部身份签名已过期")

    expected_sign = _build_signature(user_id, ts, secret)
    if not hmac.compare_digest(expected_sign, sign):
        raise HTTPException(status_code=401, detail="外部身份签名校验失败")

    return ExternalIdentity(
        user_id=user_id,
        display_name=display_name or user_id,
        ts=ts,
        sign=sign,
    )


async def require_external_identity(request: Request) -> ExternalIdentity:
    return resolve_external_identity(request)


async def require_external_identity_from_query(request: Request) -> ExternalIdentity:
    return resolve_external_identity(request, allow_query=True)
