"""Double-submit CSRF protection and baseline browser security headers."""
from __future__ import annotations

import hmac
import os
import secrets
from http.cookies import SimpleCookie

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from security import SESSION_MAX_AGE_SECONDS, SESSION_SECRET

CSRF_COOKIE_NAME = "ctf_csrf"
CSRF_MAX_AGE_SECONDS = SESSION_MAX_AGE_SECONDS
_csrf_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="ctf-platform-csrf")
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_MAX_CSRF_BODY_BYTES = 2 * 1024 * 1024


def create_csrf_token() -> str:
    return _csrf_serializer.dumps(secrets.token_urlsafe(32))


def _valid_cookie_token(value: str | None) -> bool:
    if not value:
        return False
    try:
        nonce = _csrf_serializer.loads(value, max_age=CSRF_MAX_AGE_SECONDS)
        return isinstance(nonce, str) and len(nonce) >= 32
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return False


def _cookie_value(header: bytes, key: str) -> str | None:
    cookie = SimpleCookie()
    try:
        cookie.load(header.decode("latin-1"))
        item = cookie.get(key)
        return item.value if item else None
    except Exception:
        return None


async def _read_full_body(receive, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            raise OverflowError("Request body exceeds CSRF middleware limit.")
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


class CSRFSecurityMiddleware:
    """Validate a signed double-submit token for every state-changing request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        headers = dict(scope.get("headers", []))
        cookie_token = _cookie_value(headers.get(b"cookie", b""), CSRF_COOKIE_NAME)
        cookie_valid = _valid_cookie_token(cookie_token)
        token_to_set = None
        downstream_receive = receive

        if method in _UNSAFE_METHODS:
            try:
                body = await _read_full_body(receive, _MAX_CSRF_BODY_BYTES)
            except OverflowError:
                response = PlainTextResponse("Treść żądania jest zbyt duża.", status_code=413)
                await response(scope, receive, send)
                return

            async def replay_receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            body_sent = False
            request = Request(scope, receive=replay_receive)
            submitted_token = headers.get(b"x-csrf-token", b"").decode("utf-8", errors="ignore").strip()
            content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
            if not submitted_token and (
                "application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type
            ):
                try:
                    form = await request.form()
                    submitted_token = str(form.get("_csrf_token") or "").strip()
                except Exception:
                    submitted_token = ""

            if (
                not cookie_valid
                or not submitted_token
                or not hmac.compare_digest(cookie_token or "", submitted_token)
            ):
                response = PlainTextResponse(
                    "Żądanie zostało odrzucone. Odśwież stronę i spróbuj ponownie.",
                    status_code=403,
                )
                await response(scope, replay_receive, send)
                return
            # The body was consumed for validation. Rewind the buffered copy
            # so FastAPI can parse the form a second time in the route handler.
            body_sent = False
            downstream_receive = replay_receive
        elif not cookie_valid:
            token_to_set = create_csrf_token()

        async def security_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in response_headers}

                def add_header(name: str, value: str):
                    if name.lower().encode("latin-1") not in existing:
                        response_headers.append(
                            (name.lower().encode("latin-1"), value.encode("latin-1"))
                        )
                        existing.add(name.lower().encode("latin-1"))

                add_header("x-content-type-options", "nosniff")
                add_header("x-frame-options", "DENY")
                add_header("referrer-policy", "strict-origin-when-cross-origin")
                add_header("permissions-policy", "camera=(), microphone=(), geolocation=()")
                add_header(
                    "content-security-policy",
                    "default-src 'self'; object-src 'none'; base-uri 'self'; "
                    "frame-ancestors 'none'; form-action 'self' https://formspree.io; "
                    "img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'",
                )
                if os.getenv("CTF_COOKIE_SECURE", "0") == "1":
                    add_header("strict-transport-security", "max-age=31536000; includeSubDomains")

                if token_to_set:
                    secure = "; Secure" if os.getenv("CTF_COOKIE_SECURE", "0") == "1" else ""
                    cookie = (
                        f"{CSRF_COOKIE_NAME}={token_to_set}; Path=/; "
                        f"Max-Age={CSRF_MAX_AGE_SECONDS}; SameSite=Strict{secure}"
                    )
                    response_headers.append((b"set-cookie", cookie.encode("latin-1")))

                message["headers"] = response_headers
            await send(message)

        await self.app(scope, downstream_receive, security_send)
