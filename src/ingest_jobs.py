"""Fetch a bounded number of pages and preserve raw job records in S3."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.config import get_jsearch_headers, get_s3_bucket_name, get_s3_client
from src.fetch_jobs import fetch_page


def ingest_jobs(query: str, max_pages: int = 1) -> list:
    """Store each nonempty page as UTF-8 JSON and return its S3 object key.

    Stops at the first empty page or max_pages, whichever comes first. Each
    invocation gets a distinct raw/YYYY-MM-DD/<run-id>/ prefix so repeated
    searches do not overwrite earlier runs. Pages contain unmodified job
    dictionaries, without transformations or database writes.

    Failures propagate and stop further fetching. Pages already stored remain
    in S3; a new invocation starts a new run, not a resume of the failed run.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    bucket = get_s3_bucket_name()
    get_jsearch_headers()  # Validate before creating the AWS client.
    s3 = get_s3_client()
    date = datetime.now(timezone.utc).date().isoformat()
    prefix = f"raw/{date}/{uuid4().hex}"
    keys = []
    for page in range(1, max_pages + 1):
        jobs = fetch_page(query, page=page)
        if not jobs:
            break
        key = f"{prefix}/page_{page}.json"
        body = json.dumps(jobs, ensure_ascii=False, allow_nan=False).encode("utf-8")
        s3.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType="application/json"
        )
        keys.append(key)
    return keys
