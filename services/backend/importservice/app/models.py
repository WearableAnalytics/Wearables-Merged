from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class DeviceInfo(BaseModel):
    platform: str
    deviceId: str
    authorizationToken: Optional[str] = ""

class BatchInfo(BaseModel):
    collectionStart: datetime
    collectionEnd: datetime
    lastSendTime: Optional[datetime] = None

class SourceRecord(BaseModel):
    sourceRecordId: Optional[str] = Field(default=None, min_length=1, max_length=512)
    sourceDeviceId: Optional[str] = Field(default=None, min_length=1, max_length=512)

class InstantaneousMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    timestamp: datetime

class CumulativeMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    periodStart: datetime
    periodEnd: datetime
    duration: int

class DurationMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    startTime: datetime
    endTime: datetime
    durationMinutes: float

class Measurements(BaseModel):
    instantaneous: List[InstantaneousMeasurement] = Field(default_factory=list)
    cumulative: List[CumulativeMeasurement] = Field(default_factory=list)
    duration: List[DurationMeasurement] = Field(default_factory=list)

class IngestPayload(BaseModel):
    contractVersion: Optional[Literal["wearables-numeric/1"]] = None
    deviceInfo: DeviceInfo
    batchInfo: BatchInfo
    measurements: Measurements
    sourceName: str
    sourcePlatform: Optional[str] = None
    sourceId: Optional[str] = Field(default=None, min_length=1, max_length=256)
    totalStepsToday: Optional[int] = None
    timestamp: datetime

class IngestResponse(BaseModel):
    total_messages_produced: int
    instantaneous_count: int
    cumulative_count: int
    duration_count: int
