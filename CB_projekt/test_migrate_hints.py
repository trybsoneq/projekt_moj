import unittest
from unittest.mock import call, patch

import migrate_hints


class HintMigrationPrerequisiteTests(unittest.TestCase):
    def test_standalone_hint_migration_runs_prior_stages_in_order(self):
        with (
            patch("migrate_roles.migrate") as migrate_roles,
            patch("migrate_docker.migrate") as migrate_docker,
            patch("migrate_activity.migrate") as migrate_activity,
        ):
            migrate_hints.migrate_prerequisites()

        self.assertEqual(
            [
                migrate_roles.call_count,
                migrate_docker.call_count,
                migrate_activity.call_count,
            ],
            [1, 1, 1],
        )


if __name__ == "__main__":
    unittest.main()
