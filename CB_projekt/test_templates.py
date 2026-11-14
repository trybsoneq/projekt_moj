import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class TemplateCompilationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )

    def test_base_template_compiles(self):
        self.environment.get_template("zerofour/base.html")

    def test_admin_template_compiles(self):
        self.environment.get_template("zerofour/admin.html")

    def test_infrastructure_template_compiles(self):
        self.environment.get_template("zerofour/infrastructure.html")

    def test_profile_template_compiles(self):
        self.environment.get_template("zerofour/profile.html")

    def test_admin_activity_template_compiles(self):
        self.environment.get_template("zerofour/admin_activity.html")

    def test_scoreboard_template_compiles(self):
        self.environment.get_template("zerofour/scoreboard.html")

    def test_profile_template_contains_gamification_sections(self):
        source = (TEMPLATE_DIR / "zerofour" / "profile.html").read_text(encoding="utf-8")
        self.assertIn("Odznaki i osiągnięcia", source)
        self.assertIn("Poziom doświadczenia", source)
        self.assertIn("Aktualna seria", source)

    def test_challenge_template_compiles(self):
        self.environment.get_template("zerofour/challenge.html")

    def test_tournament_templates_compile(self):
        for name in (
            "zerofour/teams.html",
            "zerofour/tournaments.html",
            "zerofour/tournament_detail.html",
            "zerofour/admin_tournaments.html",
            "zerofour/admin_tournament_detail.html",
        ):
            self.environment.get_template(name)

    def test_base_contains_team_and_tournament_navigation(self):
        source = (TEMPLATE_DIR / "zerofour" / "base.html").read_text(encoding="utf-8")
        self.assertIn('href="/tournaments"', source)
        self.assertIn('href="/teams"', source)
        self.assertIn('href="/admin/tournaments"', source)

    def test_base_template_loads_custom_navigation_css(self):
        base_path = TEMPLATE_DIR / "zerofour" / "base.html"
        css_path = TEMPLATE_DIR / "zerofour" / "assets" / "css" / "custom.css"
        source = base_path.read_text(encoding="utf-8")
        css = css_path.read_text(encoding="utf-8")
        self.assertIn("/assets/css/custom.css", source)
        self.assertIn("#nav > ul", css)
        self.assertIn("flex-wrap: wrap", css)


if __name__ == "__main__":
    unittest.main()
