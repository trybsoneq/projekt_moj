import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from hint_service import (
    HintError,
    get_hint_view,
    save_challenge_hints,
    unlock_hint,
)


class MultiLevelHintTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.user = models.User(
            username="hint-user",
            password_hash="unused",
            role="user",
            score=100,
        )
        self.challenge = models.Challenge(
            title="Hint challenge",
            description="Test challenge",
            category="Web Exploitation",
            points=200,
            flag="CTF{hint_test}",
        )
        self.db.add_all([self.user, self.challenge])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.challenge)
        save_challenge_hints(self.db, self.challenge, {
            1: ("Pierwszy trop", 0),
            2: ("Drugi trop", 10),
            3: ("Ostatni trop", 20),
        })
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_locked_hint_text_is_not_returned_to_user(self):
        view = get_hint_view(self.db, self.challenge, self.user)
        self.assertEqual(len(view), 3)
        self.assertTrue(view[0]["can_unlock"])
        self.assertFalse(view[0]["is_unlocked"])
        self.assertIsNone(view[0]["content"])
        self.assertFalse(view[1]["can_unlock"])
        self.assertIsNone(view[1]["content"])

    def test_hints_must_be_unlocked_in_order(self):
        hints = self.db.query(models.ChallengeHint).filter_by(challenge_id=self.challenge.id).all()
        second = next(item for item in hints if item.level == 2)
        with self.assertRaises(HintError):
            unlock_hint(self.db, self.user, self.challenge, second.id)
        self.assertEqual(self.user.score, 100)
        self.assertEqual(self.db.query(models.HintUnlock).count(), 0)

    def test_penalty_is_deducted_once_per_hint(self):
        first = self.db.query(models.ChallengeHint).filter_by(
            challenge_id=self.challenge.id, level=1
        ).one()
        second = self.db.query(models.ChallengeHint).filter_by(
            challenge_id=self.challenge.id, level=2
        ).one()

        result_first = unlock_hint(self.db, self.user, self.challenge, first.id)
        self.assertFalse(result_first["already_unlocked"])
        self.assertEqual(self.user.score, 100)
        self.assertEqual(result_first["points_deducted"], 0)

        result_second = unlock_hint(self.db, self.user, self.challenge, second.id)
        self.assertFalse(result_second["already_unlocked"])
        self.assertEqual(self.user.score, 90)
        self.assertEqual(result_second["points_deducted"], 10)

        repeated = unlock_hint(self.db, self.user, self.challenge, second.id)
        self.assertTrue(repeated["already_unlocked"])
        self.assertEqual(self.user.score, 90)
        self.assertEqual(self.db.query(models.HintUnlock).count(), 2)

    def test_user_cannot_spend_more_points_than_they_have(self):
        self.user.score = 5
        self.db.commit()
        hints = self.db.query(models.ChallengeHint).filter_by(challenge_id=self.challenge.id).all()
        first = next(item for item in hints if item.level == 1)
        second = next(item for item in hints if item.level == 2)
        unlock_hint(self.db, self.user, self.challenge, first.id)

        with self.assertRaises(HintError):
            unlock_hint(self.db, self.user, self.challenge, second.id)

        self.assertEqual(self.user.score, 5)
        self.assertEqual(self.db.query(models.HintUnlock).count(), 1)

    def test_unlocked_hint_keeps_text_snapshot_after_admin_edit(self):
        first = self.db.query(models.ChallengeHint).filter_by(
            challenge_id=self.challenge.id, level=1
        ).one()
        unlock_hint(self.db, self.user, self.challenge, first.id)

        first.content = "Nowa treść dla przyszłych użytkowników"
        self.db.commit()

        view = get_hint_view(self.db, self.challenge, self.user)
        self.assertEqual(view[0]["content"], "Pierwszy trop")

    def test_removing_hint_hides_it_but_keeps_unlock_history(self):
        first = self.db.query(models.ChallengeHint).filter_by(
            challenge_id=self.challenge.id, level=1
        ).one()
        unlock_hint(self.db, self.user, self.challenge, first.id)

        save_challenge_hints(self.db, self.challenge, {
            1: ("", 0),
            2: ("Drugi trop", 10),
            3: ("Ostatni trop", 20),
        })
        self.db.commit()

        self.assertEqual(self.db.query(models.HintUnlock).count(), 1)
        self.assertFalse(first.is_active)
        active_view = get_hint_view(self.db, self.challenge, self.user)
        self.assertEqual([row["level"] for row in active_view], [1, 2, 3])
        self.assertTrue(active_view[0]["is_unlocked"])
        self.assertEqual(active_view[0]["content"], "Pierwszy trop")


if __name__ == "__main__":
    unittest.main()
