import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sql.key_value import KeyValueSqlModel

_ACCESS_TOKEN_KEY = "youtube_access_token"
_REFRESH_TOKEN_KEY = "youtube_refresh_token"
_TOKEN_EXPIRES_KEY = "youtube_token_expires_ms"
_CLIENT_ID_KEY = "youtube_client_id"
_CLIENT_SECRET_KEY = "youtube_client_secret"


async def _get_value(session: AsyncSession, key: str) -> dict | None:
    result = await session.scalars(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
    row = result.first()
    return row.value if row else None


async def _set_value(session: AsyncSession, key: str, value: dict) -> None:
    result = await session.scalars(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
    row = result.first()
    if row:
        row.value = value
    else:
        session.add(KeyValueSqlModel(key=key, value=value))
    await session.commit()


async def get_youtube_access_token(session: AsyncSession) -> str | None:
    value = await _get_value(session, _ACCESS_TOKEN_KEY)
    return value.get("data") if value else None


async def set_youtube_access_token(session: AsyncSession, token: str) -> None:
    await _set_value(session, _ACCESS_TOKEN_KEY, {"data": token})


async def get_youtube_refresh_token(session: AsyncSession) -> str | None:
    value = await _get_value(session, _REFRESH_TOKEN_KEY)
    return value.get("data") if value else None


async def set_youtube_refresh_token(session: AsyncSession, token: str) -> None:
    await _set_value(session, _REFRESH_TOKEN_KEY, {"data": token})


async def get_youtube_token_expires_ms(session: AsyncSession) -> int | None:
    value = await _get_value(session, _TOKEN_EXPIRES_KEY)
    data = value.get("data") if value else None
    return int(data) if data is not None else None


async def set_youtube_token_expires_ms(session: AsyncSession, expires_ms: int) -> None:
    await _set_value(session, _TOKEN_EXPIRES_KEY, {"data": expires_ms})


async def is_youtube_token_expired(session: AsyncSession) -> bool:
    expires_ms = await get_youtube_token_expires_ms(session)
    if not expires_ms:
        return True
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return now_ms >= expires_ms


async def get_youtube_credentials(session: AsyncSession) -> dict:
    """Return stored credentials as a dict compatible with google-auth."""
    access_token = await get_youtube_access_token(session)
    refresh_token = await get_youtube_refresh_token(session)
    expires_ms = await get_youtube_token_expires_ms(session)
    client_id = await _get_value(session, _CLIENT_ID_KEY)
    client_secret = await _get_value(session, _CLIENT_SECRET_KEY)

    creds = {
        "token": access_token,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id.get("data") if client_id else None,
        "client_secret": client_secret.get("data") if client_secret else None,
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    }
    if expires_ms:
        creds["expiry"] = datetime.fromtimestamp(expires_ms / 1000, tz=timezone.utc).isoformat()
    return creds


async def set_youtube_credentials(
    session: AsyncSession,
    *,
    access_token: str,
    refresh_token: str,
    expires_ms: int,
    client_id: str,
    client_secret: str,
) -> None:
    await set_youtube_access_token(session, access_token)
    await set_youtube_refresh_token(session, refresh_token)
    await set_youtube_token_expires_ms(session, expires_ms)
    await _set_value(session, _CLIENT_ID_KEY, {"data": client_id})
    await _set_value(session, _CLIENT_SECRET_KEY, {"data": client_secret})


async def clear_youtube_credentials(session: AsyncSession) -> None:
    for key in (
        _ACCESS_TOKEN_KEY,
        _REFRESH_TOKEN_KEY,
        _TOKEN_EXPIRES_KEY,
        _CLIENT_ID_KEY,
        _CLIENT_SECRET_KEY,
    ):
        value = await _get_value(session, key)
        if value:
            value["data"] = None
            await _set_value(session, key, value)
