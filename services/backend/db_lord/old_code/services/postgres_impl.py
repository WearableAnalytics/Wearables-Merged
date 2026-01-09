from datetime import datetime
from uuid import uuid7

from app.db_handler import ResourceConflictError
from models import sql_schema
from models.sql import case_contexts, contexts, devices, patients, wearables
from queries import crud_builder
from sqlalchemy import Boolean, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection


# TODO: Actually take advantage of async and dont just write it like syncronous code
# TODO: support pagination for list endpoints
# TODO: add list endpoints for all entities
# TODO: add more enpdoint functions for things like unassigning devices/wearables from cases, changing case status, etc.
# TODO: Probably dont generate UUIDs in the app, let the DB do it
class PostgresHandler:
    """
    Takes the connection provided by the route and executes the SQL built by the builder.
    """

    # Patients
    async def create_patient(
        self, conn: AsyncConnection, patient_data: sql_schema.PatientBase, id: str | None = None
    ) -> sql_schema.Patient:
        data = patient_data.model_dump()
        # Should we even allow passing in an ID here?
        if id:
            data["id"] = id
        elif "id" not in data:
            data["id"] = uuid7()

        stmt = crud_builder.build_insert("patients", data)
        result = await conn.execute(stmt)
        return sql_schema.Patient.model_validate(result.mappings().first())

    async def upsert_patient(
        self,
        conn: AsyncConnection,
        patient_id: str,
        patient_data: sql_schema.PatientBase,
    ) -> tuple[sql_schema.Patient, bool]:
        data = patient_data.model_dump(exclude_unset=True)
        data["id"] = patient_id

        stmt = pg_insert(patients).values(data)
        update_set = {k: v for k, v in data.items() if k != "id"}
        # Branch 1: Upsert without updates
        if not update_set:
            final_stmt = stmt.on_conflict_do_nothing(index_elements=[patients.c.id]).returning(
                patients
            )  # Only returns a row if insert happened
            result = await conn.execute(final_stmt)
            row = result.mappings().first()

            if row is not None:
                return sql_schema.Patient.model_validate(row), True

            # Row is None = Conflict (Patient exists) -> Fetch it
            res = await conn.execute(crud_builder.build_get_one("patients", patient_id))
            existing = res.mappings().first()

            if existing is None:
                # Should never happen unless race condition or DB error
                raise ValueError(f"Patient {patient_id} exists but could not be retrieved.")

            return sql_schema.Patient.model_validate(existing), False
        # Branch 2: Upsert with Updates
        # Upsert: Update fields if exists, requires postgres 18+ cause of OLD/NEW usage
        created_col = literal_column("OLD IS NULL", type_=Boolean).label("is_created")
        final_stmt = stmt.on_conflict_do_update(index_elements=[patients.c.id], set_=update_set).returning(
            patients, created_col
        )

        result = await conn.execute(final_stmt)
        row = result.mappings().first()

        if row is None:
            # Should be impossible unless RLS policies hide the row
            raise ValueError(f"Upsert returned no row for patient id {patient_id}.")

        created = row["is_created"]
        return sql_schema.Patient.model_validate(row), created

    async def get_patient(self, conn: AsyncConnection, patient_id: str) -> sql_schema.Patient | None:
        stmt = crud_builder.build_get_one("patients", patient_id)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Patient.model_validate(row) if row else None

    async def update_patient(
        self, conn: AsyncConnection, patient_id: str, patient_data: sql_schema.PatientBase
    ) -> sql_schema.Patient | None:
        data = patient_data.model_dump(exclude_unset=True)
        if not data:
            return await self.get_patient(conn, patient_id)
        stmt = crud_builder.build_update("patients", patient_id, data)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Patient.model_validate(row) if row else None

    async def delete_patient(self, conn: AsyncConnection, patient_id: str) -> bool:
        stmt = crud_builder.build_delete("patients", patient_id)
        result = await conn.execute(stmt)
        return result.rowcount > 0

    # Wearables
    async def create_wearable(
        self, conn: AsyncConnection, wearable_base: sql_schema.DeviceBase, id: str | None = None
    ) -> sql_schema.Wearable:
        data = wearable_base.model_dump()
        if id:
            data["id"] = id
        elif "id" not in data:
            data["id"] = uuid7()

        stmt = crud_builder.build_insert("wearables", data)
        result = await conn.execute(stmt)
        return sql_schema.Wearable.model_validate(result.mappings().first())

    async def upsert_wearable(
        self,
        conn: AsyncConnection,
        wearable_id: str,
        wearable_base: sql_schema.DeviceBase,
    ) -> tuple[sql_schema.Wearable, bool]:
        data = wearable_base.model_dump(exclude_unset=True)
        data["id"] = wearable_id

        stmt = pg_insert(wearables).values(data)
        update_set = {k: v for k, v in data.items() if k != "id"}

        # Branch 1: Upsert without updates
        if not update_set:
            final_stmt = stmt.on_conflict_do_nothing(index_elements=[wearables.c.id]).returning(wearables)
            result = await conn.execute(final_stmt)
            row = result.mappings().first()

            if row is not None:
                return sql_schema.Wearable.model_validate(row), True

            # Conflict -> Fetch Existing
            res = await conn.execute(crud_builder.build_get_one("wearables", wearable_id))
            existing = res.mappings().first()
            if existing is None:
                raise ValueError(f"Wearable {wearable_id} could not be retrieved.")
            return sql_schema.Wearable.model_validate(existing), False

        # Branch 2: Upsert with Updates
        created_col = literal_column("OLD IS NULL", type_=Boolean).label("is_created")
        final_stmt = stmt.on_conflict_do_update(index_elements=[wearables.c.id], set_=update_set).returning(
            wearables, created_col
        )

        result = await conn.execute(final_stmt)
        row = result.mappings().first()

        if row is None:
            raise ValueError(f"Upsert returned no row for wearable {wearable_id}.")

        created = row["is_created"]
        return sql_schema.Wearable.model_validate(row), created

    async def get_wearable(self, conn: AsyncConnection, wearable_id: str) -> sql_schema.Wearable | None:
        stmt = crud_builder.build_get_one("wearables", wearable_id)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Wearable.model_validate(row) if row else None

    async def update_wearable(
        self, conn: AsyncConnection, wearable_id: str, wearable_base: sql_schema.DeviceBase
    ) -> sql_schema.Wearable | None:
        data = wearable_base.model_dump(exclude_unset=True)
        if not data:
            return await self.get_wearable(conn, wearable_id)
        stmt = crud_builder.build_update("wearables", wearable_id, data)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Wearable.model_validate(row) if row else None

    async def delete_wearable(self, conn: AsyncConnection, wearable_id: str) -> bool:
        stmt = crud_builder.build_delete("wearables", wearable_id)
        result = await conn.execute(stmt)
        return result.rowcount > 0

    # Devices
    async def create_device(
        self, conn: AsyncConnection, device_base: sql_schema.DeviceBase, id: str | None = None
    ) -> sql_schema.Device:
        data = device_base.model_dump()
        if id:
            data["id"] = id
        elif "id" not in data:
            data["id"] = uuid7()

        stmt = crud_builder.build_insert("devices", data)
        result = await conn.execute(stmt)
        return sql_schema.Device.model_validate(result.mappings().first())

    async def upsert_device(
        self,
        conn: AsyncConnection,
        device_id: str,
        device_base: sql_schema.DeviceBase,
    ) -> tuple[sql_schema.Device, bool]:
        data = device_base.model_dump(exclude_unset=True)
        data["id"] = device_id

        stmt = pg_insert(devices).values(data)
        update_set = {k: v for k, v in data.items() if k != "id"}
        # Branch 1: Upsert without updates
        if not update_set:
            final_stmt = stmt.on_conflict_do_nothing(index_elements=[devices.c.id]).returning(devices)
            result = await conn.execute(final_stmt)
            row = result.mappings().first()

            if row is not None:
                return sql_schema.Device.model_validate(row), True
            # Conflict -> Fetch Existing
            res = await conn.execute(crud_builder.build_get_one("devices", device_id))
            existing = res.mappings().first()
            if existing is None:
                raise ValueError(f"Device {device_id} could not be retrieved.")
            return sql_schema.Device.model_validate(existing), False
        # Branch 2: Upsert with Updates
        created_col = literal_column("OLD IS NULL", type_=Boolean).label("is_created")
        final_stmt = stmt.on_conflict_do_update(index_elements=[devices.c.id], set_=update_set).returning(
            devices, created_col
        )

        result = await conn.execute(final_stmt)
        row = result.mappings().first()

        if row is None:
            raise ValueError(f"Upsert returned no row for device {device_id}.")

        created = row["is_created"]
        return sql_schema.Device.model_validate(row), created

    async def get_device(self, conn: AsyncConnection, device_id: str) -> sql_schema.Device | None:
        stmt = crud_builder.build_get_one("devices", device_id)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Device.model_validate(row) if row else None

    async def update_device(
        self, conn: AsyncConnection, device_id: str, device_base: sql_schema.DeviceBase
    ) -> sql_schema.Device | None:
        data = device_base.model_dump(exclude_unset=True)
        if not data:
            return await self.get_device(conn, device_id)
        stmt = crud_builder.build_update("devices", device_id, data)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Device.model_validate(row) if row else None

    async def delete_device(self, conn: AsyncConnection, device_id: str) -> bool:
        stmt = crud_builder.build_delete("devices", device_id)
        result = await conn.execute(stmt)
        return result.rowcount > 0

    # Contexts
    async def create_context(
        self, conn: AsyncConnection, context_base: sql_schema.ContextBase, id: str | None = None
    ) -> sql_schema.Context:
        data = context_base.model_dump()
        if id:
            data["id"] = id
        elif "id" not in data:
            data["id"] = uuid7()

        stmt = crud_builder.build_insert("contexts", data)
        result = await conn.execute(stmt)
        return sql_schema.Context.model_validate(result.mappings().first())

    async def upsert_context(
        self,
        conn: AsyncConnection,
        context_id: str,
        context_base: sql_schema.ContextBase,
    ) -> tuple[sql_schema.Context, bool]:
        data = context_base.model_dump(exclude_unset=True)
        data["id"] = context_id

        stmt = pg_insert(contexts).values(data)
        update_set = {k: v for k, v in data.items() if k != "id"}
        # Branch 1: Upsert without updates
        if not update_set:
            final_stmt = stmt.on_conflict_do_nothing(index_elements=[contexts.c.id]).returning(contexts)
            result = await conn.execute(final_stmt)
            row = result.mappings().first()

            if row is not None:
                return sql_schema.Context.model_validate(row), True
            # Conflict -> Fetch Existing
            res = await conn.execute(crud_builder.build_get_one("contexts", context_id))
            existing = res.mappings().first()
            if existing is None:
                raise ValueError(f"Context {context_id} could not be retrieved.")
            return sql_schema.Context.model_validate(existing), False
        # Branch 2: Upsert with Updates
        created_col = literal_column("OLD IS NULL", type_=Boolean).label("is_created")
        final_stmt = stmt.on_conflict_do_update(index_elements=[contexts.c.id], set_=update_set).returning(
            contexts, created_col
        )

        result = await conn.execute(final_stmt)
        row = result.mappings().first()

        if row is None:
            raise ValueError(f"Upsert returned no row for context {context_id}.")

        created = row["is_created"]
        return sql_schema.Context.model_validate(row), created

    async def get_context(self, conn: AsyncConnection, context_id: str) -> sql_schema.Context | None:
        stmt = crud_builder.build_get_one("contexts", context_id)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Context.model_validate(row) if row else None

    async def update_context(
        self, conn: AsyncConnection, context_id: str, context_base: sql_schema.ContextBase
    ) -> sql_schema.Context | None:
        data = context_base.model_dump(exclude_unset=True)
        if not data:
            return await self.get_context(conn, context_id)
        stmt = crud_builder.build_update("contexts", context_id, data)
        result = await conn.execute(stmt)
        row = result.mappings().first()
        return sql_schema.Context.model_validate(row) if row else None

    async def delete_context(self, conn: AsyncConnection, context_id: str) -> bool:
        stmt = crud_builder.build_delete("contexts", context_id)
        result = await conn.execute(stmt)
        return result.rowcount > 0

    # Cases
    # TODO: use transactions for cases
    async def create_case(self, conn: AsyncConnection, case_data: sql_schema.CaseCreate) -> sql_schema.Case:
        data = case_data.model_dump()
        # Does this even make sense? when creating a case arent you almost always linking a single device/wearable/context?
        # Also we should probably validate that the linked IDs exist before attempting to create the case, maybe even optionally creating them if they dont exist and enough info is provided
        context_ids = data.pop("linked_context_ids", [])
        device_ids = data.pop("linked_device_ids", [])
        wearable_ids = data.pop("linked_wearable_ids", [])

        if "id" not in data:
            data["id"] = uuid7()

        stmt = crud_builder.build_insert("cases", data)
        await conn.execute(stmt)  # TODO: Add try-except for insert failures (e.g., unique constraint violations, ...)
        # TODO: change so that you can also set a assigned_from time when creating the case
        # TODO: create a coherent way to handle timezones throughout the lord and db(timestamptz?)
        current_time = datetime.now()
        # GATHER !!!!
        if context_ids:
            rows = [{"case_id": data["id"], "context_id": x} for x in context_ids]
            await conn.execute(crud_builder.build_link_insert("context", rows))

        if device_ids:
            rows = [{"case_id": data["id"], "device_id": x, "assigned_from": current_time} for x in device_ids]
            await conn.execute(crud_builder.build_link_insert("device", rows))

        if wearable_ids:
            rows = [{"case_id": data["id"], "wearable_id": x, "assigned_from": current_time} for x in wearable_ids]
            await conn.execute(crud_builder.build_link_insert("wearable", rows))

        # TODO: return the Case model directly from the insert result and link data without re-fetching via get_case (also figure out if we should send back details or just IDs for linked items)
        # TODO: Add overall error handling (e.g., rollback transaction on failure) and logging for debugging
        return await self.get_case(conn, str(data["id"]))

    async def get_case(
        self, conn: AsyncConnection, case_id: str, expand: list[str] | None = None
    ) -> sql_schema.Case | None:
        if expand is None:
            expand = []
        stmt = crud_builder.build_get_one("cases", case_id)
        row = (await conn.execute(stmt)).mappings().first()
        if not row:
            return None

        data = dict(row)
        # gather
        device_link_rows = (
            (await conn.execute(crud_builder.build_link_select("device", {"case_id": case_id}))).mappings().all()
        )
        data["linked_device_ids"] = [r["device_id"] for r in device_link_rows]

        wearable_link_rows = (
            (await conn.execute(crud_builder.build_link_select("wearable", {"case_id": case_id}))).mappings().all()
        )
        data["linked_wearable_ids"] = [r["wearable_id"] for r in wearable_link_rows]

        context_link_rows = (
            (await conn.execute(crud_builder.build_link_select("context", {"case_id": case_id}))).mappings().all()
        )
        data["linked_context_ids"] = [r["context_id"] for r in context_link_rows]

        # Fetch expanded details if requested
        if "patient" in expand:
            pat_row = (
                (await conn.execute(crud_builder.build_get_one("patients", data["patient_id"]))).mappings().first()
            )
            data["patient_details"] = pat_row
        else:
            data["patient_details"] = None

        if "devices" in expand:
            rich_rows = (
                (await conn.execute(crud_builder.build_case_rich_select("devices", "device", case_id))).mappings().all()
            )
            data["linked_device_details"] = rich_rows
        else:
            data["linked_device_details"] = None

        if "wearables" in expand:
            rich_rows = (
                (await conn.execute(crud_builder.build_case_rich_select("wearables", "wearable", case_id)))
                .mappings()
                .all()
            )
            data["linked_wearable_details"] = rich_rows
        else:
            data["linked_wearable_details"] = None

        if "contexts" in expand:
            rich_rows = (
                (await conn.execute(crud_builder.build_case_rich_select("contexts", "context", case_id)))
                .mappings()
                .all()
            )
            data["linked_context_details"] = rich_rows
        else:
            data["linked_context_details"] = None

        return sql_schema.Case.model_validate(data)

    # Link helpers
    async def link_device(
        self, conn: AsyncConnection, case_id: str, device_id: str, assigned_from: datetime | None = None
    ):
        data = {
            "case_id": case_id,
            "device_id": device_id,
            "assigned_from": assigned_from or datetime.now(),
            "assigned_to": None,
        }
        try:
            await conn.execute(crud_builder.build_link_insert("device", data))
        except IntegrityError as e:
            if "unique_active_device_assignment" in str(e):
                raise ResourceConflictError(f"Device {device_id} is currently active in another case.")
            raise e

    async def link_wearable(
        self, conn: AsyncConnection, case_id: str, wearable_id: str, assigned_from: datetime | None = None
    ):
        data = {
            "case_id": case_id,
            "wearable_id": wearable_id,
            "assigned_from": assigned_from or datetime.now(),
            "assigned_to": None,
        }
        try:
            await conn.execute(crud_builder.build_link_insert("wearable", data))
        except IntegrityError as e:
            if "unique_active_wearable_assignment" in str(e):
                raise ResourceConflictError(f"Wearable {wearable_id} is currently active in another case.")
            raise e

    async def link_context(self, conn: AsyncConnection, case_id: str, context_id: str):
        data = {"case_id": case_id, "context_id": context_id}
        stmt = pg_insert(case_contexts).values(data)
        await conn.execute(stmt.on_conflict_do_nothing(index_elements=["case_id", "context_id"]))
