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

- `BIOTIME_URL`, for example `http://10.0.0.5:8090`
- `BIOTIME_TOKEN`, or `BIOTIME_USERNAME` and `BIOTIME_PASSWORD`
- `BIOTIME_TIMEZONE` (optional), for example `Asia/Dubai`
- `BIOTIME_VERSION` (optional), for example `9.0`: your server's version. The tests then
  check that `server_info()` does not name another one.

```bash
uv run pytest tests/contract
```

One test writes: it creates a department, area, position and employee with codes that
start with `PYBT`, changes them, then deletes them. It runs only with
`BIOTIME_WRITE_TESTS=1`. Never point it at a production server.

Resign tests skip themselves when the server has no resign API.

## Sync and async code

Edit only the async code under `_async/` folders. The sync code under `_sync/` is generated:

```bash
uv run python scripts/unasync.py
```

A pre-commit hook fails if you forget.

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

## Releasing

A release is a pushed tag. The version comes from the tag, so nothing in the code
changes. Commits on `main` follow Conventional Commits, which keeps the release notes
readable: they list the pull requests merged since the last tag.

1. Check that CI on `main` is green.
2. Pick the version: a `fix` since the last release means a patch, a `feat` a minor
   version. Before 1.0, breaking changes also go in a minor version.
3. Tag `main` and push the tag:

    ```bash
    git switch main && git pull
    git tag -a v0.1.0 -m "pybiotime 0.1.0"
    git push origin v0.1.0
    ```

The Release workflow then checks that the tag is on `main`, runs the tests, builds the
package, checks that its version matches the tag, publishes it to PyPI and creates a
GitHub release. A tag such as `v0.2.0rc1` makes a pre-release.

### One-time setup

PyPI trusts the workflow through Trusted Publishing, so no API token is stored:

- On PyPI, add a trusted publisher for the project `pybiotime`: owner `MalikZu`,
  repository `pybiotime`, workflow `release.yml`, environment `pypi`. Before the first
  release, add it as a pending publisher from your account's publishing page.
- On GitHub, create an environment named `pypi` under Settings → Environments. Add
  yourself as a required reviewer to approve each upload by hand.
