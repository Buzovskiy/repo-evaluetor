"""Explainable maintenance heuristics, independent of HTTP and persistence."""

from calendar import monthrange
from collections import Counter
from datetime import datetime, timedelta, timezone

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


def concentration(commits, complete):
    """Use stable GitHub author IDs only, never names, emails, or committers.

    Any unlinked author makes this metric unknown: mixing account IDs with
    email fallbacks can split one person into multiple apparent contributors.
    Accounts (including bots) are a proxy for people, not verified identities.
    """
    if not complete or len(commits) < 10:
        return metric("unknown", None, "percent",
                      "Concentration requires at least 10 commits and complete history.")
    authors = []
    for commit in commits:
        author = commit.get("author")
        identity = author.get("id") if isinstance(author, dict) else None
        if type(identity) is not int or identity <= 0:
            return metric("unknown", None, "percent",
                          "Reliable GitHub author attribution is unavailable.")
        authors.append(identity)
    percentage = max(Counter(authors).values()) / len(commits) * 100
    status = "healthy" if percentage < 50 else "warning" if percentage < 80 else "critical"
    return metric(status, round(percentage, 1), "percent",
                  f"One contributor authored {percentage:.1f}% of recent commits.")


def release_metric(value, now):
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
        return metric("unknown", None, "date", "A valid release publication date is unavailable.")
    if published > months_before(now, 6):
        status, message = "healthy", "The latest stable release is less than 6 calendar months old."
    elif published > months_before(now, 12):
        status, message = "warning", "The latest stable release is 6 to less than 12 calendar months old."
    else:
        status, message = "critical", "The latest stable release is at least 12 calendar months old."
    return metric(status, published.isoformat().replace("+00:00", "Z"), "date", message)


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
            concentrated = concentration(page.commits, complete)
        except GitHubError as error:
            record_error("commits", error)
            maintenance = metric("unknown", None, "commits", "Recent commits could not be retrieved.")
            concentrated = metric("unknown", None, "percent", "Recent commits could not be retrieved.")

        try:
            release = release_metric(self.client.get_latest_release(owner, repo).get("published_at"), now)
        except LatestReleaseNotFound:
            release = metric("unknown", None, "date", "No stable release is available; this does not imply abandonment.")
        except GitHubError as error:
            record_error("releases/latest", error)
            release = metric("unknown", None, "date", "The latest stable release could not be retrieved.")

        archived = repository.get("archived")
        if type(archived) is not bool:
            archived = None
        archive_metric = metric(
            "unknown" if archived is None else "critical" if archived else "healthy",
            archived, "boolean",
            "Archive status is unavailable." if archived is None else
            "The repository is archived." if archived else "The repository is not archived.",
        )
        metrics = dict(maintenance=maintenance, concentration=concentrated,
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
