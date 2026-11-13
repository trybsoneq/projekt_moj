import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from achievement_service import (
    ACHIEVEMENT_DEFINITIONS,
    XP_PER_SOLVE,
    level_from_xp,
    longest_consecutive_days,
    process_successful_solve,
    update_user_streak,
)
from activity_service import record_flag_submission


class AchievementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.user = models.User(username="badge-user", password_hash="unused", role="user", score=0)
        self.other_user = models.User(username="other-user", password_hash="unused", role="user", score=0)
        self.challenge = models.Challenge(
            title="First challenge",
            description="Test challenge",
            category="Web",
            points=100,
            flag="CTF{first}",
        )
        self.db.add_all([self.user, self.other_user, self.challenge])
        self.db.add_all([
            models.Achievement(**definition, is_active=True)
            for definition in ACHIEVEMENT_DEFINITIONS
        ])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)
        self.db.refresh(self.challenge)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_level_progression_uses_one_hundred_xp_per_level(self):
        self.assertEqual(level_from_xp(0)["level"], 1)
        self.assertEqual(level_from_xp(99)["level"], 1)
        self.assertEqual(level_from_xp(100)["level"], 2)
        self.assertEqual(level_from_xp(250)["level"], 3)
        self.assertEqual(level_from_xp(250)["xp_to_next_level"], 50)

    def test_longest_streak_counts_unique_consecutive_days(self):
        days = [
            date(2026, 1, 1),
            date(2026, 1, 2),
            date(2026, 1, 2),
            date(2026, 1, 3),
            date(2026, 1, 5),
            date(2026, 1, 6),
        ]
        self.assertEqual(longest_consecutive_days(days), 3)
        self.assertEqual(longest_consecutive_days([]), 0)

    def test_streak_increments_once_per_day_and_resets_after_gap(self):
        self.user.last_solve_date = date(2026, 1, 1)
        self.user.current_streak = 2
        self.assertEqual(update_user_streak(self.user, datetime(2026, 1, 2, 10, 0)), 3)
        self.assertEqual(update_user_streak(self.user, datetime(2026, 1, 2, 18, 0)), 3)
        self.assertEqual(update_user_streak(self.user, datetime(2026, 1, 5, 10, 0)), 1)
        self.assertEqual(self.user.longest_streak, 3)

    def test_successful_solve_awards_xp_and_first_solve_first_blood_badges(self):
        result = record_flag_submission(self.db, self.user, self.challenge, "CTF{first}")

        codes = {item["code"] for item in result["achievements_awarded"]}
        self.assertTrue({"first_solve", "first_blood", "completionist"}.issubset(codes))
        self.assertEqual(result["base_xp_awarded"], XP_PER_SOLVE)
        self.assertEqual(self.user.xp, 10 + 20 + 50 + 100)
        self.assertEqual(self.user.score, 100)
        self.assertEqual(result["level"], 2)

    def test_first_blood_is_only_awarded_to_first_solver_of_a_challenge(self):
        record_flag_submission(self.db, self.user, self.challenge, "CTF{first}")
        result = record_flag_submission(self.db, self.other_user, self.challenge, "CTF{first}")
        codes = {item["code"] for item in result["achievements_awarded"]}
        self.assertNotIn("first_blood", codes)

        first_blood_count = (
            self.db.query(models.UserAchievement)
            .join(models.Achievement)
            .filter(models.Achievement.code == "first_blood")
            .count()
        )
        self.assertEqual(first_blood_count, 1)

    def test_badges_and_xp_are_not_awarded_twice_for_same_solve(self):
        record_flag_submission(self.db, self.user, self.challenge, "CTF{first}")
        xp_after_first = self.user.xp
        score_after_first = self.user.score
        result = record_flag_submission(self.db, self.user, self.challenge, "CTF{first}")

        self.assertTrue(result["already_solved"])
        self.assertEqual(self.user.xp, xp_after_first)
        self.assertEqual(self.user.score, score_after_first)
        self.assertEqual(
            self.db.query(models.UserAchievement).filter_by(user_id=self.user.id).count(),
            3,
        )

    def test_multiple_solves_on_same_day_do_not_increase_streak_twice(self):
        self.user.last_solve_date = date(2026, 1, 1)
        self.user.current_streak = 4
        update_user_streak(self.user, datetime(2026, 1, 1, 20, 0))
        self.assertEqual(self.user.current_streak, 4)


if __name__ == "__main__":
    unittest.main()
