"""Offline checks using synthetic database settings."""

import os
import unittest
from unittest.mock import patch

from src.config import get_database_url, get_db_engine


class DatabaseConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "DB_HOST": "localhost",
            "DB_NAME": "test_database",
            "DB_USER": "test_user",
            "DB_PASSWORD": "synthetic@:/?#% password",
        }, clear=True)
        self.environment.start()
        get_db_engine.cache_clear()

    def tearDown(self):
        get_db_engine.cache_clear()
        self.environment.stop()

    def test_special_characters_are_preserved_and_password_is_redacted(self):
        url = get_database_url()
        self.assertEqual(url.password, os.environ["DB_PASSWORD"])
        self.assertEqual(url.port, 5432)
        self.assertNotIn(os.environ["DB_PASSWORD"], str(url))
        self.assertIn("***", str(url))

    def test_missing_settings_report_names_only(self):
        del os.environ["DB_HOST"]
        with self.assertRaisesRegex(ValueError, "Missing required database settings: DB_HOST"):
            get_database_url()

    def test_blank_required_setting_is_rejected(self):
        os.environ["DB_NAME"] = "  "
        with self.assertRaisesRegex(ValueError, "DB_NAME"):
            get_database_url()

    def test_invalid_ports_are_rejected_without_echoing_values(self):
        for value in ("invalid", "", "0", "65536"):
            with self.subTest(value=value):
                os.environ["DB_PORT"] = value
                with self.assertRaisesRegex(ValueError, "^DB_PORT must be an integer between 1 and 65535$"):
                    get_database_url()

    def test_custom_port(self):
        os.environ["DB_PORT"] = "5433"
        self.assertEqual(get_database_url().port, 5433)

    def test_engine_is_cached_and_does_not_connect(self):
        with patch("psycopg2.connect", side_effect=AssertionError("Unexpected connection")):
            engine = get_db_engine()
            try:
                self.assertIs(engine, get_db_engine())
                self.assertTrue(engine.hide_parameters)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
