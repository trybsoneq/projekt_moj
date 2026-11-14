import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from notification_service import (
    create_notification,
    notify_all_users_once,
    notify_users_once,
    process_due_tournament_notifications,
)


class NotificationServiceTests(unittest.TestCase):
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
            username="notify-user",
            password_hash="unused",
            role="user",
            score=0,
            xp=0,
        )
        self.other_user = models.User(
            username="notify-other",
            password_hash="unused",
            role="user",
            score=0,
            xp=0,
        )
        self.db.add_all([self.user, self.other_user])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)
        self.now = datetime(2026, 5, 10, 12, 0, 0)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_new_category_preferences_default_to_enabled_and_dedupe(self):
        first = create_notification(
            self.db,
            self.user.id,
            "team",
            "Zaproszenie",
            "Otrzymano zaproszenie do drużyny.",
            target_url="/teams",
            dedupe_key="team-invitation:1",
        )
        duplicate = create_notification(
            self.db,
            self.user.id,
            "team",
            "Zaproszenie",
            "Powtórzona próba wysłania.",
            target_url="/teams",
            dedupe_key="team-invitation:1",
        )
        self.db.commit()

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual(self.db.query(models.Notification).count(), 1)

    def test_user_can_disable_one_category_without_disabling_others(self):
        self.db.add(models.NotificationPreference(
            user_id=self.user.id,
            team_enabled=False,
            tournament_enabled=True,
            achievement_enabled=True,
            announcement_enabled=True,
        ))
        self.db.commit()

        team_result = create_notification(
            self.db, self.user.id, "team", "Team event", "Body"
        )
        tournament_result = create_notification(
            self.db, self.user.id, "tournament", "Tournament event", "Body"
        )
        self.db.commit()

        self.assertFalse(team_result)
        self.assertTrue(tournament_result)
        self.assertEqual(self.db.query(models.Notification).count(), 1)
        self.assertEqual(
            self.db.query(models.Notification).one().category,
            "tournament",
        )

    def test_broadcast_is_sent_once_and_respects_each_users_preferences(self):
        self.db.add(models.NotificationPreference(
            user_id=self.other_user.id,
            team_enabled=False,
            tournament_enabled=True,
            achievement_enabled=True,
            announcement_enabled=True,
        ))
        self.db.commit()

        delivered_first = notify_users_once(
            self.db,
            [self.user.id, self.other_user.id],
            "team",
            "Zaproszenie",
            "Drużyna zaprasza Cię do składu.",
            target_url="/teams",
            event_key="test:broadcast:once",
        )
        delivered_second = notify_users_once(
            self.db,
            [self.user.id, self.other_user.id],
            "team",
            "Zaproszenie",
            "Powtórzony komunikat.",
            target_url="/teams",
            event_key="test:broadcast:once",
        )
        self.db.commit()

        self.assertEqual(delivered_first, 1)
        self.assertEqual(delivered_second, 0)
        self.assertEqual(self.db.query(models.Notification).count(), 1)
        self.assertEqual(
            self.db.query(models.Notification).one().user_id,
            self.user.id,
        )

    def test_tournament_reminders_start_and_finish_are_delivered_once(self):
        tournament = models.Tournament(
            title="Night Cup",
            description="Notification test",
            competition_type="individual",
            starts_at=self.now + timedelta(hours=23),
            ends_at=self.now + timedelta(hours=25),
            status="open",
            max_participants=None,
            created_by_user_id=self.user.id,
        )
        self.db.add(tournament)
        self.db.flush()
        self.db.add(models.TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user.id,
        ))
        self.db.commit()

        first = process_due_tournament_notifications(self.db, now=self.now)
        self.db.commit()
        second = process_due_tournament_notifications(self.db, now=self.now)
        self.db.commit()
        self.assertEqual(first["24h"], 1)
        self.assertEqual(second["24h"], 0)

        one_hour_before = self.now + timedelta(hours=22, minutes=30)
        one_hour = process_due_tournament_notifications(self.db, now=one_hour_before)
        self.db.commit()
        self.assertEqual(one_hour["1h"], 1)

        just_started = self.now + timedelta(hours=23, minutes=1)
        started = process_due_tournament_notifications(self.db, now=just_started)
        self.db.commit()
        started_again = process_due_tournament_notifications(self.db, now=just_started)
        self.db.commit()
        self.assertEqual(started["started"], 1)
        self.assertEqual(started_again["started"], 0)

        after_end = self.now + timedelta(hours=26)
        finished = process_due_tournament_notifications(self.db, now=after_end)
        self.db.commit()
        finished_again = process_due_tournament_notifications(self.db, now=after_end)
        self.db.commit()
        self.assertEqual(finished["finished"], 1)
        self.assertEqual(finished_again["finished"], 0)
        self.db.refresh(tournament)
        self.assertEqual(tournament.status, "finished")

    def test_announcement_broadcast_links_notifications_to_announcement(self):
        announcement = models.Announcement(
            title="Maintenance",
            body="Platform will be updated.",
            created_by_user_id=self.user.id,
        )
        self.db.add(announcement)
        self.db.flush()

        delivered = notify_all_users_once(
            self.db,
            "announcement",
            announcement.title,
            announcement.body,
            target_url="/notifications",
            event_key=f"announcement:{announcement.id}:published",
            announcement_id=announcement.id,
        )
        self.db.commit()

        self.assertEqual(delivered, 2)
        self.assertEqual(
            self.db.query(models.Notification)
            .filter(models.Notification.announcement_id == announcement.id)
            .count(),
            2,
        )

    def test_unsupported_notification_category_is_rejected(self):
        with self.assertRaises(ValueError):
            create_notification(
                self.db,
                self.user.id,
                "unknown",
                "Title",
                "Body",
            )


if __name__ == "__main__":
    unittest.main()
