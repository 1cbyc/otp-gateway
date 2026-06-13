# otp-gateway

Webhook that takes SMS payloads from an Android forwarder, pulls out the OTP, publishes it on Redis.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set WEBHOOK_SECRET and REDIS_URL
```

Run:

```bash
python main.py
```

## POST /webhook/sms

Auth: `Authorization: Bearer <WEBHOOK_SECRET>` or `X-API-Key: <WEBHOOK_SECRET>`

Session ID (pick one):

- JSON field `session_id`
- query `?session_id=...`
- header `X-Session-Id`

Body:

```json
{
  "text": "Your code is 482913. Do not share.",
  "sender": "+15551234567"
}
```

Response on success:

```json
{"session_id": "checkout-abc", "code": "482913", "published": true}
```

Errors: `401` bad auth, `400` missing session, `422` no OTP in text.

## Redis

Channel: `otp:<session_id>`

Message:

```json
{"code":"482913","sender":"+15551234567","ts":1718280000}
```

Subscribe:

```bash
redis-cli SUBSCRIBE otp:checkout-abc
```

## OTP regex

Default: 4–8 chars, at least one digit (covers numeric and mixed alphanumeric). Override with `OTP_REGEX` in `.env`.

## Android forwarder

Point the app at `https://your-host/webhook/sms`. Set the auth header. Pass `session_id` so your automation knows which flow this OTP belongs to.

Typical Tasker / SMS Forwarder mapping:

- URL: your webhook
- Header: `Authorization: Bearer <secret>`
- Body: `%SMSRB` or whatever field holds the message text
- Session: static per flow, or derived from app state via `X-Session-Id`

## Health

`GET /health` → `{"ok": true}`
