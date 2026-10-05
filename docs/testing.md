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

Like BioTime 9.5, it keeps department and employee codes when an update tries to change
them, and answers writes with related objects as bare ids. By default it never sends back
`self_password` or `flow_role`. Older versions add them where their manuals do: 8.x
employees carry a password hash, and 8.x and 9.0 write answers carry it too.

## What it imitates

- Token and JWT logins, with HTTP 400 for a wrong password.
- Paging, with next links that point at a different, internal host.
- Filters on punch time, `emp_code` and `terminal_sn`.
- Sorting by punch time and upload time. Other sorts are ignored. Set `honoured_orders` to
  imitate a server that ignores more.
- An HTML page with HTTP 200 for unknown paths.

## Older BioTime versions

`FakeBioTime(version="8.0")`, `"8.5"` or `"9.0"` answers as that version's manual shows
employees, departments, punches, the API docs page and the resign API. Other records keep
the 9.5 shape. See [BioTime versions](versions.md#testing-against-older-versions).

## Useful knobs

- `fake.requests` lists every request received, for assertions. List requests carry both
  `page_size` and `limit`. Each record's `accept` holds the Accept header; it is left out
  when records are compared.
- `fake.fail_next(503, path="/iclock/")` answers the next matching request with an error.
- `fake.tokens.clear()` makes the server reject the current token.
- `upload_time=` on `add_transaction` imitates a device that uploads late.
- `fake.resign_api = True` (or `False`) makes the resign API answer (or not), whatever
  the version.
- `fake.page_size_param = "limit"` imitates a server that pages by `limit`.
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
