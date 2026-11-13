import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from docker_manager import (
    DockerManagerError,
    SUPPORTED_TEMPLATES,
    get_active_instance,
    instance_url,
    is_supported_template,
    start_or_get_instance,
)


class DockerManagerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.user = models.User(username="docker-user", password_hash="unused", role="user")
        self.challenge = models.Challenge(
            title="CyberShop", description="SQL Injection lab",
            category="Web Exploitation", points=100,
            flag="CTF{test}", docker_template="web_sqli",
        )
        self.db.add_all([self.user, self.challenge])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.challenge)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_only_allow_listed_templates_are_accepted(self):
        self.assertTrue(is_supported_template("web_sqli"))
        self.assertTrue(is_supported_template(None))
        self.assertFalse(is_supported_template("host-filesystem-mount"))
        self.assertEqual(set(SUPPORTED_TEMPLATES), {"web_sqli"})

    def test_unknown_template_is_rejected_before_docker_access(self):
        self.challenge.docker_template = "not-allowed"
        self.db.commit()
        with patch("docker_manager._docker_client", side_effect=AssertionError("Docker must not be called")):
            with self.assertRaises(DockerManagerError):
                start_or_get_instance(self.db, self.user, self.challenge)
        self.assertEqual(self.db.query(models.ChallengeInstance).count(), 0)

    def test_active_instance_is_scoped_to_user_and_challenge(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        instance = models.ChallengeInstance(
            user_id=self.user.id, challenge_id=self.challenge.id, status="running",
            host_port=49152, created_at=now, expires_at=now + timedelta(minutes=10),
        )
        self.db.add(instance)
        self.db.commit()
        active = get_active_instance(self.db, self.user.id, self.challenge.id)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, instance.id)
        self.assertIsNone(get_active_instance(self.db, self.user.id + 1, self.challenge.id))

    def test_expired_instance_is_not_returned_as_active(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.add(models.ChallengeInstance(
            user_id=self.user.id, challenge_id=self.challenge.id, status="running",
            host_port=49153, created_at=now - timedelta(hours=1),
            expires_at=now - timedelta(seconds=1),
        ))
        self.db.commit()
        self.assertIsNone(get_active_instance(self.db, self.user.id, self.challenge.id))

    def test_instance_url_uses_configured_public_host(self):
        instance = models.ChallengeInstance(host_port=49154)
        with patch.dict(os.environ, {"CTF_PUBLIC_HOST": "ctf.example.test"}):
            self.assertEqual(instance_url(instance), "http://ctf.example.test:49154")


if __name__ == "__main__":
    unittest.main()
