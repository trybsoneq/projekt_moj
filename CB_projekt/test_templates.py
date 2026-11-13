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


if __name__ == "__main__":
    unittest.main()
