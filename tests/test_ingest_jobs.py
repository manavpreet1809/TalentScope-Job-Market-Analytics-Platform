"""Offline ingestion tests; neither JSearch nor AWS is contacted."""

import json
import os
import unittest
from unittest.mock import call, patch

from src.config import get_s3_bucket_name, get_s3_client
from src.fetch_jobs import JSearchError
from src.ingest_jobs import ingest_jobs


class IngestionTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "RAPIDAPI_KEY": "synthetic-test-key",
            "S3_BUCKET_NAME": "synthetic-test-bucket",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("fetch_page", "get_s3_client"):
            mock_patch = patch("src.ingest_jobs." + name)
            setattr(self, name, mock_patch.start())
            self.addCleanup(mock_patch.stop)
        self.s3 = self.get_s3_client.return_value

    def test_multiple_pages_are_preserved_as_separate_raw_json_objects(self):
        pages = [[{"job_id": "one", "title": "Développeur", "salary": None}],
                 [{"job_id": "two", "nested": {"skills": ["Python"]}}]]
        self.fetch_page.side_effect = pages
        keys = ingest_jobs("developer", max_pages=2)
        self.assertEqual(self.fetch_page.call_args_list,
                         [call("developer", page=1), call("developer", page=2)])
        self.assertEqual(len(keys), 2)
        for number, (request, expected) in enumerate(zip(self.s3.put_object.call_args_list, pages), 1):
            kwargs = request.kwargs
            self.assertEqual(kwargs["Bucket"], "synthetic-test-bucket")
            self.assertEqual(kwargs["ContentType"], "application/json")
            self.assertEqual(json.loads(kwargs["Body"].decode("utf-8")), expected)
            self.assertEqual(kwargs["Key"], keys[number - 1])
            self.assertRegex(kwargs["Key"], rf"^raw/\d{{4}}-\d{{2}}-\d{{2}}/[0-9a-f]{{32}}/page_{number}\.json$")
        self.assertEqual(keys[0].rsplit("/", 1)[0], keys[1].rsplit("/", 1)[0])

    def test_stops_on_empty_page(self):
        self.fetch_page.side_effect = [[{"job_id": "one"}], [], [{"job_id": "unused"}]]
        self.assertEqual(len(ingest_jobs("developer", max_pages=5)), 1)
        self.assertEqual(self.fetch_page.call_count, 2)
        self.s3.put_object.assert_called_once()

    def test_empty_first_page_writes_nothing(self):
        self.fetch_page.return_value = []
        self.assertEqual(ingest_jobs("developer", max_pages=3), [])
        self.fetch_page.assert_called_once()
        self.s3.put_object.assert_not_called()

    def test_default_is_one_page_and_repeated_runs_use_distinct_keys(self):
        self.fetch_page.return_value = [{"job_id": "one"}]
        first = ingest_jobs("developer")
        second = ingest_jobs("developer")
        self.assertNotEqual(first, second)
        self.assertEqual(self.fetch_page.call_args_list, [call("developer", page=1)] * 2)

    def test_invalid_input_causes_no_external_calls(self):
        for limit in (0, -1, True, 2.5, "2", None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ingest_jobs("developer", max_pages=limit)
        for query in ("", " ", None):
            with self.subTest(query=query), self.assertRaises(ValueError):
                ingest_jobs(query)
        self.get_s3_client.assert_not_called()
        self.fetch_page.assert_not_called()

    def test_missing_settings_fail_before_external_calls(self):
        for name in ("S3_BUCKET_NAME", "RAPIDAPI_KEY"):
            with patch.dict(os.environ, {name: " "}):
                with self.assertRaisesRegex(ValueError, name):
                    ingest_jobs("developer")
        self.get_s3_client.assert_not_called()
        self.fetch_page.assert_not_called()

    def test_api_failure_keeps_prior_page_and_stops(self):
        self.fetch_page.side_effect = [[{"job_id": "one"}], JSearchError("HTTP 429")]
        with self.assertRaises(JSearchError):
            ingest_jobs("developer", max_pages=3)
        self.assertEqual(self.fetch_page.call_count, 2)
        self.s3.put_object.assert_called_once()

    def test_storage_failure_stops_before_fetching_another_page(self):
        self.fetch_page.return_value = [{"job_id": "one"}]
        self.s3.put_object.side_effect = RuntimeError("synthetic storage failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic storage failure"):
            ingest_jobs("developer", max_pages=3)
        self.fetch_page.assert_called_once()
        self.s3.put_object.assert_called_once()


class StorageConfigTests(unittest.TestCase):
    def test_bucket_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "S3_BUCKET_NAME"):
                get_s3_bucket_name()

    def test_client_is_cached_and_uses_standard_credentials(self):
        get_s3_client.cache_clear()
        self.addCleanup(get_s3_client.cache_clear)
        with patch("boto3.client") as factory:
            self.assertIs(get_s3_client(), get_s3_client())
            factory.assert_called_once_with("s3")


if __name__ == "__main__":
    unittest.main()
