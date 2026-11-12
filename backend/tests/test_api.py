from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from backend.api_errors import retry_seconds
from backend.evaluator import RepositoryEvaluator
from backend.github import (
    CommitPage, GitHubClient, GitHubError, GitHubNetworkError, GitHubServerError,
    GitHubTimeout, InvalidResponse, RateLimitExceeded, RepositoryNotFound,
)
from unittest.mock import Mock


class EvaluationApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        github = Mock(spec=GitHubClient)
        github.get_repository.return_value = {"full_name": "django/django", "archived": False}
        github.get_tags.return_value = []
        github.get_commits.return_value = CommitPage([], False)
        github.get_latest_release.return_value = {"published_at": None}
        self.result = RepositoryEvaluator(github).evaluate("django", "django")
        self.service = patch("backend.views.RepositoryEvaluator").start()
        self.addCleanup(patch.stopall)
        self.evaluate = self.service.return_value.evaluate
        self.evaluate.return_value = self.result

    def get(self, repo="django/django"):
        return self.client.get("/api/evaluate/", {"repo": repo})

    def test_success_and_equivalent_cache_entries(self):
        original = deepcopy(self.result)
        first = self.get()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(set(first.json()["metrics"]), {"maintenance", "release", "archived"})
        expected = deepcopy(original)
        expected["meta"]["cached"] = False
        self.assertEqual(first.json(), expected)
        for value in ["Django/Django", "https://github.com/django/django",
                      "https://github.com/DJANGO/Django.git/"]:
            response = self.get(value)
            self.assertTrue(response.json()["meta"]["cached"])
        self.evaluate.assert_called_once_with("django", "django")
        self.assertEqual(self.result, original)
        self.assertNotIn("cached", cache.get("evaluation:v1:django/django")["meta"])

    def test_expiration(self):
        with patch("time.time", return_value=10000):
            self.get()
        with patch("time.time", return_value=10899):
            self.assertTrue(self.get().json()["meta"]["cached"])
        with patch("time.time", return_value=10900):
            self.assertFalse(self.get().json()["meta"]["cached"])
        self.assertEqual(self.evaluate.call_count, 2)

    def test_invalid_inputs(self):
        invalid = ["", " a/b", "a/b ", "a", "a/b/c", "-a/b", "a--b/c",
                   "a/..", "a/b%20", "a/b\\c", "https://example.com/a/b",
                   "https://github.com/a/b/issues", "https://github.com/a/b?x=1",
                   "https://github.com/a/b#", "https://user@github.com/a/b",
                   "https://github.com:443/a/b", "http://github.com/a/b",
                   "a" * 40 + "/b", "a/" + "b" * 101]
        for value in invalid:
            with self.subTest(value=value):
                response = self.get(value)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "INVALID_REPOSITORY")
        for query in ["", "?repo=a/b&repo=c/d", "?repo=a/b&extra=1"]:
            self.assertEqual(self.client.get("/api/evaluate/" + query).status_code, 400)
        self.evaluate.assert_not_called()

    def test_methods_and_health(self):
        for method in ["post", "put", "patch", "delete", "options", "head"]:
            response = getattr(self.client, method)("/api/evaluate/")
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response["Allow"], "GET")
            self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(self.client.get("/health/").json(), {"status": "ok"})

    def test_upstream_errors_not_cached(self):
        for kind, status, code in [
            (RepositoryNotFound, 404, "REPOSITORY_NOT_FOUND"),
            (RateLimitExceeded, 429, "RATE_LIMIT_EXCEEDED"),
            (GitHubTimeout, 504, "GITHUB_TIMEOUT"),
            (GitHubServerError, 502, "GITHUB_API_ERROR"),
            (GitHubNetworkError, 502, "GITHUB_API_ERROR"),
            (InvalidResponse, 502, "GITHUB_API_ERROR"),
            (GitHubError, 502, "GITHUB_API_ERROR"),
        ]:
            with self.subTest(kind=kind):
                cache.clear()
                self.evaluate.side_effect = kind("secret must not appear")
                for attempt in range(2):
                    response = self.get()
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.json(), {"error": {
                        "code": code, "message": response.json()["error"]["message"],
                        "retry_after_seconds": 60 if kind is RateLimitExceeded and attempt else None}})
                    self.assertNotIn("secret", response.content.decode())
                self.assertIsNone(cache.get("evaluation:v1:django/django"))

    def test_retry_header(self):
        self.evaluate.side_effect = RateLimitExceeded("limited", headers={"Retry-After": "60"})
        response = self.get()
        self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(response.json()["error"]["retry_after_seconds"], 60)

    def test_retry_calculation(self):
        for headers, expected in [
            ({}, None), ({"Retry-After": "bad"}, None),
            ({"X-RateLimit-Reset": "1060"}, 60),
            ({"X-RateLimit-Reset": "900"}, 0),
            ({"X-RateLimit-Reset": "nan"}, None),
            ({"Retry-After": "Thu, 01 Jan 1970 00:17:40 GMT"}, 60),
            ({"Retry-After": "-1", "X-RateLimit-Reset": "1001"}, 1),
        ]:
            self.assertEqual(retry_seconds(headers, now=1000), expected)

    def test_partial_failure_is_preserved_not_cached(self):
        self.result["meta"]["errors"] = [{
            "endpoint": "commits", "type": "GitHubServerError",
            "status": 503, "rate_limit_headers": {},
        }]
        for _ in range(2):
            response = self.get()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["meta"]["errors"], self.result["meta"]["errors"])
            self.assertFalse(response.json()["meta"]["cached"])
        self.assertEqual(self.evaluate.call_count, 2)

    def test_both_secondary_failures_return_error(self):
        self.result["meta"]["errors"] = [
            {"endpoint": "commits", "type": "GitHubServerError",
             "status": 503, "rate_limit_headers": {}},
            {"endpoint": "releases/latest", "type": "RateLimitExceeded",
             "status": 429, "rate_limit_headers": {"Retry-After": "30"}},
        ]
        for _ in range(2):
            response = self.get()
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response["Retry-After"], "30")
        self.assertEqual(self.evaluate.call_count, 1)

    def test_fallback_failure_and_commits_failure(self):
        self.result["meta"]["errors"] = [
            {"endpoint": "commits", "type": "GitHubServerError", "status": 503,
             "rate_limit_headers": {}},
            {"endpoint": "tag_commit", "type": "RateLimitExceeded", "status": 429,
             "rate_limit_headers": {"Retry-After": "30"}},
        ]
        self.assertEqual(self.get().status_code, 429)
        self.assertIsNone(cache.get("evaluation:v1:django/django"))

    def test_cooldown_expires_and_success_cache_still_works(self):
        self.get("cached/repo")
        self.evaluate.side_effect = RateLimitExceeded("limited", headers={"Retry-After": "60"})
        with patch("time.time", return_value=10000):
            self.assertEqual(self.get().status_code, 429)
            self.assertEqual(self.get("another/repo").status_code, 429)
            self.assertTrue(self.get("cached/repo").json()["meta"]["cached"])
        self.assertEqual(self.evaluate.call_count, 2)
        with patch("time.time", return_value=10061):
            self.evaluate.side_effect = None
            self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.evaluate.call_count, 3)
