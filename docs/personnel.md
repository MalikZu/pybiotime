# Employees and structure

pybiotime manages employees and the structure they belong to: departments, areas and
positions. All are on the client: `bt.departments`, `bt.areas`, `bt.positions`,
`bt.employees` and `bt.resigns`.

Each has `list()`, `get(id)`, `create(...)`, `update(id, ...)` and `delete(id)`.

## Departments, areas and positions

All three work the same way: a code, a name and an optional parent.

```python
ops = bt.departments.upsert("OPS", "Operations")
site = bt.areas.upsert("DXB", "Dubai office")
bt.positions.upsert("TECH", "Technician")

bt.departments.get_by_code("OPS")  # exact match, or None
bt.departments.update(ops.id, name="Operations team")
```

- **Areas** decide which devices know a person. An employee in the "DXB" area is sent
  to the devices in that area.
- **`upsert(code, name)`** creates the object if no object has that code. Otherwise it updates the name,
  and the parent if you pass `parent_id`. It sends a change only when something differs.

## Employees

`emp_code` is the business key. Devices know people by it, and punches carry it.

```python
from datetime import date

emp = bt.employees.upsert(
    "1001",
    department_id=ops.id,
    area_ids=[site.id],
    first_name="Sara",
    last_name="Ali",
    hire_date=date(2026, 10, 1),
)
```

- **BioTime requires a department and at least one area** when creating an employee.
- **`upsert`** creates the employee, or sends only the fields that differ from what the
  server has. Run it on every sync: when nothing changed, it sends nothing.
- **`update`** changes only the arguments you pass. To clear a field, pass it in `fields`,
  for example `fields={"position": None}`.
- **Other fields**, including custom attributes, go in `fields` under their API name:
  `fields={"Global ID": "A-17"}`. Read them back from `emp.extra`.

Reading an employee gives the same fields on every BioTime version. For example,
`emp.attendance.enable_overtime` works whether the server nests the flags (9.x) or not (8.x).
`emp.department_id`, `emp.position_id` and `emp.area_ids` give the ids directly.

The device PIN (`device_password`), the card number and, on older servers, a password
hash come back in employee data. pybiotime keeps them out of `repr()`. Keep them out of
your own logs too.

## When someone leaves

Resign the employee instead of deleting them. Their punch history stays.

```python
from pybiotime import ResignType

resign = bt.resigns.create(
    emp.id,
    resign_date=date(2026, 12, 31),
    resign_type=ResignType.QUIT,
    reason="Moved abroad",
)
```

`disable_attendance=True` (the default) stops BioTime calculating attendance for them.
To bring someone back, reinstate the resignation, not the employee:

```python
bt.resigns.reinstate([resign.id])
```

The resign endpoints are documented for BioTime 8.5 and 9.5. Older servers answer with
an error.
