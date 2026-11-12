# Repository evaluator

A small Simfoni take-home project to help developers judge the long-term maintenance risk of adopting an open-source GitHub dependency. “Will we regret this?” means looking for signs that maintenance or delivery may have slowed, or that the repository has been retired. These are explainable prompts for review, not predictions about the next two years.

The Django API and React/TypeScript frontend implement a single repository evaluation workflow, with loading, error, and partial-result states.

## Live Demo

- [React frontend — Live Demo](https://repo-evaluetor.onrender.com/)
- [Django API health](https://api-repo-evaluetor.onrender.com/health/) — verified HTTP 200 during this review.
- [GitHub repository](https://github.com/Buzovskiy/repo-evaluetor)

## How evaluation works

| Metric | Healthy | Warning | Critical |
| --- | --- | --- | --- |
| Maintenance Activity | At least 10 default-branch commits in 90 days | 1–9 commits | No commits |
| Release Freshness | Less than 6 calendar months | 6 to less than 12 calendar months | At least 12 calendar months |
| Repository Status | Explicitly not archived | — | Archived |

Commit requests retrieve only the first 100 entries. More pages produce a maintenance count of `100+`; no additional commit-history pages are fetched. Calendar-month calculations clamp dates at month ends.

Missing information produces `unknown`, not an automatically negative assessment. Overall status uses the worst signal: **critical > warning > unknown > healthy**. There is no numeric score. Healthy means no major signals detected by these heuristics; it does not establish security, absence of vulnerabilities, suitability, or continued maintenance.

## Deliberately excluded scope

**Deliberately excluded: Contributor Concentration.** GitHub commit attribution can be incomplete, and a limited sample of recent commits may not reliably represent contributor dependence. Rather than present a potentially misleading risk signal, I focused on repository activity, release freshness, and archived status.

The MVP uses synchronous requests, no database or user authentication, and a small in-memory cache. It avoids unbounded history scans and elaborate release discovery.

## Release freshness limitations

GitHub Releases are the primary source. A valid `published_at` becomes the metric's `value`, with `source: github_release` and the release's tag name as `version`.

If the release is missing or its publication date is unusable, the API inspects the first 100 Git tags. It recognizes two to four dot-separated numeric components, optionally prefixed by lowercase `v` (for example `1.2`, `v1.2.3`, or `2026.10.1`). Components are limited to nine digits. Prerelease suffixes and descriptive names are excluded.

Selection uses the highest numeric version, padding missing components with zero; equal versions use the tag name as a deterministic tie-breaker. This is not a publication-order search. A newer patch on an older supported branch may be overlooked, and tags outside the first page are not considered.

Only the selected tag's commit is resolved. With `source: git_tag`, `value` is that commit's **committer timestamp**, normalized to UTC. It is not the commit author date, tag creation time, or publication date. It can substantially predate a release. Invalid, missing, or future dates produce unknown; another tag is not scanned as a substitute. Unknown freshness has null source, version, and value.

Rate limits, network errors, and server failures do not trigger further fallback requests. A cache miss uses three GitHub requests normally, at most five with fallback. Some release processes cannot be identified reliably through these endpoints. Missing release information does not necessarily mean abandonment.

Endpoint shapes were checked against GitHub's [OpenAPI 3.0 description](https://github.com/github/rest-api-description/tree/main/descriptions/api.github.com).

## Local development

Prerequisites: Python 3.12+, uv, and Node.js/npm compatible with the frontend's Vite version.

Backend, from the repository root:

```bash
cd backend
uv sync --locked
cp .env.example .env
uv run python manage.py runserver
```

The example enables local DEBUG mode and leaves GITHUB_TOKEN empty. Set optional `GITHUB_TOKEN` in `backend/.env` for higher GitHub API rate limits. Never commit credentials. Local debug mode provides a development-only Django secret; production needs `DJANGO_SECRET_KEY`, DEBUG disabled, and appropriate ALLOWED_HOSTS.

Frontend, in another terminal:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Open the Vite URL printed in the terminal. The backend normally runs at http://127.0.0.1:8000.

The backend includes a Gunicorn dependency and WSGI entry point. Render hostname and proxy settings remain supported, but no deployment blueprint is checked in and the deployed backend health endpoint was verified here; the frontend URL was supplied by the author; its deployed end-to-end flow has not been verified here.

## API

```bash
curl 'http://127.0.0.1:8000/api/evaluate/?repo=django/django'
```

A full HTTPS GitHub repository URL is also accepted. Exactly one query parameter is required. The response contains `repository` metadata, `assessment` status/label/summary, exactly three `metrics` (maintenance, release, archived), and `meta` with analysis time, window, commit completeness, errors, and cache status.

For example, an unavailable release metric is:

```json
{"status":"unknown","value":null,"unit":"date","source":null,"version":null,"message":"No reliable release freshness information is available."}
```

Input errors return 400, missing repositories 404, rate limits 429, timeouts 504, and other upstream errors 502. One failed secondary signal remains a partial 200 assessment with `meta.errors`; failure of both commit activity and release discovery returns an upstream error. Retry information is preserved where supplied by GitHub. See [backend/API.md](backend/API.md).

Successful evaluations without upstream errors are cached for 15 minutes. The cache is per process, disappears on restart, and is not shared across workers. Concurrent misses can duplicate requests. Confirmed rate limits trigger a per-process cooldown using GitHub retry information (60 seconds if absent); successful cached results remain available. A commits rate limit stops further calls. A release rate limit preserves available commit evidence as partial results. `/health/` returns `{"status":"ok"}`.

## Running tests

From the repository root, after installing backend dependencies:

```bash
DEBUG=true backend/.venv/bin/python backend/manage.py test backend/tests
DEBUG=true backend/.venv/bin/python backend/manage.py check
```

Tests mock GitHub responses and require neither network access nor tokens.

## AI usage

AI coding assistance was used to implement backend integration, evaluation logic, HTTP handling, tests, and documentation. The author made product-level decisions, including removing Contributor Concentration and focusing on three explainable signals.

This description does not claim a particular division of manually written code or independent manual verification.

## Known limitations and possible improvements

Commit counts do not measure code quality or useful work. Tag recognition is intentionally conservative, and commit dates are imperfect release proxies. GitHub outages and rate limits can leave assessments incomplete.

Possible next steps are browser-based accessibility checks and validation of these heuristics against real adoption decisions. Broader release conventions could be supported if concrete examples justify the complexity.

## CORS and Render configuration

Browsers need CORS permission because the React frontend and Django backend use separate origins. The API allows `http://localhost:5173` and `http://127.0.0.1:5173` by default. Set comma-separated `CORS_ALLOWED_ORIGINS` to replace this list; whitespace and empty entries are ignored. Only `/api/` routes receive CORS headers. Credentialed requests and wildcard origins are not enabled.

In the **backend Render service**, set:

```dotenv
CORS_ALLOWED_ORIGINS=https://repo-evaluetor.onrender.com
```

`CORS_ALLOWED_ORIGINS` contains **frontend origins**; `ALLOWED_HOSTS` contains **backend hostnames**. Origins include the scheme and any non-default port, with no paths or trailing slashes. Save the environment change and redeploy/restart the service so it loads the updated configuration.

With the backend running, verify preflight without calling GitHub:

```bash
curl -i -X OPTIONS 'http://127.0.0.1:8000/api/evaluate/?repo=django/django' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET'
```

Expect `Access-Control-Allow-Origin: http://localhost:5173` and allowed methods including GET. In browser DevTools, inspect Network response headers on the API request. A disallowed origin receives no allowing header; curl itself does not enforce browser CORS rules.

## Frontend configuration and checks

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env` for local development. React submits requests to Django's `/api/evaluate/` using Fetch; it never calls GitHub directly. A missing API URL produces a configuration message instead of falling back to a development server.

For the frontend Render service, set `VITE_API_BASE_URL` to the actual HTTPS backend origin before building. Vite embeds this public value at build time: rebuild/redeploy after changes. Set the backend's `CORS_ALLOWED_ORIGINS` to the frontend origin as described above. Never put GitHub tokens or Django secrets in Vite variables.

Run from `frontend/`:

```bash
npm run build
npm run lint
npm test
```

Build output is `frontend/dist`. Tests use Vitest, jsdom, and mocked Fetch responses; no running backend is required. The page supports mobile layouts, keyboard submission, status announcements, and explicit release-source explanations. It has no saved history or automatic retries. Real-browser visual and deployment verification remain separate checks.

### Render service commands

Backend root: `backend`; build: `uv sync --locked`; start: `uv run gunicorn backend.wsgi:application --bind 0.0.0.0:$PORT`. Set `DEBUG=false`, private `DJANGO_SECRET_KEY`, backend `ALLOWED_HOSTS`, and frontend `CORS_ALLOWED_ORIGINS`.

Frontend root: `frontend`; build: `npm ci && npm run build`; publish: `dist`.
