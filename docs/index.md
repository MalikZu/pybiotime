# pybiotime

A typed Python client for the ZKTeco BioTime REST API.

!!! warning "Unofficial"
    pybiotime is not affiliated with or endorsed by ZKTeco.
    BioTime is a trademark of its owner.

!!! note "Status: alpha"
    The interface may change before 1.0.

## What it does

- Talks to BioTime 9.5, 9.0, 8.5 and 8.0, and gives the same models for each.
  [Only 9.5 is tested against a live server so far](versions.md).
- Offers sync and async clients with the same methods.
- Reads devices and punch transactions.
- [Manages employees](personnel.md), departments, areas and positions, and resigns and reinstates people.
- Pages through results for you, returns typed models and raises clear errors.
- [Collects new punches without gaps](punches.md#collect-new-punches-without-gaps),
  including late uploads from offline devices.
- Comes with a [`pybiotime` command](cli.md) for exports and scheduled punch collection.
- Ships an [in-memory fake server](testing.md), so you can test your code without a BioTime server.

It runs on Python 3.10 to 3.14 and depends only on `httpx` and `pydantic`, plus `tzdata` on Windows.
It does not depend on any web framework.

```python
from pybiotime import BioTimeClient, TokenAuth

with BioTimeClient("http://10.0.0.5:8090", auth=TokenAuth("api_user", "secret")) as bt:
    result = bt.transactions.read_new(saved_state)
```

Start with [Getting started](getting-started.md).
