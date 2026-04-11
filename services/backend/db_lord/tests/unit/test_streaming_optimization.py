import json
from collections.abc import AsyncIterator, Mapping
from uuid import uuid7

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.streaming import iter_ndjson
from app.db.postgres.repos.patient_repo import PatientRepo
from app.schemas.case import CaseResponse

pytestmark = pytest.mark.anyio


async def _collect(iterator: AsyncIterator[bytes]) -> list[bytes]:
    return [chunk async for chunk in iterator]


class TestIterNdjson:
    async def test_raw_mapping_path_uses_orjson_fallback(self):
        async def rows() -> AsyncIterator[dict[str, object]]:
            yield {"name": "alpha", "value": 1}

        chunks = await _collect(iter_ndjson(rows()))
        assert len(chunks) == 1
        assert chunks[0].endswith(b"\n")
        assert json.loads(chunks[0]) == {"name": "alpha", "value": 1}

    async def test_schema_path_validates_and_serializes(self):
        async def rows() -> AsyncIterator[dict[str, object]]:
            yield {
                "id": uuid7(),
                "status": "PLANNED",
                "patient_id": uuid7(),
            }

        chunks = await _collect(iter_ndjson(rows(), schema=CaseResponse))
        assert len(chunks) == 1
        assert chunks[0].endswith(b"\n")
        payload = json.loads(chunks[0])
        assert payload["status"] == "PLANNED"

    async def test_schema_path_raises_on_invalid_payload(self):
        async def rows() -> AsyncIterator[dict[str, object]]:
            yield {
                "id": uuid7(),
                "status": "NOT_A_VALID_STATUS",
                "patient_id": uuid7(),
            }

        with pytest.raises(ValidationError):
            await _collect(iter_ndjson(rows(), schema=CaseResponse))


class TestRepoStreamAsMapping:
    async def test_stream_all_as_mapping_returns_row_mappings(
        self,
        db_session: AsyncSession,
        patient_factory,
    ):
        patient_one = await patient_factory(name="Stream Mapping 1")
        patient_two = await patient_factory(name="Stream Mapping 2")
        repo = PatientRepo(db_session)

        orm_rows = [row async for row in repo.stream_all(batch_size=100)]
        mapped_rows = [row async for row in repo.stream_all(batch_size=100, as_mapping=True)]

        assert orm_rows
        assert mapped_rows
        assert isinstance(mapped_rows[0], Mapping)

        orm_ids = {row.id for row in orm_rows}
        mapping_ids = {str(row["id"]) if isinstance(row, Mapping) else str(row.id) for row in mapped_rows}

        assert str(patient_one["id"]) in mapping_ids
        assert str(patient_two["id"]) in mapping_ids
        assert {str(orm_id) for orm_id in orm_ids} == mapping_ids
