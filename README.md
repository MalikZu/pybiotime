# pybiotime

Typed Python client for the ZKTeco BioTime REST API.

> **Status: alpha.** The interface may change before 1.0.
>
> pybiotime is an unofficial project. It is not affiliated with or endorsed by ZKTeco.

```bash
pip install pybiotime
```

```python
from pybiotime import BioTimeClient, TokenAuth

with BioTimeClient("http://10.0.0.5:8090", auth=TokenAuth("api_user", "secret")) as bt:
    for punch in bt.transactions.list(emp_code="1001"):
        print(punch.punch_time, punch.punch_state)
```

Documentation: https://malikzu.github.io/pybiotime/

## What it does

- Talks to BioTime 9.5, 9.0, 8.5 and 8.0 with the same models. Only 9.5 is tested
  against a live server so far.
- Sync and async clients with the same methods.
- Devices, punch transactions, employees, departments, areas, positions and resignations.
- Reads new punches without losing late uploads from offline devices.
- Automatic pagination, typed models and clear errors.
- An in-memory fake server for testing code that uses pybiotime.
- A `pybiotime` command for exports and scheduled punch collection.
- Python 3.10 to 3.14. Depends only on `httpx` and `pydantic` (plus `tzdata` on Windows).

## Contributing

See [docs/contributing.md](docs/contributing.md).

## License

MIT
