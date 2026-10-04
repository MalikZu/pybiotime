# Testing your code

`pybiotime.testing.FakeBioTime` is an in-memory BioTime server. Use it to test code that
calls pybiotime, with no network and no real server.

```python
from datetime import datetime

from pybiotime import BioTimeClient, TokenAuth
from pybiotime.testing import FakeBioTime


def test_import_punches():
    fake = FakeBioTime(username="api", password="secret")
    fake.add_terminal(sn="TEST0000001", alias="Main gate")
    fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 8, 0))

    client = BioTimeClient(
        "http://biotime.test", auth=TokenAuth("api", "secret"), transport=fake.transport()
    )
    result = client.transactions.read_new()

    assert [p.emp_code for p in result.transactions] == ["1001"]
```

The same `transport()` works with `AsyncBioTimeClient`.

## What it imitates

- Token and JWT logins, with HTTP 400 for a wrong password.
- Paging, with next links that point at a different, internal host.
- Filters on punch time, `emp_code` and `terminal_sn`.
- Sorting by punch time and upload time. Other sorts are ignored. Set `honoured_orders` to
  imitate a server that ignores more.
- An HTML page with HTTP 200 for unknown paths.

## Useful knobs

- `fake.requests` lists every request received, for assertions.
- `fake.fail_next(503, path="/iclock/")` answers the next matching request with an error.
- `fake.tokens.clear()` makes the server reject the current token.
- `upload_time=` on `add_transaction` imitates a device that uploads late.
