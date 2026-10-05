# Getting started

## Install

```bash
pip install pybiotime
```

Or `uv add pybiotime` in a uv project.

It needs Python 3.10 or newer, and installs `httpx` and `pydantic`. On Windows it also
installs `tzdata`, because Windows has no timezone database of its own.

## Connect

```python
from pybiotime import BioTimeClient, TokenAuth

with BioTimeClient(
    "http://10.0.0.5:8090",
    auth=TokenAuth("api_user", "secret"),
    timezone="Asia/Dubai",
) as bt:
    for terminal in bt.terminals.list():
        print(terminal.sn, terminal.alias)
```

- **The address** includes the port. BioTime has no fixed port; ask whoever installed it.
- **`auth`** is how you log in. See [Authentication](authentication.md).
- **`timezone`** is the server's timezone. BioTime sends times without one, so pybiotime
  cannot know it. Set it and every returned time carries it. Leave it out and times stay naive.

The client logs in on the first request, not when you create it.

## Async

The async client has the same methods. Use `async with`, `async for` and `await`:

```python
from pybiotime import AsyncBioTimeClient, TokenAuth

async with AsyncBioTimeClient("http://10.0.0.5:8090", auth=TokenAuth("api_user", "secret")) as bt:
    async for terminal in bt.terminals.list():
        print(terminal.sn)
    punch = await bt.transactions.list().first()
```

## Lists

`list()` returns a lazy pager. Nothing is fetched until you use it:

```python
pager = bt.transactions.list(emp_code="1001")

for punch in pager:  # every match, page by page
    ...
pager.first()  # first match or None, one small request
pager.count()  # number of matches, one small request
for page in pager.pages():  # page by page, with page.count and page.has_next
    ...
```

The default page size is 100. Change it with `page_size=` on the client or on `list()`.

## Self-signed certificates

Many BioTime servers use HTTPS with a self-signed certificate. pybiotime checks
certificates by default. To trust that server, pass the path to its certificate:

```python
BioTimeClient("https://biotime.example.com", auth=..., verify="/path/to/biotime.pem")
```

`verify=False` turns the check off. Only do that on a network you trust.

## Endpoints pybiotime does not wrap yet

`request()` calls any endpoint with the same login, retries and errors:

```python
holidays = bt.request("GET", "/att/api/holidays/", params={"page_size": 50})
```

It returns the decoded JSON.
