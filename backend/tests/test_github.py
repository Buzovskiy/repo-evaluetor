import json
from datetime import datetime, timezone
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from backend.github import (
    GitHubClient, GitHubError, GitHubNetworkError, GitHubServerError,
    GitHubTimeout, InvalidResponse, LatestReleaseNotFound, RateLimitExceeded,
    RepositoryNotFound,
)


@override_settings(GITHUB_TOKEN="")
class GitHubClientTests(SimpleTestCase):
    def setUp(self):
        self.mock = patch("backend.github.requests.Session.get").start()
        self.addCleanup(patch.stopall)
        self.github = GitHubClient()
        self.since = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def respond(self, data, status=200, headers=None):
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(data).encode()
        response.headers.update(headers or {})
        self.mock.return_value = response

    def test_repository_unauthenticated(self):
        data = {"id": 1, "full_name": "a/b", "default_branch": "main", "license": None}
        self.respond(data)
        self.assertEqual(self.github.get_repository("a", "b"), data)
        args, kwargs = self.mock.call_args
        self.assertEqual(args, ("https://api.github.com/repos/a/b",))
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["Accept"], "application/vnd.github+json")
        self.assertEqual(kwargs["timeout"], (3.05, 15))
        self.assertFalse(kwargs["allow_redirects"])

    @override_settings(GITHUB_TOKEN="test-placeholder")
    def test_authenticated_release(self):
        data = {"id": 1, "tag_name": "v1", "draft": False,
                "prerelease": False, "published_at": None, "name": None}
        self.respond(data)
        self.assertEqual(GitHubClient(base_url="https://example.test/api/").get_latest_release("a", "b"), data)
        args, kwargs = self.mock.call_args
        self.assertEqual(args[0], "https://example.test/api/repos/a/b/releases/latest")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-placeholder")

    def test_commits_and_pagination(self):
        data = [{"sha": "abc", "author": None,
                 "commit": {"author": {"name": "A", "email": "a@example.test"}}}]
        self.respond(data, headers={"Link": '<https://api.github.com/repos/a/b/commits?page=3>; rel="next"'})
        result = self.github.get_commits("a", "b", since=self.since, until=self.since, page=2)
        self.assertTrue(result.has_next)
        self.assertEqual(result.commits, data)
        self.assertEqual(self.mock.call_args.args[0], "https://api.github.com/repos/a/b/commits")
        self.assertEqual(self.mock.call_args.kwargs["params"], {
            "since": "2026-01-01T00:00:00Z", "until": "2026-01-01T00:00:00Z",
            "per_page": 100, "page": 2})
        self.mock.assert_called_once()

    def test_last_empty_page(self):
        self.respond([])
        self.assertFalse(self.github.get_commits("a", "b", since=self.since).has_next)

    def test_missing_release(self):
        self.respond({"message": "Not Found"}, 404)
        with self.assertRaises(LatestReleaseNotFound):
            self.github.get_latest_release("a", "b")

    def test_http_errors(self):
        for status, headers, body, error in [
            (404, {}, {}, RepositoryNotFound),
            (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Limit": "60",
                   "X-RateLimit-Reset": "123"}, {}, RateLimitExceeded),
            (403, {}, {"message": "secondary rate limit"}, RateLimitExceeded),
            (429, {"Retry-After": "60"}, {}, RateLimitExceeded),
            (403, {}, {}, GitHubError),
            (500, {}, {}, GitHubServerError),
            (409, {}, {}, GitHubError),
        ]:
            with self.subTest(status=status, headers=headers):
                self.respond(body, status, headers)
                with self.assertRaises(error) as caught:
                    self.github.get_repository("a", "b")
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(caught.exception.rate_limit_headers, headers)

    def test_network_errors_are_sanitized(self):
        for source, expected in [(requests.Timeout, GitHubTimeout),
                                 (requests.ConnectionError, GitHubNetworkError)]:
            self.mock.side_effect = source("sensitive information")
            with self.assertRaises(expected) as caught:
                self.github.get_repository("a", "b")
            self.assertNotIn("sensitive", str(caught.exception))

    def test_malformed_responses(self):
        for data in [None, [], {}, {"id": "wrong"}]:
            self.respond(data)
            with self.assertRaises(InvalidResponse):
                self.github.get_repository("a", "b")
        self.respond({})
        self.mock.return_value._content = b"<html>invalid JSON</html>"
        with self.assertRaises(InvalidResponse):
            self.github.get_repository("a", "b")

    def test_invalid_inputs_do_not_request(self):
        with self.assertRaises(ValueError):
            self.github.get_commits("a", "b", since=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            self.github.get_commits("a", "b", since=self.since, page=0)
        self.mock.assert_not_called()

    def test_health_unchanged(self):
        self.assertEqual(self.client_class().get("/health/").json(), {"status": "ok"})
