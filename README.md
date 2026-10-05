# pybiotime

[![PyPI](https://img.shields.io/pypi/v/pybiotime)](https://pypi.org/project/pybiotime/)
[![Python](https://img.shields.io/pypi/pyversions/pybiotime)](https://pypi.org/project/pybiotime/)
[![CI](https://github.com/MalikZu/pybiotime/actions/workflows/ci.yml/badge.svg)](https://github.com/MalikZu/pybiotime/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/MalikZu/pybiotime/blob/main/LICENSE)

A typed Python client for the ZKTeco BioTime REST API, with sync and async clients.

> **Unofficial.** pybiotime is not affiliated with or endorsed by ZKTeco.
>
> **Alpha.** The interface may change before 1.0.

```bash
pip install pybiotime
```

Python 3.10 to 3.14. Depends only on `httpx` and `pydantic`, plus `tzdata` on Windows.

## Quick start

```python
from datetime import datetime

from pybiotime import BioTimeClient, TokenAuth

with BioTimeClient(
    "http://10.0.0.5:8090",
    auth=TokenAuth("api_user", "secret"),
    timezone="Asia/Dubai",
) as bt:
    for terminal in bt.terminals.list():
        print(terminal.sn, terminal.alias)

    for punch in bt.transactions.list(start=datetime(2026, 10, 1), emp_code="1001"):
        print(punch.punch_time, punch.punch_state)
```

The client logs in on first use, pages through results for you, and returns typed models.

## Collect punches without losing late uploads

A device that was offline uploads its punches later, sometimes months later. A
"last hour" query misses them. `read_new` does not:

```python
import json

result = bt.transactions.read_new(saved_state)  # None on the first run
for punch in result.transactions:
    store(punch)  # key it on the punch id
saved_state = json.dumps(result.state)  # a small dict; keep it for the next run
```

## Employees and structure

```python
ops = bt.departments.upsert("OPS", "Operations")
site = bt.areas.upsert("DXB", "Dubai office")

bt.employees.upsert(
    "1001", department_id=ops.id, area_ids=[site.id], first_name="Sara", last_name="Ali"
)
```

`upsert` creates the record, or sends only the fields that changed. Run it on every
sync: when nothing changed, it sends nothing.

## Async

`AsyncBioTimeClient` has the same methods:

```python
from pybiotime import AsyncBioTimeClient, TokenAuth

async with AsyncBioTimeClient("http://10.0.0.5:8090", auth=TokenAuth("api_user", "secret")) as bt:
    async for punch in bt.transactions.list(emp_code="1001"):
        print(punch.punch_time)
```

## Command line

```bash
export BIOTIME_URL=http://10.0.0.5:8090 BIOTIME_TOKEN=your-api-token
pybiotime info
pybiotime transactions --start 2026-10-01 --format csv -o october.csv
pybiotime sync --state state.json --output punches.jsonl   # for cron
```

## Test your code without a server

`pybiotime.testing.FakeBioTime` is an in-memory BioTime server with the real one's quirks:

```python
from datetime import datetime

from pybiotime import BioTimeClient, TokenAuth
from pybiotime.testing import FakeBioTime

fake = FakeBioTime()
fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 8, 0))

bt = BioTimeClient(
    "http://biotime.test", auth=TokenAuth("api", "secret"), transport=fake.transport()
)
```

## BioTime versions

| Version | Status |
|---|---|
| 9.5 | Tested against a live server |
| 9.0, 8.5, 8.0 | Built from the vendor manuals; not yet tested live |

All versions read into the same models. `bt.server_info()` shows what a server reports
about itself. If you run 8.x or 9.0, running the live tests against it helps a lot.

## Documentation

Full documentation: https://malikzu.github.io/pybiotime/

- [Getting started](https://malikzu.github.io/pybiotime/getting-started/)
- [Authentication](https://malikzu.github.io/pybiotime/authentication/)
- [Reading punches](https://malikzu.github.io/pybiotime/punches/)
- [Employees and structure](https://malikzu.github.io/pybiotime/personnel/)
- [Command line](https://malikzu.github.io/pybiotime/cli/)
- [Errors](https://malikzu.github.io/pybiotime/errors/)
- [BioTime versions](https://malikzu.github.io/pybiotime/versions/)
- [Testing your code](https://malikzu.github.io/pybiotime/testing/)

## Contributing

Issues and pull requests are welcome. See the
[contributing guide](https://malikzu.github.io/pybiotime/contributing/).

## License

MIT. See [LICENSE](https://github.com/MalikZu/pybiotime/blob/main/LICENSE).
