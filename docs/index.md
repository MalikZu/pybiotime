# pybiotime

A typed Python client for the ZKTeco BioTime REST API.

!!! warning "Unofficial"
    pybiotime is not affiliated with or endorsed by ZKTeco.
    BioTime is a trademark of its owner.

!!! note "Status: early development"
    Nothing is published yet. The interface may change without notice.

## What it will do

- Talk to BioTime 9.5, and to 9.0 and 8.5 where their APIs overlap.
- Offer sync and async clients with the same interface.
- Cover devices, employees, departments, areas, positions and punch transactions.
- Page through results for you, return typed models and raise clear errors.
- Read new punches without losing late uploads from offline devices.
- Ship an in-memory fake server, so you can test your code without a BioTime server.

It runs on Python 3.10 to 3.14 and depends only on `httpx` and `pydantic`.
It does not depend on any web framework.
