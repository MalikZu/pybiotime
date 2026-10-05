# BioTime versions

pybiotime gives you the same models whatever the server version. You do not need to
tell it which version you have.

| Version | Status |
|---|---|
| 9.5 | Tested against a live server |
| 9.0 | Built from the vendor manual; not yet tested live |
| 8.5 | Built from the vendor manual; not yet tested live |
| 8.0 | Built from the vendor manual and reports from live 8.x servers |

If you run 8.x or 9.0, running the [live tests](contributing.md) against your server,
with `BIOTIME_VERSION` set to its version, and reporting the result helps a lot.

## What differs, and what pybiotime does about it

- **Employee attendance flags.** 9.x nests them under `attemployee`; 8.x sends
  `enable_att`, `enable_overtime` and `enable_holiday` at the top level. Both read into
  `employee.attendance`.
- **Names beside relations.** 8.x sends `dept_name`, `position_name` and `area_name` next
  to the ids. They move into `employee.department`, `employee.position` and `employee.area`.
  8.x departments give their parent as an id with `parent_dept_name`; it moves into
  `department.parent_dept`.
- **The resign API** is documented for 8.5 and 9.5, but servers do not always match their
  manuals. Where it is missing, resign calls raise `FaultPageError`, because the server
  answers with an HTML "Page not found" page. Check `server_info().has_resigns`.
- **Page size.** Servers take `page_size`; the 8.0 and 9.0 manuals document `limit`.
  pybiotime sends both, and servers ignore the one they do not know.
- **No temperature check.** The 8.0 and 9.0 manuals say devices that do not check
  temperatures or masks send 255 for them. Both read as `None`.
- **Loose types.** Numbers come as strings, booleans as `0`/`1`, `"Yes"`/`"No"` or `"-"`,
  and empty text as `""` or `null`. Models accept all of these.
- **Password hashes.** 8.x returns employees' self-service password as a hash; 9.x leaves
  it out of reads. pybiotime keeps it out of `repr()` either way.

## Which version is this server?

No endpoint reports the version. `server_info()` reads three signals:

```python
info = bt.server_info()
info.version  # "9.5" from the docs title, "8.x" for flat employees, otherwise None
info.has_resigns  # True, False, or None when the server's answer did not tell
info.employee_shape  # "flat" (8.x) or "nested"; None without employees
info.docs_title  # title of the public /api/docs/ page, or None
```

The signals are the title of the public API docs page, the shape of one employee, and
whether the resign endpoint answers. `version` gives a number only when the docs title
shows one: some 8.x servers nest employees as 9.x does, and the resign API is not tied
to one version. To decide what to call, check `has_resigns` directly.

A signal is `None` when its request fails. Authentication and connection errors on the
API requests still raise.

## Testing against older versions

`FakeBioTime(version="8.0")` answers as the 8.0 manual shows: flat employees with a
password hash, departments that give their parent as an id and a name, no resign API,
and the 8.x docs title. `"8.5"` adds the resign API. `"9.0"` sends nested employees and
ZKBio Time punches, without the resign API. Other records keep the 9.5 shape. Run your
tests once per version to catch shape assumptions:

```python
import pytest
from pybiotime.testing import VERSIONS, FakeBioTime


@pytest.fixture(params=VERSIONS)
def fake(request):
    return FakeBioTime(version=request.param)
```

Real servers do not always match their manuals. `resign_api=True` or `False` overrides
the version's default, and `page_size_param="limit"` imitates a server that pages by
`limit`.
