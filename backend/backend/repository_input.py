"""Strict parsing; user input is never used as a request URL."""

import re
from urllib.parse import urlsplit
from django.http import QueryDict

OWNER = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}")


def parse_repository(params: QueryDict):
    if set(params) != {"repo"} or len(params.getlist("repo")) != 1:
        raise ValueError("Provide exactly one repo parameter.")
    value = params["repo"]
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        raise ValueError("Provide a repository without whitespace.")
    if "://" in value:
        url = urlsplit(value)
        if (url.scheme != "https" or url.netloc.lower() != "github.com"
                or "?" in value or "#" in value):
            raise ValueError("Only plain HTTPS github.com repository URLs are supported.")
        value = url.path.removeprefix("/").removesuffix("/")
        value = value.removesuffix(".git")
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError("Use owner/repository or a GitHub repository URL.")
    owner, repo = parts
    if (len(owner) > 39 or not OWNER.fullmatch(owner)
            or not REPOSITORY.fullmatch(repo) or repo in (".", "..")):
        raise ValueError("Invalid GitHub owner or repository name.")
    return owner.lower(), repo.lower()
