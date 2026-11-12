import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.core.cache import cache

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

    def test_concentration_boundaries(self):
        for largest, total, expected in [(4, 10, "healthy"), (5, 10, "warning"),
                                          (7, 10, "warning"), (8, 10, "critical"),
                                          (79, 99, "warning")]:
            with self.subTest(largest=largest, total=total):
                authors = [1] * largest + list(range(2, total - largest + 2))
                self.github.get_commits.return_value = CommitPage(
                    [{"author": {"id": identity}} for identity in authors], False)
                result = self.evaluate()["metrics"]["concentration"]
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["value"], round(largest / total * 100, 1))

    def test_unreliable_concentration(self):
        for author in [None, {}, {"login": "a"}, {"id": "1"}, {"id": True}]:
            with self.subTest(author=author):
                self.commits(12)
                self.github.get_commits.return_value.commits[0]["author"] = author
                self.assertEqual(self.evaluate()["metrics"]["concentration"]["status"], "unknown")
        for count, more in [(0, False), (9, False), (9, True)]:
            self.commits(count, more)
            result = self.evaluate()["metrics"]["concentration"]
            self.assertIsNone(result["value"])
            self.assertEqual(result["sample_size"], count)
            self.assertEqual(result["is_sample"], more)

    def test_concentration_sample_metadata_and_thresholds(self):
        for size, more, largest, expected in [
            (10, False, 4, "healthy"), (50, False, 30, "warning"),
            (100, False, 35, "healthy"), (100, True, 35, "healthy"),
            (100, True, 50, "warning"), (100, True, 80, "critical"),
        ]:
            with self.subTest(size=size, more=more, largest=largest):
                self.github.reset_mock()
                authors = [1] * largest + list(range(2, size - largest + 2))
                self.github.get_commits.return_value = CommitPage(
                    [{"author": {"id": identity}} for identity in authors], more)
                result = self.evaluate()
                concentration = result["metrics"]["concentration"]
                self.assertEqual(concentration["status"], expected)
                self.assertEqual(concentration["value"], round(largest / size * 100, 1))
                self.assertEqual(concentration["sample_size"], size)
                self.assertEqual(concentration["is_sample"], more)
                self.assertEqual(result["meta"]["commits_complete"], not more)
                self.assertEqual(result["assessment"]["status"], expected)
                if more:
                    self.assertIn("sample", concentration["message"])
                    self.assertIn("sample", result["assessment"]["summary"])
                    self.assertIn("not the complete 90-day history", concentration["message"])
                else:
                    self.assertIn(f"the {size} commits analyzed", concentration["message"])
                self.github.get_commits.assert_called_once_with(
                    "a", "b", since=self.now - timedelta(days=90), until=self.now, page=1)
                self.github.get_repository.assert_called_once()
                self.github.get_latest_release.assert_called_once()

    def test_unattributed_sample_retains_metadata(self):
        self.commits(100, True)
        del self.github.get_commits.return_value.commits[-1]["author"]
        result = self.evaluate()["metrics"]["concentration"]
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["value"])
        self.assertEqual(result["sample_size"], 100)
        self.assertTrue(result["is_sample"])

    def test_api_serializes_sample_result(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.commits(100, True)
        with patch("backend.views.RepositoryEvaluator", return_value=self.evaluator):
            response = self.client.get("/api/evaluate/", {"repo": "a/b"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"repository", "assessment", "metrics", "meta"})
        self.assertEqual(data["metrics"]["concentration"]["sample_size"], 100)
        self.assertTrue(data["metrics"]["concentration"]["is_sample"])
        self.assertFalse(data["meta"]["commits_complete"])
        self.github.get_commits.assert_called_once()

    def test_account_ids_ignore_names_and_committers(self):
        self.commits(12)
        for index, commit in enumerate(self.github.get_commits.return_value.commits):
            commit["author"]["login"] = f"renamed-{index}"
        self.assertEqual(self.evaluate()["metrics"]["concentration"]["value"], 33.3)

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
        result = self.evaluate()
        for name in ("maintenance", "concentration", "release"):
            self.assertEqual(result["metrics"][name]["status"], "unknown")
            self.assertIsNone(result["metrics"][name]["value"])
        self.assertIsNone(result["meta"]["commits_complete"])
        self.assertEqual(result["metrics"]["concentration"]["sample_size"], 0)
        self.assertFalse(result["metrics"]["concentration"]["is_sample"])
        self.assertEqual(result["meta"]["errors"], [
            {"endpoint": "commits", "type": "RateLimitExceeded", "status": 429,
             "rate_limit_headers": headers},
            {"endpoint": "releases/latest", "type": "GitHubServerError", "status": 503,
             "rate_limit_headers": {}},
        ])

    def test_missing_release_is_not_service_failure(self):
        self.github.get_latest_release.side_effect = LatestReleaseNotFound("missing", status=404)
        result = self.evaluate()
        self.assertEqual(result["metrics"]["release"]["status"], "unknown")
        self.assertEqual(result["meta"]["errors"], [])

    def test_naive_evaluation_time_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("a", "b", now=datetime(2026, 1, 1))
        self.github.get_repository.assert_not_called()
