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
    calculate_cpu_percent,
    calculate_memory_usage,
    format_bytes,
    get_active_instance,
    instance_url,
    is_supported_template,
    start_or_get_instance,
    PROXY_CONTEXT,
    PROXY_PORT,
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

    def test_ingress_proxy_template_is_available(self):
        self.assertTrue(PROXY_CONTEXT.is_dir())
        self.assertEqual(PROXY_PORT, 8080)

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


class DockerMetricsTests(unittest.TestCase):
    def test_cpu_percentage_uses_cpu_and_system_deltas(self):
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 300, "percpu_usage": [1, 1]},
                "system_cpu_usage": 1200,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 200},
                "system_cpu_usage": 1100,
            },
        }
        self.assertEqual(calculate_cpu_percent(stats), 200.0)

    def test_cpu_percentage_returns_none_without_valid_sample(self):
        self.assertIsNone(calculate_cpu_percent({}))
        self.assertIsNone(calculate_cpu_percent({
            "cpu_stats": {"cpu_usage": {"total_usage": 10}, "system_cpu_usage": 100},
            "precpu_stats": {"cpu_usage": {"total_usage": 5}, "system_cpu_usage": 100},
        }))

    def test_memory_usage_subtracts_inactive_file_cache(self):
        stats = {
            "memory_stats": {
                "usage": 512 * 1024 * 1024,
                "limit": 1024 * 1024 * 1024,
                "stats": {"total_inactive_file": 128 * 1024 * 1024},
            }
        }
        result = calculate_memory_usage(stats)
        self.assertEqual(result["usage_bytes"], 384 * 1024 * 1024)
        self.assertEqual(result["limit_bytes"], 1024 * 1024 * 1024)
        self.assertEqual(result["percent"], 37.5)

    def test_format_bytes_handles_missing_and_megabytes(self):
        self.assertEqual(format_bytes(None), "—")
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")


if __name__ == "__main__":
    unittest.main()
