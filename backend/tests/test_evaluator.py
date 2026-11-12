import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from django.test import SimpleTestCase

from backend.evaluator import RepositoryEvaluator
from backend.github import (
    CommitPage, GitHubClient, GitHubServerError, LatestReleaseNotFound,
    RateLimitExceeded, RepositoryNotFound,
)


class RepositoryEvaluatorTests(SimpleTestCase):
    def setUp(self):
        self.github = Mock(spec=GitHubClient)
        self.github.get_repository.return_value = {
            "full_name": "a/b", "html_url": "https://github.com/a/b",
            "description": None, "default_branch": "main", "stargazers_count": 12,
            "archived": False,
        }
        self.now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        self.github.get_latest_release.return_value = {"published_at": "2026-10-01T00:00:00Z"}
        self.github.get_tags.return_value = []
        self.commits(12)
        self.evaluator = RepositoryEvaluator(self.github)

    def commits(self, count, next_page=False):
        self.github.get_commits.return_value = CommitPage(
            [{"author": {"id": i % 3 + 1}, "commit": {"author": {"name": "Same"}},
              "committer": {"id": 99}} for i in range(count)], next_page)

    def evaluate(self):
        return self.evaluator.evaluate("a", "b", now=self.now)

    def test_maintenance_boundaries(self):
        for count, more, status, value in [
            (0, False, "critical", 0), (1, False, "warning", 1),
            (9, False, "warning", 9), (10, False, "healthy", 10),
            (36, False, "healthy", 36), (100, False, "healthy", 100),
            (100, True, "healthy", "100+"),
        ]:
            with self.subTest(count=count, more=more):
                self.commits(count, more)
                result = self.evaluate()
                self.assertEqual(result["metrics"]["maintenance"]["status"], status)
                self.assertEqual(result["metrics"]["maintenance"]["value"], value)
                self.assertEqual(result["meta"]["commits_complete"], not more)
        self.assertEqual(self.github.get_commits.call_count, 7)
        self.github.get_commits.assert_called_with(
            "a", "b", since=self.now - timedelta(days=90), until=self.now, page=1)

    def test_release_boundaries(self):
        for date, expected in [
            ("2026-05-12T00:00:01Z", "healthy"),
            ("2026-05-12T00:00:00Z", "warning"),
            ("2026-03-01T00:00:00Z", "warning"),
            ("2025-11-12T00:00:00Z", "critical"),
            (None, "unknown"), ("garbage", "unknown"),
            ("2026-10-01", "unknown"), ("2027-01-01T00:00:00Z", "unknown"),
        ]:
            with self.subTest(date=date):
                self.github.get_latest_release.return_value = {"published_at": date}
                self.assertEqual(self.evaluate()["metrics"]["release"]["status"], expected)

    def test_calendar_month_clamping(self):
        for now, published, expected in [
            ("2024-08-31", "2024-02-29T00:00:00Z", "warning"),
            ("2024-08-31", "2024-02-29T00:00:01Z", "healthy"),
            ("2024-02-29", "2023-02-28T00:00:00Z", "critical"),
        ]:
            self.now = datetime.fromisoformat(now).replace(tzinfo=timezone.utc)
            self.github.get_latest_release.return_value = {"published_at": published}
            self.assertEqual(self.evaluate()["metrics"]["release"]["status"], expected)

    def test_archive_and_overall(self):
        for archived, expected in [(False, "healthy"), (True, "critical"),
                                   (None, "unknown"), ("false", "unknown"), (0, "unknown")]:
            self.github.get_repository.return_value["archived"] = archived
            result = self.evaluate()
            self.assertEqual(result["metrics"]["archived"]["status"], expected)
            self.assertEqual(result["assessment"]["status"], expected)
        del self.github.get_repository.return_value["archived"]
        self.assertIsNone(self.evaluate()["repository"]["archived"])

    def test_overall_priority_and_serialization(self):
        self.github.get_latest_release.return_value = {"published_at": None}
        self.assertEqual(self.evaluate()["assessment"]["status"], "unknown")
        self.commits(5)
        self.assertEqual(self.evaluate()["assessment"]["status"], "warning")
        self.commits(0)
        result = self.evaluate()
        self.assertEqual(result["assessment"]["status"], "critical")
        self.assertIn("0 commits", result["assessment"]["summary"])
        json.dumps(result)

    def test_metadata_failures_propagate(self):
        for error in [RepositoryNotFound("missing"), RateLimitExceeded("limited", status=403)]:
            self.github.get_repository.side_effect = error
            with self.assertRaises(type(error)) as caught:
                self.evaluate()
            self.assertIs(caught.exception, error)
        self.github.get_commits.assert_not_called()
        self.github.get_latest_release.assert_not_called()

    def test_partial_failures_preserve_rate_limits(self):
        headers = {"Retry-After": "60", "X-RateLimit-Remaining": "0",
                   "X-RateLimit-Limit": "60", "X-RateLimit-Reset": "123"}
        self.github.get_commits.side_effect = RateLimitExceeded("limited", status=429, headers=headers)
        self.github.get_latest_release.side_effect = GitHubServerError("failed", status=503)
        with self.assertRaises(RateLimitExceeded) as caught:
            self.evaluate()
        self.assertEqual(caught.exception.rate_limit_headers, headers)
        self.github.get_latest_release.assert_not_called()
        self.github.get_tags.assert_not_called()

    def test_missing_release_is_not_service_failure(self):
        self.github.get_latest_release.side_effect = LatestReleaseNotFound("missing", status=404)
        result = self.evaluate()
        self.assertEqual(result["metrics"]["release"]["status"], "unknown")
        self.assertEqual(result["meta"]["errors"], [])

    def test_naive_evaluation_time_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("a", "b", now=datetime(2026, 1, 1))
        self.github.get_repository.assert_not_called()

    def test_three_metrics_and_primary_source(self):
        self.github.get_latest_release.return_value["tag_name"] = "v2.0"
        result = self.evaluate()
        self.assertEqual(set(result["metrics"]), {"maintenance", "release", "archived"})
        self.assertNotIn("sample_size", json.dumps(result))
        self.assertNotIn("is_sample", json.dumps(result))
        self.assertEqual(result["assessment"]["status"], "healthy")
        self.assertEqual(result["metrics"]["release"]["source"], "github_release")
        self.assertEqual(result["metrics"]["release"]["version"], "v2.0")
        self.github.get_tags.assert_not_called()
        self.github.get_commit.assert_not_called()

    def test_tag_selection_and_fallback_triggers(self):
        for primary in [None, "bad", "2027-01-01T00:00:00Z", "missing"]:
            with self.subTest(primary=primary):
                self.github.reset_mock()
                self.github.get_latest_release.side_effect = (
                    LatestReleaseNotFound("missing") if primary == "missing" else None)
                self.github.get_latest_release.return_value = {"published_at": primary}
                self.github.get_tags.return_value = [
                    {"name": name, "commit": {"sha": name}}
                    for name in ["5.2.8", "v6.0.1", "6.0.0", "6.1-rc1", "nightly", "release-9", "6..2"]
                ]
                self.github.get_commit.return_value = {"commit": {
                    "committer": {"date": "2026-10-01T02:00:00+02:00"},
                    "author": {"date": "2000-01-01T00:00:00Z"}}}
                release = self.evaluate()["metrics"]["release"]
                self.assertEqual(release["source"], "git_tag")
                self.assertEqual(release["version"], "v6.0.1")
                self.assertEqual(release["value"], "2026-10-01T00:00:00Z")
                self.assertEqual(release["status"], "healthy")
                self.assertIn("not the tag publication date", release["message"])
                self.github.get_tags.assert_called_once_with("a", "b")
                self.github.get_commit.assert_called_once_with("a", "b", "v6.0.1")

    def test_no_recognized_tags(self):
        for names in [[], ["1.2-alpha", "1.2-beta", "1.2-rc1", "dev"],
                      ["release", "1..2", "v", "123", "1.2.3.4.5"]]:
            self.github.get_latest_release.side_effect = LatestReleaseNotFound("missing")
            self.github.get_tags.return_value = [
                {"name": name, "commit": {"sha": "abc"}} for name in names]
            release = self.evaluate()["metrics"]["release"]
            self.assertEqual(release["status"], "unknown")
            self.assertIsNone(release["source"])
            self.assertIsNone(release["version"])
        self.github.get_commit.assert_not_called()

    def test_tag_dates(self):
        self.github.get_latest_release.return_value = {"published_at": None}
        self.github.get_tags.return_value = [{"name": "1.2", "commit": {"sha": "abc"}}]
        for date, expected in [(None, "unknown"), ("bad", "unknown"),
                               ("2027-01-01T00:00:00Z", "unknown"),
                               ("2026-05-12T00:00:00Z", "warning"),
                               ("2025-11-12T00:00:00Z", "critical")]:
            self.github.get_commit.return_value = {"commit": {"committer": {"date": date}}}
            self.assertEqual(self.evaluate()["metrics"]["release"]["status"], expected)
        self.github.get_commit.return_value = {"commit": {"committer": None}}
        self.assertEqual(self.evaluate()["metrics"]["release"]["status"], "unknown")

    def test_upstream_errors_do_not_trigger_more_discovery(self):
        from backend.github import GitHubNetworkError
        for kind in [RateLimitExceeded, GitHubNetworkError, GitHubServerError]:
            self.github.reset_mock()
            self.github.get_latest_release.side_effect = kind("failed", headers={"Retry-After": "60"})
            result = self.evaluate()
            self.assertEqual(result["meta"]["errors"][0]["type"], kind.__name__)
            self.assertEqual(result["meta"]["errors"][0]["rate_limit_headers"], {"Retry-After": "60"})
            self.github.get_tags.assert_not_called()
            self.github.get_commit.assert_not_called()

    def test_fallback_failures_preserved(self):
        self.github.get_latest_release.side_effect = LatestReleaseNotFound("missing")
        self.github.get_tags.side_effect = RateLimitExceeded("limited", status=429)
        result = self.evaluate()
        self.assertEqual(result["meta"]["errors"][0]["endpoint"], "tags")
        self.github.get_commit.assert_not_called()
        self.github.get_tags.side_effect = None
        self.github.get_tags.return_value = [{"name": "1.2.3", "commit": {"sha": "abc"}}]
        self.github.get_commit.side_effect = GitHubServerError("failed", status=503)
        self.assertEqual(self.evaluate()["meta"]["errors"][0]["endpoint"], "tag_commit")
