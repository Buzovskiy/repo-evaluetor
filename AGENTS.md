# AI Agent Instructions

## Source of truth

This repository is a take-home exercise for Simfoni Product Engineering.

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

## Deliverable documentation

When writing the **root** `README.md`, explicitly address all three questions in `docs/ASSIGNMENT.md`: the meaning of “will we regret this” and how it was decided, deliberately excluded scope, and transparent AI-tool usage (what AI helped with versus the author's own decisions).

The README should also make it easy to run the frontend and backend locally. Do not invent implementation details or claim unbuilt features are complete.
