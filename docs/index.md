# pybiotime

A typed Python client for the ZKTeco BioTime REST API.

!!! warning "Unofficial"
    pybiotime is not affiliated with or endorsed by ZKTeco.
    BioTime is a trademark of its owner.

!!! note "Status: early development"
    Nothing is published yet. The interface may change without notice.

## What it does

- Talks to BioTime 9.5. Support for 9.0 and 8.5 is planned where their APIs overlap.
- Offers sync and async clients with the same methods.
- Reads devices and punch transactions today. Employees, departments, areas and positions come next.
- Pages through results for you, returns typed models and raises clear errors.
- [Collects new punches without gaps](punches.md#collect-new-punches-without-gaps),
  including late uploads from offline devices.
- Ships an [in-memory fake server](testing.md), so you can test your code without a BioTime server.

It runs on Python 3.10 to 3.14 and depends only on `httpx` and `pydantic`, plus `tzdata` on Windows.
It does not depend on any web framework.

```python
from pybiotime import BioTimeClient, TokenAuth

with BioTimeClient("http://10.0.0.5:8090", auth=TokenAuth("api_user", "secret")) as bt:
    result = bt.transactions.read_new(saved_state)
```

Start with [Getting started](getting-started.md).
