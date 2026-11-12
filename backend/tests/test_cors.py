from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from backend.github import GitHubServerError


@override_settings(CORS_ALLOWED_ORIGINS=[
    "http://localhost:5173", "http://127.0.0.1:5173",
])
class CorsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = patch("backend.views.RepositoryEvaluator")
        self.evaluate = patcher.start().return_value.evaluate
        self.addCleanup(patcher.stop)
        self.evaluate.return_value = {
            "repository": {}, "assessment": {}, "metrics": {},
            "meta": {"errors": []},
        }

    def test_allowed_origins_and_get(self):
        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            with self.subTest(origin=origin):
                response = self.client.get("/api/evaluate/", {"repo": "a/b"},
                                           HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
                self.assertNotIn("Access-Control-Allow-Credentials", response)
                self.assertIn("origin", response["Vary"].lower())
        self.evaluate.assert_called_once_with("a", "b")

    def test_disallowed_origin(self):
        response = self.client.get("/api/evaluate/", {"repo": "a/b"},
                                   HTTP_ORIGIN="https://untrusted.example")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_preflight(self):
        response = self.client.options(
            "/api/evaluate/", HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertEqual(response["Access-Control-Allow-Methods"], "GET, OPTIONS")
        self.assertIn("content-type", response["Access-Control-Allow-Headers"])
        self.assertNotIn("Access-Control-Allow-Credentials", response)
        self.evaluate.assert_not_called()

    def test_api_errors_have_cors(self):
        response = self.client.get("/api/evaluate/", HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.evaluate.side_effect = GitHubServerError("failed")
        response = self.client.get("/api/evaluate/", {"repo": "a/b"},
                                   HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_health_has_no_cors(self):
        response = self.client.get("/health/", HTTP_ORIGIN="http://localhost:5173")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_normal_get_without_origin(self):
        response = self.client.get("/api/evaluate/", {"repo": "a/b"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", response)
