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


class SourceRecord(BaseModel):
    sourceRecordId: Optional[str] = Field(default=None, min_length=1, max_length=512)
    sourceDeviceId: Optional[str] = Field(default=None, min_length=1, max_length=512)


class InstantaneousMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class CumulativeMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    periodStart: datetime
    periodEnd: datetime
    duration: int
    metadata: Optional[Dict[str, Any]] = None


class DurationMeasurement(SourceRecord):
    type: str
    value: float
    unit: str
    startTime: datetime
    endTime: datetime
    durationMinutes: float
    metadata: Optional[Dict[str, Any]] = None


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
    sourceId: Optional[str] = None
    participantId: Optional[str] = None
    totalStepsToday: Optional[int] = None
    timestamp: datetime


class SyncRequest(BaseModel):
    patient_id: str
    credentials: Dict[str, Any] = Field(default_factory=dict)
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


class HistoryBackfillRequest(BaseModel):
    patient_id: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    days: int = Field(default=30, ge=1, le=365)
    data_types: Optional[List[str]] = None
    allow_pre_auth: bool = False


class HistoryBackfillResponse(BaseModel):
    provider: str
    patient_id: str
    status: str
    start_time: datetime
    end_time: datetime
    pre_auth_applied: bool
    triggered: List[str] = Field(default_factory=list)
    already_requested: List[str] = Field(default_factory=list)
    skipped: Dict[str, str] = Field(default_factory=dict)
    failed: Dict[str, str] = Field(default_factory=dict)


class PreAuthConsentRequest(BaseModel):
    allow_pre_auth_history: bool
