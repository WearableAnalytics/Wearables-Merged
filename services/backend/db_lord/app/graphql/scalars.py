from datetime import datetime
from typing import TYPE_CHECKING

import strawberry
from pydantic import AwareDatetime as PydanticAwareDatetime
from pydantic import TypeAdapter, ValidationError

from app.core.utils import to_utc

_aware_datetime_adapter = TypeAdapter(PydanticAwareDatetime)


def _parse_aware_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Datetime value must be an ISO 8601 string.")

    raw = value.strip()
    if not raw:
        raise ValueError("Datetime value must be a non-empty ISO 8601 string.")
    try:
        return to_utc(_aware_datetime_adapter.validate_python(raw))
    except ValidationError as exc:
        if any(error.get("type") == "timezone_aware" for error in exc.errors()):
            raise ValueError("Datetime must include timezone information.") from exc
        raise ValueError("Invalid ISO 8601 datetime.") from exc


def _serialize_aware_datetime(value: datetime) -> str:
    return to_utc(value).isoformat().replace("+00:00", "Z")


if TYPE_CHECKING:
    type AwareDateTime = datetime
else:
    AwareDateTime = strawberry.scalar(
        datetime,
        name="AwareDateTime",
        description="ISO 8601 datetime with timezone offset.",
        serialize=_serialize_aware_datetime,
        parse_value=_parse_aware_datetime,
    )
