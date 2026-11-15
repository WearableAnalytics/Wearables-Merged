"""Legacy numeric batches remain accepted; v1 adds explicit source identity."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class DeviceInfo(InputModel):
    platform: str = Field(min_length=1, max_length=64)
    deviceId: str = Field(min_length=1, max_length=256)
    authorizationToken: str | None = Field(default="", max_length=8192)


class BatchInfo(InputModel):
    collectionStart: datetime
    collectionEnd: datetime
    lastSendTime: datetime | None = None


class Reading(InputModel):
    type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,95}$")
    value: float
    unit: str = Field(min_length=1, max_length=96)
    sourceRecordId: str | None = Field(default=None, min_length=1, max_length=512)


class InstantaneousMeasurement(Reading):
    timestamp: datetime


class CumulativeMeasurement(Reading):
    periodStart: datetime
    periodEnd: datetime
    duration: int = Field(ge=0)


class DurationMeasurement(Reading):
    startTime: datetime
    endTime: datetime
    durationMinutes: int = Field(ge=0)


class Measurements(InputModel):
    instantaneous: list[InstantaneousMeasurement] = Field(default_factory=list)
    cumulative: list[CumulativeMeasurement] = Field(default_factory=list)
    duration: list[DurationMeasurement] = Field(default_factory=list)


class IngestPayload(InputModel):
    contractVersion: Literal["wearables-numeric/1"] | None = None
    sourceId: str | None = Field(default=None, min_length=1, max_length=256)
    deviceInfo: DeviceInfo
    batchInfo: BatchInfo
    measurements: Measurements
    sourceName: str = Field(min_length=1, max_length=256)
    sourcePlatform: str | None = Field(default=None, max_length=96)
    totalStepsToday: int | None = Field(default=None, ge=0)
    timestamp: datetime

    def readings(self):
        for category in ("instantaneous", "cumulative", "duration"):
            for index, reading in enumerate(getattr(self.measurements, category)):
                yield category, index, reading

    @model_validator(mode="after")
    def check_intervals(self):
        strict = self.contractVersion is not None
        if strict and (not self.sourceId or not self.sourcePlatform):
            raise ValueError("The versioned contract requires sourceId and sourcePlatform")
        try:
            if self.batchInfo.collectionStart > self.batchInfo.collectionEnd:
                raise ValueError("Collection interval is reversed")
            for category, _, reading in self.readings():
                if strict and not reading.sourceRecordId:
                    raise ValueError("The versioned contract requires a sourceRecordId for every reading")
                if category == "cumulative" and reading.periodStart > reading.periodEnd:
                    raise ValueError("Measurement interval is reversed")
                if category == "duration" and reading.startTime > reading.endTime:
                    raise ValueError("Measurement interval is reversed")
        except TypeError as exc:
            raise ValueError("Mixed aware and naive timestamps are not supported") from exc
        return self
