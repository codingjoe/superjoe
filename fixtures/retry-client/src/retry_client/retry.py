"""Retrying HTTP requests."""

import time

import httpx

ATTEMPTS = 3
BACKOFF_SECS = 0.5


def fetch(url: str) -> httpx.Response:
    """Fetch a URL, retrying until the server answers."""
    for attempt in range(ATTEMPTS):
        response = httpx.get(url)
        if response.is_success:
            return response
        time.sleep(BACKOFF_SECS * 2**attempt)
    return response
