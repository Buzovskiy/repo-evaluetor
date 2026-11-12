"""Read-only evaluation API; transport and assessment remain in their services."""

from copy import deepcopy
import time

from django.core.cache import cache
from django.http import JsonResponse

from .api_errors import json_error, upstream_error, upstream_details, retry_seconds
from .evaluator import RepositoryEvaluator
from .github import GitHubError, RateLimitExceeded
from .repository_input import parse_repository

CACHE_TTL = 15 * 60


def remember_limit(headers):
    seconds = retry_seconds(headers)
    seconds = seconds if seconds is not None else 60
    if seconds > 0:
        cache.set("github:cooldown", time.time() + seconds, timeout=seconds)


def evaluate(request):
    if request.method != "GET":
        response = json_error(405, "METHOD_NOT_ALLOWED", "Only GET is supported.")
        response["Allow"] = "GET"
        return response
    try:
        owner, repo = parse_repository(request.GET)
    except ValueError:
        return json_error(400, "INVALID_REPOSITORY",
                          "Provide exactly one valid GitHub repository as repo.")
    key = f"evaluation:v1:{owner}/{repo}"
    result = cache.get(key)
    cached = result is not None
    if not cached:
        deadline = cache.get("github:cooldown")
        if deadline is not None:
            return upstream_details("RateLimitExceeded", {"X-RateLimit-Reset": str(deadline)})
        try:
            result = RepositoryEvaluator().evaluate(owner, repo)
        except GitHubError as error:
            if isinstance(error, RateLimitExceeded):
                remember_limit(error.rate_limit_headers)
            return upstream_error(error)
        errors = result["meta"].get("errors", [])
        for error in errors:
            if error["type"] == "RateLimitExceeded":
                remember_limit(error["rate_limit_headers"])
        # Metadata alone cannot provide an activity/release assessment.
        if (any(error["endpoint"] == "commits" for error in errors)
                and any(error["endpoint"] in {"releases/latest", "tags", "tag_commit"} for error in errors)):
            priority = {"RateLimitExceeded": 0, "GitHubTimeout": 1}
            error = min(errors, key=lambda item: priority.get(item["type"], 2))
            return upstream_details(error["type"], error["rate_limit_headers"])
        if not errors:
            cache.set(key, deepcopy(result), timeout=CACHE_TTL)
    result = deepcopy(result)
    result["meta"]["cached"] = cached
    response = JsonResponse(result)
    response["Cache-Control"] = "no-store"
    return response
