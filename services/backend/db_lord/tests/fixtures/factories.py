from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus

UNSET = object()


async def _persist_model[TOrm](session: AsyncSession, instance: TOrm) -> TOrm:
    """Persist a single ORM instance and refresh it."""
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


def _pick_by_seed[TValue](seed: UUID, values: tuple[TValue, ...]) -> TValue:
    return values[seed.int % len(values)]


def _default_patient_name(seed: UUID) -> str:
    return _pick_by_seed(
        seed,
        (
            "Alex Meyer",
            "Sam Rivera",
            "Jordan Kim",
            "Taylor Schmidt",
            "Robin Fischer",
            "Casey Weber",
        ),
    )


def _default_patient_sex(seed: UUID) -> str | None:
    return (None, "M", "F")[seed.int % 3]


def _default_patient_dob(seed: UUID) -> date:
    base = date(1969, 1, 1)
    return base + timedelta(days=seed.int % (45 * 365))


def _default_device_model(seed: UUID) -> str:
    return _pick_by_seed(seed, ("iPhone 15 Pro", "Galaxy S24", "Pixel 9", "Samsung smartfridge"))


def _default_wearable_model(seed: UUID) -> str:
    return _pick_by_seed(seed, ("Apple Watch Series 9", "Galaxy Watch 6", "Polar Sense", "Rolex Submariner"))


def _default_hardware_manufacturer(seed: UUID) -> str:
    return _pick_by_seed(seed, ("Apple", "Samsung", "Google", "Polar", "Withings"))


def _default_device_os_version(seed: UUID) -> str:
    return _pick_by_seed(seed, ("iOS 17.5", "Android 14", "Android 15", "Firmware 3.2.1"))


def _default_wearable_os_version(seed: UUID) -> str:
    return _pick_by_seed(seed, ("watchOS 10.4", "Wear OS 5", "Firmware 2.8.0", "Firmware 4.1.3"))


def _default_context_group_name(seed: UUID) -> str:
    return _pick_by_seed(
        seed, ("Six minute walking test", "ICU Alpha", "Ward B", "ER Intake", "Sleep Lab", "Remote Monitoring")
    )


def _default_context_coordinator(seed: UUID) -> str | None:
    return _pick_by_seed(seed, (None, "Dr. Kennedy", "Nurse Patel", "Dr. Neumann", "Ops Coordinator"))


def _default_assigned_from(case_id: UUID, asset_id: UUID) -> datetime:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return base + timedelta(seconds=(case_id.int ^ asset_id.int) % 86_400)


async def _create_patient_model(
    session: AsyncSession,
    *,
    name: str | None = None,
    charite_id: UUID | None = None,
    sex: str | None | object = UNSET,
    **kwargs: Any,
) -> Any:
    from app.db.postgres.orm import Patient

    patient_id = uuid7()
    patient = Patient(
        id=patient_id,
        charite_id=charite_id or uuid7(),
        name=name or _default_patient_name(patient_id),
        sex=_default_patient_sex(patient_id) if sex is UNSET else sex,
        dob=kwargs.pop("dob", _default_patient_dob(patient_id)),
        **kwargs,
    )
    return await _persist_model(session, patient)


def _serialize_patient(patient: Any) -> dict[str, Any]:
    return {
        "id": patient.id,
        "charite_id": patient.charite_id,
        "name": patient.name,
        "sex": patient.sex,
        "dob": patient.dob,
        "weight": patient.weight,
        "height": patient.height,
    }


async def _create_case_model(
    session: AsyncSession,
    *,
    patient_id: UUID,
    status: CaseStatus | str = CaseStatus.PLANNED,
    **kwargs: Any,
) -> Any:
    from app.db.postgres.orm import Case

    case = Case(
        id=kwargs.pop("id", uuid7()),
        patient_id=patient_id,
        status=status,
        **kwargs,
    )
    return await _persist_model(session, case)


def _serialize_case(case: Any) -> dict[str, Any]:
    return {
        "id": case.id,
        "patient_id": case.patient_id,
        "status": case.status,
    }


async def _create_device_model(
    session: AsyncSession,
    *,
    serial_nr: str | None = None,
    model: str | None = None,
    os_version: str | None = None,
    status: HardwareStatus | str = HardwareStatus.AVAILABLE,
    **kwargs: Any,
) -> Any:
    from app.db.postgres.orm import Device

    device_id = uuid7()
    device = Device(
        id=device_id,
        serial_nr=serial_nr or f"SN-{device_id.hex[-12:]}",
        model=model or _default_device_model(device_id),
        manufacturer=kwargs.pop("manufacturer", _default_hardware_manufacturer(device_id)),
        os_version=os_version or _default_device_os_version(device_id),
        status=status,
        **kwargs,
    )
    return await _persist_model(session, device)


def _serialize_hardware(hardware: Any) -> dict[str, Any]:
    return {
        "id": hardware.id,
        "serial_nr": hardware.serial_nr,
        "model": hardware.model,
        "manufacturer": hardware.manufacturer,
        "os_version": hardware.os_version,
        "status": hardware.status,
    }


async def _create_wearable_model(
    session: AsyncSession,
    *,
    serial_nr: str | None = None,
    model: str | None = None,
    os_version: str | None = None,
    status: HardwareStatus | str = HardwareStatus.AVAILABLE,
    **kwargs: Any,
) -> Any:
    from app.db.postgres.orm import Wearable

    wearable_id = uuid7()
    wearable = Wearable(
        id=wearable_id,
        serial_nr=serial_nr or f"WR-{wearable_id.hex[-12:]}",
        model=model or _default_wearable_model(wearable_id),
        manufacturer=kwargs.pop("manufacturer", _default_hardware_manufacturer(wearable_id)),
        os_version=os_version or _default_wearable_os_version(wearable_id),
        status=status,
        **kwargs,
    )
    return await _persist_model(session, wearable)


async def _create_context_model(
    session: AsyncSession,
    *,
    group_name: str | None = None,
    coordinator: str | None | object = UNSET,
    **kwargs: Any,
) -> Any:
    from app.db.postgres.orm import Context

    context_id = uuid7()
    context = Context(
        id=context_id,
        group_name=group_name or _default_context_group_name(context_id),
        coordinator=_default_context_coordinator(context_id) if coordinator is UNSET else coordinator,
        **kwargs,
    )
    return await _persist_model(session, context)


def _serialize_context(context: Any) -> dict[str, Any]:
    return {
        "id": context.id,
        "group_name": context.group_name,
        "coordinator": context.coordinator,
    }


@pytest.fixture
def patient_factory(db_session: AsyncSession):
    async def _create_patient(**kwargs: Any) -> dict[str, Any]:
        patient = await _create_patient_model(db_session, **kwargs)
        return _serialize_patient(patient)

    return _create_patient


@pytest.fixture
def case_factory(db_session: AsyncSession):
    async def _create_case(**kwargs: Any) -> dict[str, Any]:
        case = await _create_case_model(db_session, **kwargs)
        return _serialize_case(case)

    return _create_case


@pytest.fixture
def device_factory(db_session: AsyncSession):
    async def _create_device(**kwargs: Any) -> dict[str, Any]:
        device = await _create_device_model(db_session, **kwargs)
        return _serialize_hardware(device)

    return _create_device


@pytest.fixture
def device_orm_factory(db_session: AsyncSession):
    from app.db.postgres.orm import Device

    async def _create_device(**kwargs: Any) -> Device:
        return await _create_device_model(db_session, **kwargs)

    return _create_device


@pytest.fixture
def wearable_factory(db_session: AsyncSession):
    async def _create_wearable(**kwargs: Any) -> dict[str, Any]:
        wearable = await _create_wearable_model(db_session, **kwargs)
        return _serialize_hardware(wearable)

    return _create_wearable


@pytest.fixture
def wearable_orm_factory(db_session: AsyncSession):
    from app.db.postgres.orm import Wearable

    async def _create_wearable(**kwargs: Any) -> Wearable:
        return await _create_wearable_model(db_session, **kwargs)

    return _create_wearable


@pytest.fixture
def context_factory(db_session: AsyncSession):
    async def _create_context(**kwargs: Any) -> dict[str, Any]:
        context = await _create_context_model(db_session, **kwargs)
        return _serialize_context(context)

    return _create_context


@pytest.fixture
def case_device_link_factory(db_session: AsyncSession):
    from app.db.postgres.orm import CaseDevice

    async def _link_case_device(
        case_id: UUID,
        device_id: UUID,
        assigned_from: datetime | None = None,
        assigned_to: datetime | None = None,
    ) -> dict[str, Any]:
        link = CaseDevice(
            case_id=case_id,
            device_id=device_id,
            assigned_from=assigned_from or _default_assigned_from(case_id, device_id),
            assigned_to=assigned_to,
        )
        link = await _persist_model(db_session, link)
        return {
            "case_id": link.case_id,
            "device_id": link.device_id,
            "assigned_from": link.assigned_from,
            "assigned_to": link.assigned_to,
        }

    return _link_case_device


@pytest.fixture
def case_context_link_factory(db_session: AsyncSession):
    from app.db.postgres.orm import CaseContext

    async def _link_case_context(
        case_id: UUID,
        context_id: UUID,
    ) -> dict[str, Any]:
        link = CaseContext(
            case_id=case_id,
            context_id=context_id,
        )
        link = await _persist_model(db_session, link)
        return {
            "case_id": link.case_id,
            "context_id": link.context_id,
        }

    return _link_case_context
