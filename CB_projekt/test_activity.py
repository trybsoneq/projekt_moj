import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from activity_service import (
    MAX_FLAG_ATTEMPTS_PER_MINUTE,
    SubmissionRateLimitError,
    record_flag_submission,
)


class FlagSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.user = models.User(username="activity-user", password_hash="not-used", role="user", score=0)
        self.challenge = models.Challenge(
            title="Test challenge",
            description="Test description",
            category="Web Exploitation",
            points=100,
            flag="CTF{correct_flag}",
        )
        self.db.add_all([self.user, self.challenge])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.challenge)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_incorrect_attempt_is_recorded_without_storing_flag_text(self):
        result = record_flag_submission(self.db, self.user, self.challenge, "CTF{wrong}")
        submissions = self.db.query(models.Submission).all()

        self.assertFalse(result["is_correct"])
        self.assertEqual(len(submissions), 1)
        self.assertFalse(submissions[0].is_correct)
        self.assertEqual(self.user.score, 0)
        self.assertEqual(self.db.query(models.Solve).count(), 0)
        self.assertFalse(hasattr(submissions[0], "submitted_flag"))

    def test_correct_attempt_records_result_and_awards_points(self):
        result = record_flag_submission(self.db, self.user, self.challenge, "  CTF{correct_flag}  ")
        submissions = self.db.query(models.Submission).all()

        self.assertTrue(result["is_correct"])
        self.assertEqual(result["points_awarded"], 100)
        self.assertEqual(self.user.score, 100)
        self.assertEqual(self.db.query(models.Solve).count(), 1)
        self.assertEqual(len(submissions), 1)
        self.assertTrue(submissions[0].is_correct)

    def test_solving_same_challenge_twice_does_not_award_points_twice(self):
        record_flag_submission(self.db, self.user, self.challenge, "CTF{correct_flag}")
        result = record_flag_submission(self.db, self.user, self.challenge, "CTF{correct_flag}")

        self.assertTrue(result["already_solved"])
        self.assertEqual(result["points_awarded"], 0)
        self.assertEqual(self.user.score, 100)
        self.assertEqual(self.db.query(models.Solve).count(), 1)
        self.assertEqual(self.db.query(models.Submission).count(), 1)

    def test_rate_limit_applies_across_challenges_for_one_user(self):
        second_challenge = models.Challenge(
            title="Second challenge",
            description="Another test",
            category="Forensics",
            points=50,
            flag="CTF{second}",
        )
        self.db.add(second_challenge)
        self.db.commit()

        with patch("activity_service.MAX_FLAG_ATTEMPTS_PER_MINUTE", 2):
            record_flag_submission(self.db, self.user, self.challenge, "wrong-1")
            record_flag_submission(self.db, self.user, second_challenge, "wrong-2")
            with self.assertRaises(SubmissionRateLimitError):
                record_flag_submission(self.db, self.user, self.challenge, "wrong-3")

        self.assertEqual(self.db.query(models.Submission).count(), 2)

    def test_rate_limited_attempt_does_not_create_history_record(self):
        with patch("activity_service.MAX_FLAG_ATTEMPTS_PER_MINUTE", 1):
            record_flag_submission(self.db, self.user, self.challenge, "wrong")
            with self.assertRaises(SubmissionRateLimitError):
                record_flag_submission(self.db, self.user, self.challenge, "another-wrong")
        self.assertEqual(self.db.query(models.Submission).count(), 1)


if __name__ == "__main__":
    unittest.main()
