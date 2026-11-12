"""Explainable maintenance heuristics, independent of HTTP and persistence."""

from calendar import monthrange
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from .github import GitHubClient, GitHubError, LatestReleaseNotFound

LABELS = {
    "healthy": "No major signals detected",
    "warning": "Review recommended",
    "critical": "High maintenance risk",
    "unknown": "Insufficient data",
}


def metric(status, value, unit, message):
    return dict(status=status, value=value, unit=unit, message=message)


def months_before(now, months):
    """Subtract calendar months, clamping the day to the destination month."""
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    month += 1
    return now.replace(year=year, month=month,
                       day=min(now.day, monthrange(year, month)[1]))


def release_metric(value: object, now, source="github_release", version=None) -> dict[str, Any]:
    try:
        if not isinstance(value, str):
            raise ValueError
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.utcoffset() is None:
            raise ValueError
        published = published.astimezone(timezone.utc)
        if published > now:
            raise ValueError
    except (ValueError, OverflowError):
        return dict(metric("unknown", None, "date", "No reliable release freshness information is available."), source=None, version=None)
    if published > months_before(now, 6):
        status, message = "healthy", "The latest GitHub Release is less than 6 calendar months old."
    elif published > months_before(now, 12):
        status, message = "warning", "The latest GitHub Release is 6 to less than 12 calendar months old."
    else:
        status, message = "critical", "The latest GitHub Release is at least 12 calendar months old."
    if source == "git_tag":
        message = ("Freshness is estimated from the selected stable version tag's associated "
                   "commit committer date, not the tag publication date. "
                   "The highest recognized version in the first 100 tags may not be the latest published release.")
    return dict(metric(status, published.isoformat().replace("+00:00", "Z"), "date", message),
                source=source, version=version)



class RepositoryEvaluator:
    def __init__(self, client=None):
        self.client = client if client is not None else GitHubClient()

    def evaluate(self, owner, repo, *, now=None):
        """Return JSON-compatible data; metadata errors propagate unchanged.

        meta.errors records partial service failures (type, status, rate headers).
        Expected missing releases are represented only by an unknown metric.
        """
        now = now if now is not None else datetime.now(timezone.utc)
        if now.utcoffset() is None:
            raise ValueError("Evaluation time must be timezone-aware")
        now = now.astimezone(timezone.utc)
        repository = self.client.get_repository(owner, repo)
        errors = []

        def record_error(endpoint, error):
            errors.append({"endpoint": endpoint, "type": type(error).__name__,
                           "status": error.status,
                           "rate_limit_headers": dict(error.rate_limit_headers)})

        complete = None
        try:
            page = self.client.get_commits(owner, repo, since=now - timedelta(days=90),
                                           until=now, page=1)
            complete = not page.has_next
            count = len(page.commits)
            value = "100+" if page.has_next else count
            status = "healthy" if page.has_next or count >= 10 else "warning" if count else "critical"
            maintenance = metric(status, value, "commits", f"{value} commits in the last 90 days.")
        except GitHubError as error:
            record_error("commits", error)
            maintenance = metric("unknown", None, "commits", "Recent commits could not be retrieved.")

        release = release_metric(None, now)
        release_endpoint = "releases/latest"
        try:
            try:
                latest = self.client.get_latest_release(owner, repo)
            except LatestReleaseNotFound:
                latest = {}
            release = release_metric(latest.get("published_at"), now,
                                     version=latest.get("tag_name"))
            if release["status"] == "unknown":
                release_endpoint = "tags"
                tags = self.client.get_tags(owner, repo)
                candidates = []
                for tag in tags:
                    # Two to four numeric components; no prerelease/build suffixes.
                    match = re.fullmatch(r"v?([0-9]{1,9}(?:\.[0-9]{1,9}){1,3})", tag["name"])
                    if match:
                        parts = tuple(map(int, match[1].split(".")))
                        candidates.append((parts + (0,) * (4 - len(parts)), tag["name"], tag))
                if candidates:
                    selected = max(candidates, key=lambda item: (item[0], item[1]))[2]
                    release_endpoint = "tag_commit"
                    commit = self.client.get_commit(owner, repo, selected["commit"]["sha"])
                    committer = commit["commit"].get("committer")
                    date = committer.get("date") if isinstance(committer, dict) else None
                    release = release_metric(date, now, "git_tag", selected["name"])
        except GitHubError as error:
            record_error(release_endpoint, error)
            release = release_metric(None, now)
            release["message"] = "Release freshness could not be retrieved from GitHub."

        archived = repository.get("archived")
        if type(archived) is not bool:
            archived = None
        archive_metric = metric(
            "unknown" if archived is None else "critical" if archived else "healthy",
            archived, "boolean",
            "Archive status is unavailable." if archived is None else
            "The repository is archived." if archived else "The repository is not archived.",
        )
        metrics = dict(maintenance=maintenance,
                       release=release, archived=archive_metric)
        overall = next(status for status in ("critical", "warning", "unknown", "healthy")
                       if any(item["status"] == status for item in metrics.values()))
        if overall == "healthy":
            summary = "No major maintenance-risk signals were detected by these heuristics; security and suitability are not established."
        else:
            summary = " ".join(item["message"] for item in metrics.values()
                               if item["status"] == overall)
        return {
            "repository": {
                "full_name": repository.get("full_name"), "url": repository.get("html_url"),
                "description": repository.get("description"),
                "default_branch": repository.get("default_branch"),
                "stars": repository.get("stargazers_count"), "archived": archived,
            },
            "assessment": dict(status=overall, label=LABELS[overall], summary=summary),
            "metrics": metrics,
            "meta": dict(analyzed_at=now.isoformat().replace("+00:00", "Z"),
                         window_days=90, commits_complete=complete, errors=errors),
        }
