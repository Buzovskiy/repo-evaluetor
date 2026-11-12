"""Small synchronous GitHub transport; no evaluation rules or automatic pagination."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from django.conf import settings


class GitHubError(Exception):
    """Safe error metadata; never includes request headers or response bodies."""

    def __init__(self, message, *, status=None, headers: Mapping[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.rate_limit_headers = {
            key: headers[key]
            for key in ("X-RateLimit-Limit", "X-RateLimit-Remaining",
                        "X-RateLimit-Reset", "Retry-After")
            if headers is not None and key in headers
        }


class RepositoryNotFound(GitHubError):
    pass


class LatestReleaseNotFound(GitHubError):
    """Release endpoint returned 404; repository may also be inaccessible."""


class RateLimitExceeded(GitHubError):
    pass


class GitHubServerError(GitHubError):
    pass


class GitHubNetworkError(GitHubError):
    pass


class GitHubTimeout(GitHubNetworkError):
    pass


class InvalidResponse(GitHubError):
    pass


@dataclass(frozen=True)
class CommitPage:
    commits: list[dict]
    has_next: bool


class GitHubClient:
    def __init__(self, *, base_url="https://api.github.com", timeout=(3.05, 15)):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _path(owner, repo):
        if any(not value or value in (".", "..") or "/" in value
               for value in (owner, repo)):
            raise ValueError("Owner and repository must be nonempty path segments")
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    def _get(self, path, *, params=None, missing: type[GitHubError] = RepositoryNotFound):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-evaluator",
        }
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
        try:
            # No retries or redirects: a moved repository is an explicit HTTP error.
            with requests.Session() as session:
                session.trust_env = False  # Do not acquire implicit netrc credentials.
                response = session.get(
                    self.base_url + path, params=params, headers=headers,
                    timeout=self.timeout, allow_redirects=False,
                )
        except requests.Timeout:
            raise GitHubTimeout("GitHub request timed out") from None
        except requests.RequestException:
            raise GitHubNetworkError("GitHub request failed") from None

        status = response.status_code
        try:
            data = response.json()
        except ValueError:
            data = None
        message = data.get("message", "") if isinstance(data, dict) else ""
        limited = (
            response.headers.get("X-RateLimit-Remaining") == "0"
            or "Retry-After" in response.headers
            or (isinstance(message, str) and "rate limit" in message.lower())
        )
        error = None
        if status == 404:
            error = missing
        elif status == 429 or (status == 403 and limited):
            error = RateLimitExceeded
        elif 500 <= status <= 599:
            error = GitHubServerError
        elif status != 200:
            error = GitHubError
        if error:
            raise error(f"GitHub returned HTTP {status}", status=status,
                        headers=response.headers)
        if data is None:
            raise InvalidResponse("GitHub returned invalid JSON")
        return data, response

    @staticmethod
    def _object(data, fields):
        # Validate only the small transport contract, preserving all other fields.
        if not isinstance(data, dict) or any(
            type(data.get(key)) is not kind for key, kind in fields.items()
        ):
            raise InvalidResponse("GitHub returned an unexpected response shape")
        return data

    def get_repository(self, owner, repo):
        data, _ = self._get(self._path(owner, repo))
        return self._object(data, {"id": int, "full_name": str, "default_branch": str})

    def get_latest_release(self, owner, repo):
        data, _ = self._get(self._path(owner, repo) + "/releases/latest",
                            missing=LatestReleaseNotFound)
        return self._object(data, {"id": int, "tag_name": str,
                                   "draft": bool, "prerelease": bool})

    @staticmethod
    def _timestamp(value):
        if value.utcoffset() is None:
            raise ValueError("GitHub timestamps must be timezone-aware")
        value = value.astimezone(timezone.utc)
        if not 1970 <= value.year <= 2099:
            raise ValueError("GitHub timestamps must be between 1970 and 2099")
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")

    def get_commits(self, owner, repo, *, since: datetime, until=None, page=1):
        """One default-branch page. Repeat with page+1 only when has_next is true."""
        if type(page) is not int or page < 1:
            raise ValueError("page must be a positive integer")
        params = {"since": self._timestamp(since), "per_page": 100, "page": page}
        if until is not None:
            params["until"] = self._timestamp(until)
            if until < since:
                raise ValueError("until must not precede since")
        data, response = self._get(self._path(owner, repo) + "/commits", params=params)
        if not isinstance(data, list):
            raise InvalidResponse("GitHub returned an unexpected commit list")
        for item in data:
            self._object(item, {"sha": str, "commit": dict})
            if "author" not in item or not isinstance(item["author"], (dict, type(None))):
                raise InvalidResponse("GitHub returned an unexpected commit author")
        return CommitPage(data, "next" in response.links)
