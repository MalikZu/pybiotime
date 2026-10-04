from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from pybiotime._async.pagination import AsyncPager
from pybiotime._core import build_model, merge_params
from pybiotime._personnel import employee_changes, employee_payload, resign_payload
from pybiotime.models import Area, BioTimeModel, Department, Employee, Position, Resign

if TYPE_CHECKING:
    from pybiotime._async.client import AsyncBioTimeClient

__all__ = ["AsyncAreas", "AsyncDepartments", "AsyncEmployees", "AsyncPositions", "AsyncResigns"]

M = TypeVar("M", bound=BioTimeModel)


class AsyncCodedResource(Generic[M]):
    """Shared code for departments, areas and positions: objects with a code and a name."""

    path: ClassVar[str]
    model: type[M]
    code_field: ClassVar[str]
    name_field: ClassVar[str]
    parent_field: ClassVar[str]

    def __init__(self, client: AsyncBioTimeClient) -> None:
        self._client = client

    def list(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        parent_id: int | None = None,
        page_size: int | None = None,
    ) -> AsyncPager[M]:
        params = merge_params(
            {self.code_field: code, self.name_field: name, self.parent_field: parent_id}
        )
        return AsyncPager(self._client, self.path, params, self._parse, page_size)

    async def get(self, object_id: int) -> M:
        """Fetch one by id. Raises `NotFoundError` if there is none."""
        return await self._call("GET", f"{self.path}{object_id}/")

    async def get_by_code(self, code: str) -> M | None:
        """Fetch the one with exactly this code, or ``None``."""
        async for item in self.list(code=code):
            if getattr(item, self.code_field) == code:
                return item
        return None

    async def create(self, code: str, name: str, *, parent_id: int | None = None) -> M:
        body: dict[str, Any] = {self.code_field: code, self.name_field: name}
        if parent_id is not None:
            body[self.parent_field] = parent_id
        return await self._call("POST", self.path, json=body)

    async def update(
        self,
        object_id: int,
        *,
        code: str | None = None,
        name: str | None = None,
        parent_id: int | None = None,
    ) -> M:
        """Change the given fields; others stay as they are."""
        changes = {
            key: value
            for key, value in (
                (self.code_field, code),
                (self.name_field, name),
                (self.parent_field, parent_id),
            )
            if value is not None
        }
        return await self._call("PATCH", f"{self.path}{object_id}/", json=changes)

    async def delete(self, object_id: int) -> None:
        await self._client._request("DELETE", f"{self.path}{object_id}/")

    async def upsert(self, code: str, name: str, *, parent_id: int | None = None) -> M:
        """Create it, or update the name and parent of the existing one with this code.

        Sends a change only when something differs. `parent_id=None` leaves the parent as is.
        """
        existing = await self.get_by_code(code)
        if existing is None:
            return await self.create(code, name, parent_id=parent_id)
        parent = getattr(existing, self.parent_field)
        current_parent = parent.id if parent is not None else None
        new_name = name if getattr(existing, self.name_field) != name else None
        new_parent = parent_id if parent_id is not None and parent_id != current_parent else None
        if new_name is None and new_parent is None:
            return existing
        object_id: int = getattr(existing, "id")  # noqa: B009 - M is generic
        return await self.update(object_id, name=new_name, parent_id=new_parent)

    async def _call(self, method: str, path: str, json: Any = None) -> M:
        body = await self._client._request(method, path, json=json)
        return build_model(self.model, body, timezone=self._client.timezone, path=path)

    def _parse(self, item: dict[str, Any]) -> M:
        return build_model(self.model, item, timezone=self._client.timezone, path=self.path)


class AsyncDepartments(AsyncCodedResource[Department]):
    """Departments: ``/personnel/api/departments/``."""

    path = "/personnel/api/departments/"
    model = Department
    code_field = "dept_code"
    name_field = "dept_name"
    parent_field = "parent_dept"


class AsyncAreas(AsyncCodedResource[Area]):
    """Areas, which group devices and the people allowed on them: ``/personnel/api/areas/``."""

    path = "/personnel/api/areas/"
    model = Area
    code_field = "area_code"
    name_field = "area_name"
    parent_field = "parent_area"


class AsyncPositions(AsyncCodedResource[Position]):
    """Positions (job titles): ``/personnel/api/positions/``."""

    path = "/personnel/api/positions/"
    model = Position
    code_field = "position_code"
    name_field = "position_name"
    parent_field = "parent_position"


class AsyncEmployees:
    """Employees: ``/personnel/api/employees/``.

    Writes take the common fields as keyword arguments. Pass any other field, such as a
    custom attribute, in `fields` under its API name, for example ``{"Global ID": "..."}``.
    """

    path = "/personnel/api/employees/"

    def __init__(self, client: AsyncBioTimeClient) -> None:
        self._client = client

    def list(
        self,
        *,
        emp_code: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        department_id: int | None = None,
        app_status: int | None = None,
        page_size: int | None = None,
    ) -> AsyncPager[Employee]:
        params = merge_params(
            {
                "emp_code": emp_code,
                "first_name": first_name,
                "last_name": last_name,
                "department": department_id,
                "app_status": app_status,
            }
        )
        return AsyncPager(self._client, self.path, params, self._parse, page_size)

    async def get(self, employee_id: int) -> Employee:
        """Fetch one employee by id. Raises `NotFoundError` if there is none."""
        return await self._call("GET", f"{self.path}{employee_id}/")

    async def get_by_code(self, emp_code: str) -> Employee | None:
        """Fetch the employee with exactly this code, or ``None``.

        Some servers match codes by prefix, so the result is checked here too.
        """
        async for employee in self.list(emp_code=emp_code):
            if employee.emp_code == emp_code:
                return employee
        return None

    async def create(
        self,
        emp_code: str,
        *,
        department_id: int,
        area_ids: Sequence[int],
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
        position_id: int | None = None,
        hire_date: date | None = None,
        birthday: date | None = None,
        gender: str | None = None,
        emp_type: int | None = None,
        email: str | None = None,
        mobile: str | None = None,
        card_no: str | None = None,
        device_password: str | None = None,
        app_status: int | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> Employee:
        """Create an employee. BioTime requires a department and at least one area."""
        body = employee_payload(
            emp_code=emp_code,
            department_id=department_id,
            area_ids=area_ids,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            position_id=position_id,
            hire_date=hire_date,
            birthday=birthday,
            gender=gender,
            emp_type=emp_type,
            email=email,
            mobile=mobile,
            card_no=card_no,
            device_password=device_password,
            app_status=app_status,
            fields=fields,
        )
        return await self._call("POST", self.path, json=body)

    async def update(
        self,
        employee_id: int,
        *,
        emp_code: str | None = None,
        department_id: int | None = None,
        area_ids: Sequence[int] | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
        position_id: int | None = None,
        hire_date: date | None = None,
        birthday: date | None = None,
        gender: str | None = None,
        emp_type: int | None = None,
        email: str | None = None,
        mobile: str | None = None,
        card_no: str | None = None,
        device_password: str | None = None,
        app_status: int | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> Employee:
        """Change the given fields; others stay as they are.

        A ``None`` argument means "leave it". To clear a field, pass it in `fields`, for
        example ``fields={"position": None}``.
        """
        body = employee_payload(
            emp_code=emp_code,
            department_id=department_id,
            area_ids=area_ids,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            position_id=position_id,
            hire_date=hire_date,
            birthday=birthday,
            gender=gender,
            emp_type=emp_type,
            email=email,
            mobile=mobile,
            card_no=card_no,
            device_password=device_password,
            app_status=app_status,
            fields=fields,
        )
        return await self._call("PATCH", f"{self.path}{employee_id}/", json=body)

    async def delete(self, employee_id: int) -> None:
        """Delete an employee. To keep their history, resign them instead."""
        await self._client._request("DELETE", f"{self.path}{employee_id}/")

    async def upsert(
        self,
        emp_code: str,
        *,
        department_id: int,
        area_ids: Sequence[int],
        first_name: str | None = None,
        last_name: str | None = None,
        nickname: str | None = None,
        position_id: int | None = None,
        hire_date: date | None = None,
        birthday: date | None = None,
        gender: str | None = None,
        emp_type: int | None = None,
        email: str | None = None,
        mobile: str | None = None,
        card_no: str | None = None,
        device_password: str | None = None,
        app_status: int | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> Employee:
        """Create the employee, or bring the existing one with this code up to date.

        Only fields that differ are sent, so running it again changes nothing. ``None``
        arguments leave the existing value alone.
        """
        desired = employee_payload(
            emp_code=emp_code,
            department_id=department_id,
            area_ids=area_ids,
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            position_id=position_id,
            hire_date=hire_date,
            birthday=birthday,
            gender=gender,
            emp_type=emp_type,
            email=email,
            mobile=mobile,
            card_no=card_no,
            device_password=device_password,
            app_status=app_status,
            fields=fields,
        )
        existing = await self.get_by_code(emp_code)
        if existing is None:
            return await self._call("POST", self.path, json=desired)
        changes = employee_changes(existing, desired)
        if not changes:
            return existing
        return await self._call("PATCH", f"{self.path}{existing.id}/", json=changes)

    async def _call(self, method: str, path: str, json: Any = None) -> Employee:
        body = await self._client._request(method, path, json=json)
        return build_model(Employee, body, timezone=self._client.timezone, path=path)

    def _parse(self, item: dict[str, Any]) -> Employee:
        return build_model(Employee, item, timezone=self._client.timezone, path=self.path)


class AsyncResigns:
    """Resignations: ``/personnel/api/resigns/``.

    Documented for BioTime 8.5 and 9.5. Older servers answer with an error.
    """

    path = "/personnel/api/resigns/"

    def __init__(self, client: AsyncBioTimeClient) -> None:
        self._client = client

    def list(
        self,
        *,
        employee_id: int | None = None,
        resign_type: int | None = None,
        page_size: int | None = None,
    ) -> AsyncPager[Resign]:
        params = merge_params({"employee": employee_id, "resign_type": resign_type})
        return AsyncPager(self._client, self.path, params, self._parse, page_size)

    async def get(self, resign_id: int) -> Resign:
        return await self._call("GET", f"{self.path}{resign_id}/")

    async def create(
        self,
        employee_id: int,
        *,
        resign_date: date,
        resign_type: int,
        disable_attendance: bool = True,
        reason: str = "",
    ) -> Resign:
        """Record that an employee left. Compare `resign_type` with `pybiotime.ResignType`.

        With `disable_attendance`, BioTime stops calculating attendance for them.
        """
        body = resign_payload(
            employee_id=employee_id,
            resign_date=resign_date,
            resign_type=resign_type,
            disable_attendance=disable_attendance,
            reason=reason,
        )
        return await self._call("POST", self.path, json=body)

    async def update(
        self,
        resign_id: int,
        *,
        resign_date: date | None = None,
        resign_type: int | None = None,
        disable_attendance: bool | None = None,
        reason: str | None = None,
    ) -> Resign:
        """Change the given fields; others stay as they are."""
        body = resign_payload(
            resign_date=resign_date,
            resign_type=resign_type,
            disable_attendance=disable_attendance,
            reason=reason,
        )
        return await self._call("PATCH", f"{self.path}{resign_id}/", json=body)

    async def delete(self, resign_id: int) -> None:
        await self._client._request("DELETE", f"{self.path}{resign_id}/")

    async def reinstate(self, resign_ids: Sequence[int]) -> None:
        """Bring resigned employees back. Takes resignation ids, not employee ids."""
        await self._client._request(
            "POST", f"{self.path}reinstatement/", json={"resigns": list(resign_ids)}
        )

    async def _call(self, method: str, path: str, json: Any = None) -> Resign:
        body = await self._client._request(method, path, json=json)
        return build_model(Resign, body, timezone=self._client.timezone, path=path)

    def _parse(self, item: dict[str, Any]) -> Resign:
        return build_model(Resign, item, timezone=self._client.timezone, path=self.path)
