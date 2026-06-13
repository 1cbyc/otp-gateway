"""SMS/OTP webhook -> Redis pub/sub."""

import json
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    webhook_secret: str
    redis_url: str = "redis://localhost:6379/0"
    otp_regex: str = r"(?i)(?<![A-Z0-9])(?=[A-Z0-9]*\d)([A-Z0-9]{4,8})(?![A-Z0-9])"
    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
_otp_re = re.compile(settings.otp_regex)


class SmsPayload(BaseModel):
    text: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    sender: str | None = None


def extract_code(text: str) -> str | None:
    m = _otp_re.search(text)
    return m.group(1).upper() if m else None


def channel(session_id: str) -> str:
    return f"otp:{session_id}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await app.state.redis.ping()
    except redis.ConnectionError as e:
        raise RuntimeError(f"redis unreachable: {e}") from e
    yield
    await app.state.redis.aclose()


app = FastAPI(title="otp-gateway", lifespan=lifespan)


def verify_secret(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif x_api_key:
        token = x_api_key

    if not token or token != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/webhook/sms")
async def sms_webhook(
    payload: SmsPayload,
    _: Annotated[None, Depends(verify_secret)],
    session_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    x_session_id: Annotated[str | None, Header()] = None,
):
    sid = payload.session_id or session_id or x_session_id
    if not sid:
        raise HTTPException(status_code=400, detail="session_id required")

    code = extract_code(payload.text)
    if not code:
        raise HTTPException(status_code=422, detail="no code in message")

    msg = json.dumps({"code": code, "sender": payload.sender, "ts": int(time.time())})
    await app.state.redis.publish(channel(sid), msg)

    return {"session_id": sid, "code": code, "published": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
