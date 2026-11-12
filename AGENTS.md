# AI Agent Instructions

## Source of truth

This repository is a take-home exercise.

**Read `docs/ASSIGNMENT.md` before planning or making changes.** It contains the assignment requirements and constraints. Do not modify it unless explicitly requested.

Treat `docs/ASSIGNMENT.md` as the source of truth for the task; do not infer additional requirements from examples, starter templates, or suggestions in these instructions.

## Repository layout

- `backend/`: Python >=3.12, Django project; dependencies defined in `backend/pyproject.toml` and locked in `backend/uv.lock`.
- `frontend/`: React with TypeScript, built with Vite; scripts and dependencies are in `frontend/package.json`.
- `docs/ASSIGNMENT.md`: original exercise requirements.
- `frontend/README.md`: Vite starter documentation, **not** the requested final project README.

The project currently contains starter code. Inspect existing files and conventions before implementing features. Keep frontend and backend changes in their respective directories.

## Product and engineering priorities

1. Focus on helping a user judge the long-term risk of adopting an open-source GitHub dependency.
2. Prioritize product judgment and implementation quality over feature count.
3. Keep the scope appropriate for a single-evening take-home exercise. Prefer one polished, meaningful workflow over several incomplete features.
4. Use GitHub's public API as the data source. Handle rate limits, failed requests, and unavailable data thoughtfully.
5. Do not add authentication, a database, or infrastructure without a clear reason. Do not treat optional ideas as mandatory features.

## Working practices

- Explain important trade-offs before expanding scope; avoid speculative features and premature abstractions.
- Keep changes focused and maintainable, and add targeted tests where valuable.
- Never commit secrets, credentials, or tokens.
- Do not claim a command, test, or deployment succeeded unless it was actually run and verified.
- Before finishing, run relevant available checks where practical, and state what was not verified.

## GitHub REST API reference

- Use GitHub's official REST API OpenAPI specification as the primary reference for endpoint definitions, request parameters, response schemas, and field types: https://github.com/github/rest-api-description.
- Prefer the stable OpenAPI 3.0 bundled descriptions under `descriptions/`; check the version of the specification when interpreting schemas.
- Consult https://docs.github.com/en/rest for behavior not fully represented in OpenAPI, especially pagination, authentication, rate limits, response headers, and error handling.
- For the initial repository evaluation workflow, consult these endpoints:
  - `GET /repos/{owner}/{repo}`
  - `GET /repos/{owner}/{repo}/commits`
  - `GET /repos/{owner}/{repo}/releases/latest`
- Verify required, optional, and nullable fields against the schemas. Do not assume one sample response covers all valid responses.
- When network access is available, use real API responses to validate assumptions without treating examples as a replacement for the documented schema.
- Handle pagination, incomplete data, missing releases, and API failures explicitly. Do not interpret missing data as zero or silently assign a risk score.
- Keep GitHub tokens and other credentials out of source files, test fixtures, logs, and commits.

## Deliverable documentation

When writing the **root** `README.md`, explicitly address all three questions in `docs/ASSIGNMENT.md`: the meaning of “will we regret this” and how it was decided, deliberately excluded scope, and transparent AI-tool usage (what AI helped with versus the author's own decisions).

The README should also make it easy to run the frontend and backend locally. Do not invent implementation details or claim unbuilt features are complete.
