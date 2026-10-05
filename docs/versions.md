# BioTime versions

pybiotime gives you the same models whatever the server version. You do not need to
tell it which version you have.

| Version | Status |
|---|---|
| 9.5 | Tested against a live server |
| 9.0 | Built from the vendor manual; not yet tested live |
| 8.5 | Built from the vendor manual; not yet tested live |
| 8.0 | Built from the vendor manual and reports from live 8.x servers |

If you run 8.x or 9.0, running the [live tests](contributing.md) against your server
and reporting the result helps a lot.

## What differs, and what pybiotime does about it

- **Employee attendance flags.** 9.x nests them under `attemployee`; 8.x sends
  `enable_att`, `enable_overtime` and `enable_holiday` at the top level. Both read into
  `employee.attendance`.
- **Names beside relations.** 8.x sends `dept_name`, `position_name` and `area_name` next
  to the ids. They move into `employee.department`, `employee.position` and `employee.area`.
- **The resign API** exists on 8.5 and 9.5 only. On other versions, resign calls raise
  `FaultPageError`, because the server answers with an HTML "Page not found" page.
- **Page size.** Servers take `page_size`; the 9.0 manual documents `limit`. pybiotime
  sends both, and servers ignore the one they do not know.
- **Loose types.** Numbers come as strings, booleans as `0`/`1`, `"Yes"`/`"No"` or `"-"`,
  and empty text as `""` or `null`. Models accept all of these.
- **Password hashes.** 8.x returns employees' self-service password as a hash; 9.5 leaves
  it out. pybiotime keeps it out of `repr()` either way.

## Which version is this server?

No endpoint reports the version. `server_info()` reads three signals and makes a best guess:

```python
info = bt.server_info()
info.version  # "9.5", or "8.x" when only the generation is clear
info.has_resigns  # whether the resign API exists
info.employee_shape  # "nested" (9.x) or "flat" (8.x); None without employees
info.docs_title  # title of the public /api/docs/ page
```

The signals are the title of the public API docs page, the shape of one employee, and
whether the resign endpoint answers. Treat `version` as a guess. To decide what to call,
check `has_resigns` directly.

## Testing against older versions

`FakeBioTime(version="8.0")` answers in the 8.0 shape: flat employees, no resign API, and
the 8.x docs title. Run your tests once per version to catch shape assumptions:

```python
import pytest
from pybiotime.testing import VERSIONS, FakeBioTime


@pytest.fixture(params=VERSIONS)
def fake(request):
    return FakeBioTime(version=request.param)
```
