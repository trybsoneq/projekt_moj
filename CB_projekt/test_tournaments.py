import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from activity_service import record_flag_submission
from tournament_service import (
    TournamentError,
    join_tournament,
    record_tournament_solve,
    registered_count,
    tournament_leaderboards,
)


class TournamentServiceTests(unittest.TestCase):
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
            username="tournament-user",
            password_hash="unused",
            role="user",
            score=321,
            xp=75,
        )
        self.other_user = models.User(
            username="second-user",
            password_hash="unused",
            role="user",
            score=0,
            xp=0,
        )
        self.challenge = models.Challenge(
            title="Tournament challenge",
            description="Test",
            category="Web",
            points=100,
            flag="CTF{tournament}",
        )
        self.db.add_all([self.user, self.other_user, self.challenge])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)
        self.db.refresh(self.challenge)

        self.now = datetime(2026, 5, 10, 12, 0, 0)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def make_tournament(self, competition_type="individual", starts_at=None, ends_at=None, limit=None):
        tournament = models.Tournament(
            title="Test tournament",
            description="Tournament test",
            competition_type=competition_type,
            starts_at=starts_at or self.now - timedelta(hours=1),
            ends_at=ends_at or self.now + timedelta(hours=2),
            status="open",
            max_participants=limit,
            created_by_user_id=self.user.id,
        )
        self.db.add(tournament)
        self.db.flush()
        self.db.add(models.TournamentChallenge(
            tournament_id=tournament.id,
            challenge_id=self.challenge.id,
            points=75,
        ))
        self.db.commit()
        self.db.refresh(tournament)
        return tournament

    def test_individual_tournament_awards_separate_points_and_ranks_player(self):
        tournament = self.make_tournament()
        self.db.add(models.TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user.id,
        ))
        self.db.commit()

        awarded = record_tournament_solve(
            self.db, self.user, self.challenge, solved_at=self.now
        )
        self.db.commit()

        self.assertEqual(awarded, 75)
        self.assertEqual(self.user.score, 321)
        self.assertEqual(self.user.xp, 75)
        rows, teams = tournament_leaderboards(self.db, tournament)
        self.assertEqual(teams, [])
        self.assertEqual(rows[0]["name"], "tournament-user")
        self.assertEqual(rows[0]["points"], 75)
        self.assertEqual(rows[0]["solves"], 1)

    def test_same_challenge_is_credited_only_once_per_individual(self):
        tournament = self.make_tournament()
        self.db.add(models.TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user.id,
        ))
        self.db.commit()

        first = record_tournament_solve(self.db, self.user, self.challenge, self.now)
        self.db.commit()
        second = record_tournament_solve(self.db, self.user, self.challenge, self.now)
        self.db.commit()

        self.assertEqual(first, 75)
        self.assertEqual(second, 0)
        self.assertEqual(
            self.db.query(models.TournamentSolve)
            .filter_by(tournament_id=tournament.id)
            .count(),
            1,
        )

    def test_team_solve_counts_for_team_and_individual_solver(self):
        tournament = self.make_tournament(competition_type="team")
        team = models.Team(
            name="Packet Hunters",
            description="",
            invite_code="invite-test",
            owner_user_id=self.user.id,
        )
        self.db.add(team)
        self.db.flush()
        self.db.add_all([
            models.TeamMember(team_id=team.id, user_id=self.user.id, role="leader"),
            models.TeamMember(team_id=team.id, user_id=self.other_user.id, role="member"),
            models.TournamentTeamParticipant(tournament_id=tournament.id, team_id=team.id),
            models.TournamentParticipant(tournament_id=tournament.id, user_id=self.user.id),
            models.TournamentParticipant(tournament_id=tournament.id, user_id=self.other_user.id),
        ])
        self.db.commit()

        awarded = record_tournament_solve(self.db, self.user, self.challenge, self.now)
        self.db.commit()
        second_solver = record_tournament_solve(self.db, self.other_user, self.challenge, self.now)
        self.db.commit()

        individual, teams = tournament_leaderboards(self.db, tournament)
        self.assertEqual(awarded, 75)
        self.assertEqual(second_solver, 0)
        self.assertEqual(teams[0]["name"], "Packet Hunters")
        self.assertEqual(teams[0]["points"], 75)
        self.assertEqual(teams[0]["solves"], 1)
        self.assertEqual(individual[0]["name"], "tournament-user")
        self.assertEqual(individual[0]["points"], 75)
        self.assertEqual(self.user.score, 321)
        self.assertEqual(self.user.xp, 75)

    def test_solve_outside_scheduled_window_is_not_credited(self):
        tournament = self.make_tournament(
            starts_at=self.now + timedelta(minutes=1),
            ends_at=self.now + timedelta(hours=2),
        )
        self.db.add(models.TournamentParticipant(
            tournament_id=tournament.id,
            user_id=self.user.id,
        ))
        self.db.commit()

        awarded = record_tournament_solve(self.db, self.user, self.challenge, self.now)
        self.db.commit()

        self.assertEqual(awarded, 0)
        self.assertEqual(self.db.query(models.TournamentSolve).count(), 0)

    def test_previously_solved_challenge_can_count_in_a_live_tournament(self):
        now = datetime.utcnow()
        tournament = self.make_tournament(
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(hours=1),
        )
        self.db.add_all([
            models.TournamentParticipant(
                tournament_id=tournament.id,
                user_id=self.user.id,
            ),
            models.Solve(
                user_id=self.user.id,
                challenge_id=self.challenge.id,
                timestamp=now - timedelta(days=3),
            ),
        ])
        self.db.commit()

        result = record_flag_submission(
            self.db,
            self.user,
            self.challenge,
            "CTF{tournament}",
        )

        self.assertTrue(result["already_solved"])
        self.assertEqual(result["points_awarded"], 0)
        self.assertEqual(result["tournament_points_awarded"], 75)
        self.assertEqual(self.user.score, 321)
        self.assertEqual(self.user.xp, 75)
        self.assertEqual(
            self.db.query(models.TournamentSolve)
            .filter_by(tournament_id=tournament.id)
            .count(),
            1,
        )

    def test_registration_respects_start_time_and_capacity(self):
        tournament = self.make_tournament(
            starts_at=self.now + timedelta(hours=1),
            ends_at=self.now + timedelta(hours=2),
            limit=1,
        )
        join_tournament(self.db, self.user, tournament, now=self.now)
        self.db.commit()
        self.assertEqual(registered_count(self.db, tournament), 1)

        with self.assertRaises(TournamentError):
            join_tournament(self.db, self.other_user, tournament, now=self.now)

    def test_team_registration_requires_leader(self):
        tournament = self.make_tournament(
            competition_type="team",
            starts_at=self.now + timedelta(hours=1),
            ends_at=self.now + timedelta(hours=2),
        )
        team = models.Team(
            name="Team Test",
            description="",
            invite_code="invite-test-2",
            owner_user_id=self.user.id,
        )
        self.db.add(team)
        self.db.flush()
        self.db.add_all([
            models.TeamMember(team_id=team.id, user_id=self.user.id, role="leader"),
            models.TeamMember(team_id=team.id, user_id=self.other_user.id, role="member"),
        ])
        self.db.commit()

        with self.assertRaises(TournamentError):
            join_tournament(self.db, self.other_user, tournament, now=self.now)
        join_tournament(self.db, self.user, tournament, now=self.now)
        self.db.commit()
        self.assertEqual(registered_count(self.db, tournament), 1)
        self.assertEqual(
            self.db.query(models.TournamentParticipant)
            .filter_by(tournament_id=tournament.id)
            .count(),
            2,
        )


if __name__ == "__main__":
    unittest.main()
