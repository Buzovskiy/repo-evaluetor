# Repository evaluation API

GET /api/evaluate/?repo=django/django accepts exactly one query parameter.
HTTPS github.com repository URLs are also accepted, with an optional trailing
slash or .git suffix. Names are normalized to lowercase. Credentials, ports,
query strings, fragments, extra path segments, whitespace, and other hosts are
rejected. Input URLs are parsed only; the existing GitHub client constructs requests.

A 200 response preserves the evaluator's repository, assessment, metrics, and meta
objects, adding meta.cached (false on a fresh evaluation, true on a cache hit).
Unknown metrics from absent data are still valid evaluations. A single secondary
request failure remains a partial 200 response with meta.errors. When both commits
and releases fail, the API returns an upstream error; rate limits take precedence
over timeouts, then other errors. Metadata failures always become HTTP errors.

Errors use:
{"error":{"code":"REPOSITORY_NOT_FOUND","message":"GitHub repository was not found.","retry_after_seconds":null}}

Invalid input returns 400; missing repositories 404; rate limits 429; timeouts
504; other GitHub failures 502. Unsupported methods return JSON 405 with Allow: GET.
Retry-After seconds or HTTP dates are preferred over X-RateLimit-Reset; valid retry
intervals are returned in both the JSON error and Retry-After header. Past deadlines
produce zero. No interval is invented when headers are absent or invalid.

Evaluations without meta.errors are cached for 900 seconds, including meaningful
unknown metrics (for example, no release) and bounded/paginated commit samples.
Equivalent URL and owner/repo inputs share case-insensitive entries. Failures and
partial service failures are not cached. Response metadata is added to a copy.

Django's in-memory cache is per process, is not shared across workers, and is lost
on restart. Concurrent misses may make duplicate GitHub requests. This is not
request throttling. HTTP responses use Cache-Control: no-store so the application
cache controls freshness. No CORS policy, authentication, or dependencies were added.

Run from the repository root:
DEBUG=true backend/.venv/bin/python backend/manage.py test backend/tests
DEBUG=true backend/.venv/bin/python backend/manage.py check

Tests mock the evaluator/GitHub client and require no network or credentials.
