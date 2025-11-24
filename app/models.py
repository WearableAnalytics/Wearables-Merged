from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class DeviceInfo(BaseModel):
    platform: str
    deviceId: str

class BatchInfo(BaseModel):
    collectionStart: datetime
    collectionEnd: datetime

class InstantaneousMeasurement(BaseModel):
    type: str
    value: float
    unit: str
    timestamp: datetime

class CumulativeMeasurement(BaseModel):
    type: str
    value: float
    unit: str
    periodStart: datetime
    periodEnd: datetime
    duration: int

class DurationMeasurement(BaseModel):
    type: str
    value: float
    unit: str
    startTime: datetime
    endTime: datetime
    durationMinutes: int

class Measurements(BaseModel):
    instantaneous: List[InstantaneousMeasurement] = Field(default_factory=list)
    cumulative: List[CumulativeMeasurement] = Field(default_factory=list)
    duration: List[DurationMeasurement] = Field(default_factory=list)

class IngestPayload(BaseModel):
    deviceInfo: DeviceInfo
    batchInfo: BatchInfo
    measurements: Measurements
    sourceName: str
    totalStepsToday: Optional[int] = None
    timestamp: datetime

class IngestResponse(BaseModel):
    total_messages_produced: int
    instantaneous_count: int
    cumulative_count: int
    duration_count: int
