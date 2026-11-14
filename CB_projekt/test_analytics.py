import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from analytics_export import create_csv, create_pdf
from analytics_service import (
    admin_analytics,
    admin_report_rows,
    parse_date_range,
    player_analytics,
    team_analytics,
)
from database import Base


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

        self.admin = models.User(
            username="analytics-admin",
            password_hash="unused",
            role="admin",
            score=0,
            xp=0,
        )
        self.player = models.User(
            username="analytics-player",
            password_hash="unused",
            role="user",
            score=150,
            xp=240,
            current_streak=2,
            longest_streak=5,
        )
        self.other = models.User(
            username="analytics-other",
            password_hash="unused",
            role="user",
            score=50,
            xp=80,
        )
        self.challenge = models.Challenge(
            title="Analytics SQL",
            description="Test challenge",
            category="Web Exploitation",
            points=100,
            flag="CTF{analytics}",
        )
        self.second_challenge = models.Challenge(
            title="Analytics Crypto",
            description="Second test challenge",
            category="Cryptography",
            points=75,
            flag="CTF{crypto}",
        )
        self.db.add_all([
            self.admin, self.player, self.other,
            self.challenge, self.second_challenge,
        ])
        self.db.commit()
        for item in [self.admin, self.player, self.other, self.challenge, self.second_challenge]:
            self.db.refresh(item)

        self.day1 = datetime(2026, 1, 1, 10, 0, 0)
        self.day2 = datetime(2026, 1, 2, 11, 0, 0)
        self.day3 = datetime(2026, 1, 3, 12, 0, 0)
        self.db.add_all([
            models.Submission(
                user_id=self.player.id,
                challenge_id=self.challenge.id,
                is_correct=False,
                submitted_at=self.day1,
            ),
            models.Submission(
                user_id=self.player.id,
                challenge_id=self.challenge.id,
                is_correct=True,
                submitted_at=self.day2,
            ),
            models.Submission(
                user_id=self.other.id,
                challenge_id=self.challenge.id,
                is_correct=False,
                submitted_at=self.day3,
            ),
            models.Solve(
                user_id=self.player.id,
                challenge_id=self.challenge.id,
                timestamp=self.day2,
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_admin_analytics_does_not_multiply_attempts_by_solve_rows(self):
        data = admin_analytics(self.db)

        self.assertEqual(data["total_users"], 3)
        self.assertEqual(data["total_challenges"], 2)
        self.assertEqual(data["attempts"], 3)
        self.assertEqual(data["correct_attempts"], 1)
        self.assertEqual(data["incorrect_attempts"], 2)
        self.assertEqual(data["active_users"], 2)
        self.assertEqual(data["solves"], 1)
        self.assertEqual(data["success_rate"], 33.3)

        challenge = next(row for row in data["challenges"] if row["id"] == self.challenge.id)
        self.assertEqual(challenge["attempts"], 3)
        self.assertEqual(challenge["correct_attempts"], 1)
        self.assertEqual(challenge["solves"], 1)

        category = next(row for row in data["categories"] if row["category"] == "Web Exploitation")
        self.assertEqual(category["attempts"], 3)
        self.assertEqual(category["correct"], 1)
        self.assertEqual(category["solvers"], 1)

    def test_date_filter_uses_inclusive_calendar_dates(self):
        start_at, end_at, start_date, end_date = parse_date_range(
            "2026-01-02",
            "2026-01-02",
        )
        data = admin_analytics(self.db, start_at, end_at)

        self.assertEqual(start_date.isoformat(), "2026-01-02")
        self.assertEqual(end_date.isoformat(), "2026-01-02")
        self.assertEqual(data["attempts"], 1)
        self.assertEqual(data["correct_attempts"], 1)
        self.assertEqual(data["solves"], 1)

    def test_date_range_rejects_start_after_end(self):
        with self.assertRaises(ValueError):
            parse_date_range("2026-02-01", "2026-01-01")

    def test_top_users_uses_separate_aggregations(self):
        data = admin_analytics(self.db)
        player = next(row for row in data["top_users"] if row["user_id"] == self.player.id)

        self.assertEqual(player["attempts"], 2)
        self.assertEqual(player["correct"], 1)
        self.assertEqual(player["solves"], 1)
        self.assertEqual(player["accuracy"], 50.0)

    def test_player_analytics_contains_personal_progress_and_activity(self):
        data = player_analytics(self.db, self.player)

        self.assertEqual(data["username"], "analytics-player")
        self.assertEqual(data["score"], 150)
        self.assertEqual(data["xp"], 240)
        self.assertEqual(data["level"], 3)
        self.assertEqual(data["attempts"], 2)
        self.assertEqual(data["correct"], 1)
        self.assertEqual(data["solves"], 1)
        self.assertEqual(data["accuracy"], 50.0)
        category = next(row for row in data["categories"] if row["category"] == "Web Exploitation")
        self.assertEqual(category["solves"], 1)
        self.assertEqual(category["total"], 1)

    def test_team_analytics_shows_member_contributions_and_tournament_points(self):
        team = models.Team(
            name="Analytics Team",
            description="Test team",
            invite_code="analytics-invite",
            owner_user_id=self.player.id,
        )
        self.db.add(team)
        self.db.flush()
        self.db.add_all([
            models.TeamMember(team_id=team.id, user_id=self.player.id, role="leader"),
            models.TeamMember(team_id=team.id, user_id=self.other.id, role="member"),
        ])
        tournament = models.Tournament(
            title="Analytics Cup",
            description="Test cup",
            competition_type="team",
            starts_at=self.day1,
            ends_at=self.day3 + timedelta(days=1),
            status="finished",
            max_participants=None,
            created_by_user_id=self.admin.id,
        )
        self.db.add(tournament)
        self.db.flush()
        self.db.add(models.TournamentTeamParticipant(
            tournament_id=tournament.id,
            team_id=team.id,
        ))
        self.db.add(models.TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.player.id,
        ))
        self.db.add(models.TournamentSolve(
            tournament_id=tournament.id,
            challenge_id=self.challenge.id,
            user_id=self.player.id,
            team_id=team.id,
            solver_user_id=self.player.id,
            points=125,
            solved_at=self.day2,
        ))
        self.db.commit()

        data = team_analytics(self.db, team)
        self.assertEqual(data["member_count"], 2)
        self.assertEqual(data["total_attempts"], 3)
        self.assertEqual(data["total_solves"], 1)
        self.assertEqual(data["tournament_points"], 125)
        leader = next(row for row in data["members"] if row["username"] == self.player.username)
        self.assertEqual(leader["tournament_points"], 125)
        self.assertEqual(data["tournaments"][0]["points"], 125)

    def test_team_export_rows_contain_team_and_member_data(self):
        team = models.Team(
            name="Export Team",
            description="",
            invite_code="export-invite",
            owner_user_id=self.player.id,
        )
        self.db.add(team)
        self.db.flush()
        self.db.add(models.TeamMember(team_id=team.id, user_id=self.player.id, role="leader"))
        self.db.commit()

        data = team_analytics(self.db, team)
        rows = admin_report_rows(admin_analytics(self.db), "summary")
        self.assertEqual(rows[0], ["Metryka", "Wartość"])
        self.assertEqual(data["team"].name, "Export Team")
        self.assertEqual(data["members"][0]["username"], self.player.username)

    def test_csv_escapes_spreadsheet_formulas_and_keeps_utf8(self):
        payload = create_csv([
            ["Nazwa", "Wartość"],
            ["Drużyna Łódź", "=1+1"],
        ])
        decoded = payload.decode("utf-8-sig")
        self.assertIn("Drużyna Łódź", decoded)
        self.assertIn("'=1+1", decoded)

    def test_pdf_export_returns_a_valid_pdf_document(self):
        payload = create_pdf(
            "Raport CyberSim",
            [("Podsumowanie", [["Metryka", "Wartość"], ["Próby", "3"]])],
        )
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertGreater(len(payload), 500)


if __name__ == "__main__":
    unittest.main()
