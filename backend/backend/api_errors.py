"""Safe, consistent errors and GitHub retry metadata for the HTTP boundary."""

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from django.http import JsonResponse

from .github import RepositoryNotFound, RateLimitExceeded, GitHubTimeout


def retry_seconds(headers, now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    retry = headers.get("Retry-After")
    if retry is not None:
        try:
            if retry.isascii() and retry.isdigit():
                return int(retry)
            date = parsedate_to_datetime(retry)
            if date.utcoffset() is not None:
                return max(0, math.ceil(date.timestamp() - now))
        except (ValueError, TypeError, OverflowError):
            pass
    try:
        reset = float(headers["X-RateLimit-Reset"])
        if math.isfinite(reset) and reset >= 0:
            return max(0, math.ceil(reset - now))
    except (KeyError, ValueError, TypeError, OverflowError):
        pass
    return None


def json_error(status, code, message, retry=None):
    response = JsonResponse({"error": {
        "code": code, "message": message, "retry_after_seconds": retry,
    }}, status=status)
    response["Cache-Control"] = "no-store"
    if retry is not None:
        response["Retry-After"] = str(retry)
    return response


def upstream_error(error):
    return upstream_details(type(error).__name__, error.rate_limit_headers)


def upstream_details(kind, headers):
    if kind == RepositoryNotFound.__name__:
        return json_error(404, "REPOSITORY_NOT_FOUND", "GitHub repository was not found.")
    if kind == RateLimitExceeded.__name__:
        return json_error(429, "RATE_LIMIT_EXCEEDED", "GitHub rate limit exceeded.",
                          retry_seconds(headers))
    if kind == GitHubTimeout.__name__:
        return json_error(504, "GITHUB_TIMEOUT", "GitHub request timed out.")
    return json_error(502, "GITHUB_API_ERROR", "GitHub could not complete the request.")
