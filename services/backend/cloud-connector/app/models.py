from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    platform: str
    deviceId: str
    authorizationToken: Optional[str] = ""


class BatchInfo(BaseModel):
    collectionStart: datetime
    collectionEnd: datetime
    lastSendTime: Optional[datetime] = None


class InstantaneousMeasurement(BaseModel):
    type: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


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


class WaveformMeasurement(BaseModel):
    """Represents a high-frequency sensor recording of arbitrary duration"""
    type: str = "ELECTROCARDIOGRAM"
    unit: str = "MICROVOLTS"
    startTime: datetime
    endTime: datetime
    durationSeconds: float
    samplingFrequencyHz: float
    classification: Optional[str] = None
    meanHeartRate: Optional[float] = None
    leadName: Optional[str] = "LEAD_I"
    samples: List[float] = Field(default_factory=list)


class Measurements(BaseModel):
    instantaneous: List[InstantaneousMeasurement] = Field(default_factory=list)
    cumulative: List[CumulativeMeasurement] = Field(default_factory=list)
    duration: List[DurationMeasurement] = Field(default_factory=list)
    waveforms: List[WaveformMeasurement] = Field(default_factory=list)


class IngestPayload(BaseModel):
    deviceInfo: DeviceInfo
    batchInfo: BatchInfo
    measurements: Measurements
    sourceName: str
    sourcePlatform: Optional[str] = None
    totalStepsToday: Optional[int] = None
    timestamp: datetime


class SyncRequest(BaseModel):
    patient_id: str
    credentials: Dict[str, Any]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class SyncResponse(BaseModel):
    provider: str
    patient_id: str
    status: str
    instantaneous_count: int
    cumulative_count: int
    duration_count: int
    waveform_count: int = 0
    published_to_kafka: bool
    timestamp: datetime
