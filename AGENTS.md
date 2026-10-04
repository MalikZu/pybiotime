# pybiotime

Unofficial, typed Python SDK for the ZKTeco BioTime REST API.
BioTime 9.5 first; 9.0 and 8.5 where the API overlaps. Open source, MIT.

**Maintainers: read `internal/README.md` at the start of every session.**
It holds the current status, decisions and next step. `internal/` is not in git.

## Rules

- **Framework-agnostic.** Never import `frappe`, `django` or any web framework.
  Framework integrations are separate projects that depend on this one.
- **Python 3.10 to 3.14.** Frappe v15 runs on 3.10/3.11 and Frappe v16 on 3.14,
  and both must be able to install this package. Nothing newer than 3.10: no
  `except*` or `ExceptionGroup`, no `typing.Self`, `tomllib` or `datetime.UTC`
  (3.11), no PEP 695 `type` aliases (3.12), no PEP 758 `except A, B:` (3.14).
  CI tests every version.
- **Few, compatible dependencies.** A new runtime dependency needs a reason in the
  PR, and its version range must fit inside Frappe v15 and v16 pins.
- **Sync and async parity.** A feature is not done until both clients have it.
- **One shape per model.** BioTime version differences live in `compat.py`, and
  fixtures cover every supported BioTime version.
- **Never log secrets.** Redact the `Authorization` header, passwords, and the
  hashes the API returns (`self_password`, `device_password`, `card_no`).
- **No network in unit tests.** Use fixtures or `pybiotime.testing`. Live-server
  tests are opt-in through `BIOTIME_URL` plus `BIOTIME_TOKEN` or
  `BIOTIME_USERNAME`/`BIOTIME_PASSWORD`. They write only with `BIOTIME_WRITE_TESTS=1`,
  and then delete what they create.
- **Never commit vendor manuals or copy their prose.** ZKTeco PDFs stay in
  `internal/vendor/`. Docs restate facts in our own words.

## Working on this repo

- `internal/` is never committed. No internal plans or notes in commits, docs or
  code comments.
- Commit as you go, one small commit per coherent change. Conventional commits:
  `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`.
- Docs are for users: short sentences, plain words, no filler. A change a user
  can see ships its doc in the same PR.
- Public text never credits individuals by name and never names customers.
- README and docs state that the project is unofficial and not affiliated with ZKTeco.
- Keep this file small. Details go in `docs/` and get linked.
