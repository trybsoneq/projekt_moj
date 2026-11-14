import unittest

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from csrf_middleware import CSRFSecurityMiddleware, CSRF_COOKIE_NAME
from security import SlidingWindowRateLimiter, validate_registration
from database import engine as application_engine


class CSRFMiddlewareTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(CSRFSecurityMiddleware)

        @app.get("/form")
        def get_form():
            return PlainTextResponse("form page")

        @app.post("/change")
        async def change(request: Request):
            form = await request.form()
            return {"saved": form.get("value")}

        @app.post("/json-change")
        async def json_change(request: Request):
            return {"saved": (await request.json()).get("value")}

        self.client = TestClient(app)

    def test_get_sets_signed_csrf_cookie_and_security_headers(self):
        response = self.client.get("/form")
        self.assertEqual(response.status_code, 200)
        self.assertIn(CSRF_COOKIE_NAME, response.cookies)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertIn("SameSite=Strict", response.headers["set-cookie"])

    def test_same_origin_form_with_matching_double_submit_token_passes(self):
        self.client.get("/form")
        token = self.client.cookies.get(CSRF_COOKIE_NAME)
        response = self.client.post(
            "/change",
            data={"_csrf_token": token, "value": "saved"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"saved": "saved"})

    def test_missing_or_mismatched_form_token_is_rejected(self):
        self.client.get("/form")
        missing = self.client.post("/change", data={"value": "no"})
        mismatched = self.client.post(
            "/change",
            data={"_csrf_token": "not-the-cookie", "value": "no"},
        )
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(mismatched.status_code, 403)

    def test_json_requests_can_use_csrf_header(self):
        self.client.get("/form")
        token = self.client.cookies.get(CSRF_COOKIE_NAME)
        response = self.client.post(
            "/json-change",
            json={"value": "json"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"saved": "json"})


class AuthenticationRateLimiterTests(unittest.TestCase):
    def test_sliding_window_limiter_blocks_then_releases(self):
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        self.assertEqual(limiter.check("client-a", now=0), 0)
        self.assertEqual(limiter.check("client-a", now=10), 0)
        self.assertGreater(limiter.check("client-a", now=20), 0)
        self.assertEqual(limiter.check("client-a", now=61), 0)

    def test_success_reset_clears_only_one_client(self):
        limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
        limiter.check("client-a", now=0)
        limiter.check("client-b", now=0)
        limiter.reset("client-a")
        self.assertEqual(limiter.check("client-a", now=1), 0)
        self.assertGreater(limiter.check("client-b", now=1), 0)

    def test_sqlite_connections_enable_foreign_keys_and_busy_timeout(self):
        with application_engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
            self.assertGreaterEqual(connection.exec_driver_sql("PRAGMA busy_timeout").scalar(), 5000)

    def test_registration_validation_enforces_username_password_and_confirmation(self):
        self.assertIsNone(validate_registration("player_01", "long-password-123", "long-password-123"))
        self.assertIsNotNone(validate_registration("ab", "long-password-123", "long-password-123"))
        self.assertIsNotNone(validate_registration("bad name", "long-password-123", "long-password-123"))
        self.assertIsNotNone(validate_registration("player", "short", "short"))
        self.assertIsNotNone(validate_registration("player", "long-password-123", "different-password"))
        self.assertIsNotNone(validate_registration("player", "ą" * 40, "ą" * 40))


if __name__ == "__main__":
    unittest.main()
