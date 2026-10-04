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

## Personnel

Seed departments, areas, positions and employees, then test code that manages them:

```python
fake = FakeBioTime()
ops = fake.add_department(code="OPS", name="Operations")
site = fake.add_area(code="DXB", name="Dubai office")
fake.add_employee(emp_code="1001", department_id=ops, area_ids=[site], first_name="Sara")
```

The fake checks what a real server checks: required fields, unique codes, and ids
that must exist. Failures raise `BadRequestError` with `field_errors`, as on a real server.

Like BioTime 9.5, it never sends back `self_password` or `flow_role`.

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
- `fake.creates_without_id` lists the collections whose creates answer without the new id.
  It defaults to `{"positions"}`, as BioTime 9.5 does.
- `fake.after_request` is called with each request after it is answered. Use it to add
  punches while your code is paging, as devices do on a live server:

```python
def add_punch_once(request):
    if request.path == "/iclock/api/transactions/" and "page" not in request.params:
        fake.after_request = None
        fake.add_transaction(emp_code="1002", punch_time=datetime(2026, 10, 1, 8, 5))


fake.after_request = add_punch_once
```
