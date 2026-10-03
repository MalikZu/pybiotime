# Contributing

## Set up

You need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pre-commit install
```

The hooks run ruff, mypy and a commit-message check on every commit.

## Check your change

```bash
uv run pytest
uv run pre-commit run --all-files
```

Unit tests never touch the network. They use recorded responses and the fake server.

Tests against a real BioTime server are opt-in. Set these variables to run them:

- `BIOTIME_URL`
- `BIOTIME_USERNAME`
- `BIOTIME_PASSWORD`

## Rules

- Python 3.10 is the oldest supported version. Do not use newer syntax or standard-library modules.
- Every feature works in both the sync and the async client.
- Never log secrets: tokens, passwords, or the password and card hashes the API returns.
- Keep runtime dependencies few. Their ranges must fit what Frappe v15 and v16 pin. CI checks this.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `type: summary`.
Allowed types are `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci` and `perf`.
Keep each commit to one change.

## Docs

```bash
uv run --group docs mkdocs serve
```
