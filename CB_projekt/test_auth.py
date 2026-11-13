import unittest

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from security import create_session_token, get_current_user, require_admin


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=cls.engine)
        db = cls.Session()
        db.add_all([
            models.User(username="regular", password_hash="x", role="user"),
            models.User(username="admin-test", password_hash="x", role="admin"),
        ])
        db.commit()
        cls.user_id = db.query(models.User).filter_by(username="regular").one().id
        cls.admin_id = db.query(models.User).filter_by(username="admin-test").one().id
        db.close()

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app = FastAPI()
        app.dependency_overrides[get_db] = override_db
        app.get("/whoami")(lambda user=Depends(get_current_user): {
            "username": user.username if user else None,
            "role": user.role if user else None,
        })
        app.get("/admin-only")(lambda user=Depends(require_admin): {"ok": True})
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def test_missing_cookie_is_anonymous(self):
        response = self.client.get("/whoami")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["username"])

    def test_valid_signed_cookie_resolves_user(self):
        token = create_session_token(self.user_id)
        response = self.client.get("/whoami", cookies={"ctf_session": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"username": "regular", "role": "user"})

    def test_tampered_cookie_is_anonymous(self):
        token = create_session_token(self.admin_id) + "tampered"
        response = self.client.get("/whoami", cookies={"ctf_session": token})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["username"])

    def test_regular_user_cannot_access_admin_dependency(self):
        token = create_session_token(self.user_id)
        response = self.client.get("/admin-only", cookies={"ctf_session": token})
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_dependency(self):
        token = create_session_token(self.admin_id)
        response = self.client.get("/admin-only", cookies={"ctf_session": token})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
