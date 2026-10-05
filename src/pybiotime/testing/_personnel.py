"""The personnel endpoints of `FakeBioTime`: departments, areas, positions, employees, resigns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from pybiotime.compat import _FLAT_ATTENDANCE, _RELATION_NAMES

_FORMAT = "%Y-%m-%d %H:%M:%S"
_ROOT = "/personnel/api/"


@dataclass(frozen=True)
class _Coded:
    """How one code-and-name collection is spelled on the wire."""

    code: str
    name: str
    parent: str
    label: str
    #: Whether responses carry a ``parent_*_name`` copy, as areas and positions do.
    parent_name: bool


_CODED = {
    "departments": _Coded("dept_code", "dept_name", "parent_dept", "department", False),
    "areas": _Coded("area_code", "area_name", "parent_area", "area", True),
    "positions": _Coded("position_code", "position_name", "parent_position", "position", True),
}

# Codes BioTime 9.5 ignores on update: they are not in its update schema.
_FIXED_ON_UPDATE = {"departments": "dept_code", "employees": "emp_code"}

# Employee fields that can be written but are never read back, as on BioTime 9.5.
_WRITE_ONLY = ("self_password", "flow_role")


@dataclass(frozen=True)
class _Profile:
    """What the fake changes to imitate one BioTime version, as its manual shows it."""

    #: Title of the public ``/api/docs/`` page.
    docs_title: str
    #: 8.x: flat attendance flags, names beside relations and a password hash on
    #: employees; departments give their parent as an id, with its name beside it.
    flat: bool
    #: Whether the manual documents the resign API.
    resign_api: bool
    #: The self-service password hash in employee write answers (and in 8.x reads).
    password_hash: str | None = None
    #: ZKBio Time 9.0's punches: no names or labels, and sync fields of their own.
    zkbio_transactions: bool = False


_HASH_8X = "pbkdf2_sha256$36000$fake-hash"
_HASH_9X = "pbkdf2_sha256$390000$fake-hash"
_PROFILES = {
    "8.0": _Profile("BIOTIME API DOCS", flat=True, resign_api=False, password_hash=_HASH_8X),
    "8.5": _Profile("BIOTIME API DOCS", flat=True, resign_api=True, password_hash=_HASH_8X),
    "9.0": _Profile(
        "ZKBio Time API DOCS",
        flat=False,
        resign_api=False,
        password_hash=_HASH_9X,
        zkbio_transactions=True,
    ),
    "9.5": _Profile("BioTime 9.5 API DOCS", flat=False, resign_api=True),
}
#: Versions the fake can imitate.
VERSIONS = tuple(_PROFILES)

_EMPLOYEE_TEXT = (
    "first_name",
    "last_name",
    "nickname",
    "contact_tel",
    "office_tel",
    "mobile",
    "national",
    "city",
    "address",
    "postcode",
    "email",
    "enroll_sn",
    "ssn",
    "religion",
)


@dataclass(kw_only=True)
class PersonnelData:
    """Personnel records held by the fake. Rows are stored as the API would accept them."""

    departments: list[dict[str, Any]] = field(default_factory=list)
    areas: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    employees: list[dict[str, Any]] = field(default_factory=list)
    resigns: list[dict[str, Any]] = field(default_factory=list)
    #: Collections whose create answers echo the submitted fields without the new id.
    #: BioTime 9.5 does this for positions.
    creates_without_id: set[str] = field(default_factory=lambda: {"positions"})
    #: The BioTime version to imitate: "8.0", "8.5", "9.0" or "9.5".
    version: str = "9.5"
    #: Whether the resign API answers. ``None`` follows the version: the 8.5 and 9.5
    #: manuals document it. Set it to imitate a server that differs from its manual.
    resign_api: bool | None = None

    @property
    def has_resigns(self) -> bool:
        """Whether the resign API answers on this fake."""
        return self._profile.resign_api if self.resign_api is None else self.resign_api

    @property
    def _profile(self) -> _Profile:
        try:
            return _PROFILES[self.version]
        except KeyError:
            raise ValueError(f"version must be one of {', '.join(VERSIONS)}") from None

    def _new_id(self) -> int:
        raise NotImplementedError

    # --- data -------------------------------------------------------------------------

    def add_department(self, *, code: str, name: str, parent_id: int | None = None) -> int:
        return self._add_coded("departments", code, name, parent_id)

    def add_area(self, *, code: str, name: str, parent_id: int | None = None) -> int:
        return self._add_coded("areas", code, name, parent_id)

    def add_position(self, *, code: str, name: str, parent_id: int | None = None) -> int:
        return self._add_coded("positions", code, name, parent_id)

    def add_employee(
        self, *, emp_code: str, department_id: int, area_ids: list[int], **fields: Any
    ) -> int:
        new_id = self._new_id()
        row = {
            "id": new_id,
            "emp_code": emp_code,
            "department": department_id,
            "area": list(area_ids),
            "update_time": datetime.now().strftime(_FORMAT),
            **fields,
        }
        self.employees.append(row)
        return new_id

    def _add_coded(self, kind: str, code: str, name: str, parent_id: int | None) -> int:
        spec = _CODED[kind]
        new_id = self._new_id()
        row = {"id": new_id, spec.code: code, spec.name: name, spec.parent: parent_id}
        getattr(self, kind).append(row)
        return new_id

    # --- HTTP -------------------------------------------------------------------------

    def _personnel(
        self, method: str, path: str, params: dict[str, str], body: Any
    ) -> httpx.Response | None:
        """Answer a ``/personnel/api/`` request, or ``None`` if the path is not one of ours."""
        parts = path[len(_ROOT) :].strip("/").split("/")
        kind, rest = parts[0], parts[1:]
        if kind == "resigns" and rest == ["reinstatement"] and method == "POST":
            return self._reinstate(body)
        if kind not in (*_CODED, "employees", "resigns") or len(rest) > 1:
            return None
        rows: list[dict[str, Any]] = getattr(self, kind)
        if not rest:
            if method == "GET":
                rendered = [self._render(kind, r) for r in rows]
                return self._list(path, params, self._filter(kind, params, rendered))
            if method == "POST":
                return self._write(kind, None, body)
            return _detail(405, f'Method "{method}" not allowed.')

        row = next((r for r in rows if str(r["id"]) == rest[0]), None)
        if row is None:
            return _detail(404, "Not found.")
        if method == "GET":
            return httpx.Response(200, json=self._render(kind, row))
        if method in ("PATCH", "PUT"):
            return self._write(kind, row, body)
        if method == "DELETE":
            rows.remove(row)
            return httpx.Response(204)
        return _detail(405, f'Method "{method}" not allowed.')

    def _list(
        self, path: str, params: dict[str, str], rows: list[dict[str, Any]]
    ) -> httpx.Response:
        raise NotImplementedError

    def _filter(
        self, kind: str, params: dict[str, str], rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter rendered rows, so filters see the values a client sees."""
        keys: tuple[str, ...]
        if kind in _CODED:
            spec = _CODED[kind]
            keys = (spec.code, spec.name, spec.parent)
        elif kind == "employees":
            keys = ("emp_code", "first_name", "last_name", "department", "app_status")
            rows = sorted(rows, key=lambda r: str(r["emp_code"]))
        else:
            keys = ("employee", "resign_type")
        for key in keys:
            # An empty value does not filter, as with django-filter.
            if params.get(key, "") != "":
                rows = [r for r in rows if _shown(r.get(key)) == params[key]]
        return rows

    # --- writes -----------------------------------------------------------------------

    def _write(self, kind: str, row: dict[str, Any] | None, body: Any) -> httpx.Response:
        if not isinstance(body, dict):
            return httpx.Response(400, json={"non_field_errors": ["Invalid data."]})
        if row is not None:
            body = {k: v for k, v in body.items() if k != _FIXED_ON_UPDATE.get(kind)}
        merged = {**(row or {}), **body}
        errors = self._validate(kind, merged, row, set(body))
        if errors:
            return httpx.Response(400, json=errors)
        if row is None:
            row = {"id": self._new_id(), **body}
            getattr(self, kind).append(row)
            if kind in self.creates_without_id:
                return httpx.Response(201, json=body)
            status = 201
        else:
            row.update(body)
            status = 200
        if kind == "employees":
            row["update_time"] = datetime.now().strftime(_FORMAT)
        if kind == "resigns":
            return httpx.Response(status, json=self._render(kind, row))
        # Other write answers give relations as bare ids, as the vendor manuals show.
        answer = {k: v for k, v in row.items() if k not in _WRITE_ONLY}
        if kind == "employees":
            answer = self._employee_answer(answer)
        return httpx.Response(status, json=answer)

    def _employee_answer(self, answer: dict[str, Any]) -> dict[str, Any]:
        """Add what this version's manual shows in employee write answers."""
        profile = self._profile
        if profile.flat:
            answer.pop("update_time", None)
            for flag in _FLAT_ATTENDANCE:
                answer.setdefault(flag, True)
        if profile.password_hash:
            answer["self_password"] = profile.password_hash
            answer["flow_role"] = []
        return answer

    def _validate(
        self, kind: str, data: dict[str, Any], current: dict[str, Any] | None, sent: set[str]
    ) -> dict[str, list[str]]:
        errors: dict[str, list[str]] = {}
        required: tuple[str, ...]
        if kind in _CODED:
            spec = _CODED[kind]
            required = (spec.code, spec.name)
            unique = spec.code
            references = {spec.parent: kind}
        elif kind == "employees":
            required = ("emp_code", "department", "area")
            unique = "emp_code"
            references = {"department": "departments", "position": "positions"}
            areas = data.get("area")
            if "area" in sent and isinstance(areas, list):
                known = {a["id"] for a in self.areas}
                missing = [a for a in areas if a not in known]
                if missing:
                    errors["area"] = [f'Invalid pk "{missing[0]}" - object does not exist.']
        else:
            required = ("employee",)
            unique = "employee"
            references = {"employee": "employees"}

        for key in required:
            if data.get(key) in (None, "", []):
                errors[key] = ["This field is required."]
        clash = [
            r
            for r in getattr(self, kind)
            if r.get(unique) == data.get(unique) and (current is None or r["id"] != current["id"])
        ]
        if clash and unique not in errors:
            label = _CODED[kind].label if kind in _CODED else kind.rstrip("s")
            errors[unique] = [f"{label} with this {unique} already exists."]
        # Like a real server, check only the references that were sent.
        for key, target in references.items():
            value = data.get(key)
            if key not in sent or value is None:
                continue
            if not any(r["id"] == value for r in getattr(self, target)):
                errors[key] = [f'Invalid pk "{value}" - object does not exist.']
        return errors

    def _reinstate(self, body: Any) -> httpx.Response:
        ids = body.get("resigns") if isinstance(body, dict) else None
        if not isinstance(ids, list) or not ids:
            return httpx.Response(400, json={"resigns": ["This field is required."]})
        self.resigns = [r for r in self.resigns if r["id"] not in ids]
        return httpx.Response(200, json={"code": 0, "msg": "", "data": []})

    # --- rendering, in the BioTime 9.5 shape unless `version` says otherwise ----------

    def _render(self, kind: str, row: dict[str, Any]) -> dict[str, Any]:
        if kind in _CODED:
            return self._render_coded(kind, row)
        if kind == "employees":
            return self._render_employee(row)
        return self._render_resign(row)

    def _render_coded(self, kind: str, row: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        spec = _CODED[kind]
        parent_id = row.get(spec.parent)
        parent = next((r for r in getattr(self, kind) if r["id"] == parent_id), None)
        rendered: dict[str, Any] = {
            "id": row["id"],
            spec.code: row[spec.code],
            spec.name: row[spec.name],
        }
        if depth:
            rendered[spec.parent] = parent_id
            return rendered
        if kind == "departments" and self._profile.flat:
            # 8.x gives the parent department as an id, with its name beside it.
            rendered[spec.parent] = parent["id"] if parent else None
            rendered["parent_dept_name"] = parent[spec.name] if parent else None
            return rendered
        rendered[spec.parent] = self._render_coded(kind, parent, depth + 1) if parent else None
        if spec.parent_name:
            rendered[f"{spec.parent}_name"] = parent[spec.name] if parent else None
        return rendered

    def _render_employee(self, row: dict[str, Any]) -> dict[str, Any]:
        def ref(kind: str, object_id: Any) -> dict[str, Any] | None:
            spec = _CODED[kind]
            match = next((r for r in getattr(self, kind) if r["id"] == object_id), None)
            if match is None:
                return None
            return {"id": match["id"], spec.code: match[spec.code], spec.name: match[spec.name]}

        rendered: dict[str, Any] = {"id": row["id"], "emp_code": row["emp_code"]}
        rendered.update({key: row.get(key, "") for key in _EMPLOYEE_TEXT})
        rendered.update(
            {
                "format_name": f"{row['emp_code']} {row.get('first_name', '')}".strip(),
                "full_name": f"{row.get('first_name', '')} {row.get('last_name', '')}".strip(),
                "photo": "",
                "device_password": row.get("device_password"),
                "card_no": row.get("card_no"),
                "department": ref("departments", row.get("department")),
                "position": ref("positions", row.get("position")),
                "hire_date": row.get("hire_date", datetime.now().date().isoformat()),
                "gender": row.get("gender"),
                "birthday": row.get("birthday"),
                "verify_mode": row.get("verify_mode", 0),
                "emp_type": row.get("emp_type"),
                "attemployee": {
                    "id": row["id"],
                    "enable_attendance": True,
                    "enable_overtime": True,
                    "enable_holiday": True,
                    "enable_schedule": True,
                },
                "dev_privilege": row.get("dev_privilege", 0),
                # Areas deleted since are left out: a real server drops those links.
                "area": [r for r in (ref("areas", a) for a in row.get("area", [])) if r],
                "app_status": row.get("app_status", 0),
                "app_role": row.get("app_role", 1),
                "update_time": row.get("update_time"),
            }
        )
        rendered.update(
            {k: v for k, v in row.items() if k not in rendered and k not in _WRITE_ONLY}
        )
        if self._profile.flat:
            return _as_8x(rendered, self._profile.password_hash)
        return rendered

    def _render_resign(self, row: dict[str, Any]) -> dict[str, Any]:
        employee = next((e for e in self.employees if e["id"] == row["employee"]), {})
        person = {
            "id": row["employee"],
            "emp_code": employee.get("emp_code"),
            "first_name": employee.get("first_name", ""),
            "last_name": employee.get("last_name", ""),
        }
        return {
            "id": row["id"],
            "resign_date": row.get("resign_date"),
            "resign_type": row.get("resign_type"),
            "disableatt": row.get("disableatt"),
            "employee": person,
            "first_name": person["first_name"],
            "last_name": person["last_name"],
            "reason": row.get("reason", ""),
        }


def _detail(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"detail": message})


def _shown(value: Any) -> str:
    """A rendered value as a filter compares it: related objects by their id."""
    if isinstance(value, dict):
        value = value.get("id")
    return str(value)


def _as_8x(employee: dict[str, Any], password_hash: str | None) -> dict[str, Any]:
    """Reshape a 9.x employee the way BioTime 8.x sends it."""
    flags = employee.pop("attemployee")
    for key in ("format_name", "full_name", "photo", "update_time"):
        employee.pop(key, None)
    for flat, nested in _FLAT_ATTENDANCE.items():
        # A flag written to the employee wins over the default.
        employee.setdefault(flat, flags[nested])
    for relation, key in _RELATION_NAMES.items():
        ref = employee.get(relation)
        employee[key] = ref[key] if ref else None
    employee["area_name"] = ",".join(area["area_name"] for area in employee.get("area", []))
    # 8.x also returns the self-service password, as a hash.
    employee["self_password"] = password_hash
    return employee
