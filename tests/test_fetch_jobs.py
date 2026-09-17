"""Single-page client tests: every HTTP call is mocked."""

import os
import unittest
from unittest.mock import Mock, patch

import requests

from src.config import get_jsearch_headers
from src.fetch_jobs import API_URL, JSearchError, fetch_page


class JSearchTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"RAPIDAPI_KEY": "synthetic-test-key"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        http = patch("src.fetch_jobs.requests.get")
        self.get = http.start()
        self.addCleanup(http.stop)
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"status": "OK", "data": [{"job_id": "example"}]}
        self.get.return_value = self.response

    def test_fetches_exactly_one_page_and_preserves_raw_jobs(self):
        jobs = fetch_page("  developer in Edmonton  ")
        self.assertIs(jobs, self.response.json.return_value["data"])
        self.get.assert_called_once_with(
            API_URL,
            headers={"X-RapidAPI-Key": "synthetic-test-key", "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
            params={"query": "developer in Edmonton", "page": 1, "num_pages": 1},
            timeout=15,
            allow_redirects=False,
        )
        self.response.close.assert_called_once()

    def test_empty_results_are_valid(self):
        self.response.json.return_value["data"] = []
        self.assertEqual(fetch_page("developer"), [])

    def test_invalid_query_does_not_call_api(self):
        for query in ("", "  ", None, 1):
            with self.subTest(query=query), self.assertRaises(ValueError):
                fetch_page(query)
        self.get.assert_not_called()

    def test_missing_key_does_not_call_api(self):
        for value in ("", "  "):
            os.environ["RAPIDAPI_KEY"] = value
            with self.assertRaisesRegex(ValueError, "RAPIDAPI_KEY"):
                fetch_page("developer")
        self.get.assert_not_called()

    def test_host_setting_is_validated(self):
        os.environ["RAPIDAPI_HOST"] = "jsearch.p.rapidapi.com"
        self.assertEqual(get_jsearch_headers()["X-RapidAPI-Host"], "jsearch.p.rapidapi.com")
        os.environ["RAPIDAPI_HOST"] = "invalid.example"
        with self.assertRaisesRegex(ValueError, "RAPIDAPI_HOST"):
            fetch_page("developer")
        self.get.assert_not_called()

    def test_multiline_key_is_rejected(self):
        os.environ["RAPIDAPI_KEY"] = "synthetic\nkey"
        with self.assertRaisesRegex(ValueError, "single-line"):
            fetch_page("developer")
        self.get.assert_not_called()

    def test_http_errors_and_redirects_are_not_retried(self):
        for status in (301, 401, 403, 429, 500):
            with self.subTest(status=status):
                self.get.reset_mock()
                self.response.status_code = status
                with self.assertRaisesRegex(JSearchError, f"HTTP {status}"):
                    fetch_page("developer")
                self.get.assert_called_once()
                self.response.close.assert_called_once()
        self.response.json.assert_not_called()

    def test_network_errors_are_sanitized_and_not_retried(self):
        for error, message in (
            (requests.Timeout("synthetic-test-key"), "JSearch request timed out"),
            (requests.ConnectionError("synthetic-test-key"), "Unable to complete JSearch request"),
        ):
            with self.subTest(error=type(error).__name__):
                self.get.reset_mock()
                self.get.side_effect = error
                with self.assertRaises(JSearchError) as caught:
                    fetch_page("developer")
                self.assertEqual(str(caught.exception), message)
                self.get.assert_called_once()

    def test_invalid_json(self):
        self.response.json.side_effect = ValueError("synthetic response body")
        with self.assertRaisesRegex(JSearchError, "^JSearch returned invalid JSON$"):
            fetch_page("developer")
        self.response.close.assert_called_once()

    def test_invalid_response_shapes(self):
        for payload in ([], {}, {"status": "ERROR", "data": []},
                        {"status": "OK"}, {"status": "OK", "data": None},
                        {"status": "OK", "data": {}}, {"status": "OK", "data": [1]}):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                with self.assertRaises(JSearchError):
                    fetch_page("developer")


if __name__ == "__main__":
    unittest.main()
