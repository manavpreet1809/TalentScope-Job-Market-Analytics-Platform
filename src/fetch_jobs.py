"""Fetch one page from JSearch through RapidAPI, without storing results."""

import requests

from src.config import get_jsearch_headers


API_URL = "https://jsearch.p.rapidapi.com/search"
REQUEST_TIMEOUT_SECONDS = 15


class JSearchError(RuntimeError):
    """A request failed or JSearch returned an unexpected response."""


def fetch_page(query: str, page: int = 1) -> list:
    """Return one numbered page of raw job dictionaries for a nonempty query.

    Makes one request, with no retries or redirects. Errors omit response
    bodies and underlying exception details to avoid exposing credentials.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    headers = get_jsearch_headers()
    try:
        response = requests.get(
            API_URL,
            headers=headers,
            params={"query": query.strip(), "page": page, "num_pages": 1},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.Timeout:
        raise JSearchError("JSearch request timed out") from None
    except requests.RequestException:
        raise JSearchError("Unable to complete JSearch request") from None

    try:
        if not 200 <= response.status_code < 300:
            raise JSearchError(
                f"JSearch request failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise JSearchError("JSearch returned invalid JSON") from None
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            raise JSearchError("JSearch returned an unsuccessful response")
        jobs = payload.get("data")
        if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
            raise JSearchError("JSearch returned an invalid job list")
        return jobs
    finally:
        response.close()
