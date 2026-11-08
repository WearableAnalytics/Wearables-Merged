import pytest
from app.providers.garmin import GarminProvider


@pytest.mark.asyncio
async def test_garmin_provider_validate_credentials():
    provider = GarminProvider()
    assert await provider.validate_credentials({"personal_token": "valid_token_123"}) is True
    assert await provider.validate_credentials({"token": "oauth_token_xyz"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


@pytest.mark.asyncio
async def test_garmin_provider_parses_full_health_bundle_and_ecg():
    provider = GarminProvider()

    mock_bundle = {
        "pulseOx": [
            {
                "startTimeInSeconds": 1730203417,
                "timeOffsetSpo2Values": {
                    "0": 96.0,
                    "57": 98.0,
                    "118": 97.0,
                },
            }
        ],
        "respiration": [
            {
                "startTimeInSeconds": 1730203417,
                "timeOffsetEpochToBreaths": {
                    "0": 14.8,
                    "60": 15.2,
                },
            }
        ],
        "hrv": [
            {
                "startTimeInSeconds": 1730203417,
                "lastNightAvg": 57.4,
                "hrvValues": {
                    "0": 53.0,
                    "180": 61.0,
                },
            }
        ],
        "dailies": [
            {
                "startTimeInSeconds": 1730203417,
                "durationInSeconds": 86400,
                "restingHeartRateInBeatsPerMinute": 58,
                "steps": 7842,
                "floorsClimbed": 9,
                "activeKilocalories": 487,
                "bmrKilocalories": 1682,
                "distanceInMeters": 5894.3,
                "moderateIntensityDurationInSeconds": 1620,
                "vigorousIntensityDurationInSeconds": 780,
                "timeOffsetHeartRateSamples": {"15": 63, "32": 69, "48": 74},
            }
        ],
        "sleeps": [
            {
                "startTimeInSeconds": 1730203417,
                "durationInSeconds": 27420,
                "deepSleepDurationInSeconds": 4980,
                "lightSleepDurationInSeconds": 15720,
                "remSleepInSeconds": 5580,
                "awakeDurationInSeconds": 1140,
            }
        ],
        "stressDetails": [
            {
                "startTimeInSeconds": 1730203417,
                "timeOffsetStressLevelValues": {"0": 33, "180": 42},
                "timeOffsetBodyBatteryValues": {"0": 76, "180": 71},
            }
        ],
        "bodyComps": [
            {
                "measurementTimeInSeconds": 1730203417,
                "weightInGrams": 76850,
                "bodyMassIndex": 23.4,
                "bodyFatInPercent": 16.1,
            }
        ],
        "bloodPressures": [
            {
                "measurementTimeInSeconds": 1730203417,
                "systolic": 122,
                "diastolic": 79,
                "pulse": 67,
            }
        ],
        "skinTemp": [
            {
                "startTimeInSeconds": 1730203417,
                "avgDeviationCelsius": -0.35,
            }
        ],
        "userMetrics": [
            {
                "startTimeInSeconds": 1730203417,
                "vo2Max": 48.5,
            }
        ],
        "ecg": [
            {
                "startTimeInSeconds": 1730203417,
                "durationInSeconds": 30.0,
                "samplingFrequencyHz": 250.0,
                "rhythmClassification": "SINUS_RHYTHM",
                "meanHeartRate": 68.5,
                "leadName": "LEAD_I",
                "samples": [-18.2, -14.5, -4.1, 88.6, 612.4, -142.0, -28.7, 12.3, 45.1, 18.0],
            },
            {
                "startTimeInSeconds": 1730203537,
                "durationInSeconds": 60.0,
                "samplingFrequencyHz": 500.0,
                "rhythmClassification": "SINUS_RHYTHM",
                "meanHeartRate": 63.2,
                "leadName": "LEAD_I",
                "samples": [-11.3, -5.2, 54.7, 580.1, -118.5, 32.4],
            },
        ],
    }

    patient_id = "01a17e07-a10d-7a7c-aa23-2a0da2297b39"
    payload = await provider.fetch_telemetry(
        patient_id=patient_id,
        credentials={"mock_data": mock_bundle, "token": "dummy"},
    )

    assert payload.deviceInfo.platform == "Garmin"
    assert payload.deviceInfo.deviceId == patient_id
    assert payload.totalStepsToday == 7842

    inst = payload.measurements.instantaneous
    cum = payload.measurements.cumulative
    dur = payload.measurements.duration
    wav = payload.measurements.waveforms

    inst_types = {m.type for m in inst}
    assert {
        "BLOOD_OXYGEN",
        "RESPIRATORY_RATE",
        "HEART_RATE_VARIABILITY_RMSSD",
        "HEART_RATE",
        "RESTING_HEART_RATE",
        "STRESS_LEVEL",
        "BODY_BATTERY",
        "WEIGHT",
        "BODY_MASS_INDEX",
        "BODY_FAT_PERCENTAGE",
        "BLOOD_PRESSURE_SYSTOLIC",
        "BLOOD_PRESSURE_DIASTOLIC",
        "BODY_TEMPERATURE",
        "VO2_MAX",
        "ELECTROCARDIOGRAM",
    }.issubset(inst_types)

    cum_types = {m.type for m in cum}
    assert {
        "STEPS",
        "FLIGHTS_CLIMBED",
        "ACTIVE_ENERGY_BURNED",
        "BASAL_ENERGY_BURNED",
        "DISTANCE_WALKING_RUNNING",
    } == cum_types

    dur_types = {m.type for m in dur}
    assert {
        "EXERCISE_TIME",
        "SLEEP_ASLEEP",
        "SLEEP_DEEP",
        "SLEEP_LIGHT",
        "SLEEP_REM",
        "SLEEP_AWAKE",
    } == dur_types

    # Check ECG waveforms
    assert len(wav) == 2
    ecg_30 = wav[0]
    assert ecg_30.type == "ELECTROCARDIOGRAM"
    assert ecg_30.durationSeconds == 30.0
    assert ecg_30.samplingFrequencyHz == 250.0
    assert ecg_30.classification == "SINUS_RHYTHM"
    assert ecg_30.meanHeartRate == 68.5
    assert len(ecg_30.samples) == 10

    ecg_60 = wav[1]
    assert ecg_60.durationSeconds == 60.0
    assert ecg_60.samplingFrequencyHz == 500.0
    assert ecg_60.meanHeartRate == 63.2


def test_garmin_pkce_and_webhook_user_linking(monkeypatch, tmp_path):
    from app.config import get_settings
    from app.storage import ConnectionStore

    get_settings.cache_clear()
    monkeypatch.setenv("GARMIN_CLIENT_ID", "test-client-id-1234")
    monkeypatch.setenv("GARMIN_CLIENT_SECRET", "test-client-secret-5678")
    get_settings.cache_clear()

    provider = GarminProvider()
    verifier, challenge = provider.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert "=" not in challenge

    auth_url = provider.build_authorization_url(
        state="state-xyz",
        code_challenge=challenge,
        redirect_uri="http://localhost/cloud/callback",
    )
    assert auth_url.startswith("https://connect.garmin.com/oauth2Confirm?")
    assert "client_id=test-client-id-1234" in auth_url
    assert "code_challenge_method=S256" in auth_url

    store = ConnectionStore(storage_path=str(tmp_path / "connections.json"))
    patient_id = "01a17e07-a10d-7a7c-aa23-2a0da2297b39"
    garmin_uid = "d3315b1072421d0dd7c8f6b8e1de4df8"

    store.save_connection(
        provider="garmin",
        patient_id=patient_id,
        provider_user_id=garmin_uid,
        access_token="access-token-abc",
        refresh_token="refresh-token-def",
        expires_in=86400,
        permissions=["HEALTH_EXPORT", "ACTIVITY_EXPORT"],
    )

    assert store.resolve_patient_id("garmin", garmin_uid) == patient_id

    webhook_push = {
        "dailies": [
            {
                "userId": garmin_uid,
                "startTimeInSeconds": 1730203417,
                "durationInSeconds": 86400,
                "steps": 6419,
                "restingHeartRateInBeatsPerMinute": 56,
            }
        ],
        "pulseOx": [
            {
                "userId": garmin_uid,
                "startTimeInSeconds": 1730203417,
                "timeOffsetSpo2Values": {"0": 97.0},
            }
        ],
    }

    payloads = provider.parse_webhook_payload(
        data=webhook_push,
        resolve_patient_id=lambda uid: store.resolve_patient_id("garmin", uid),
    )
    assert len(payloads) == 1
    assert payloads[0].deviceInfo.deviceId == patient_id
    assert payloads[0].totalStepsToday == 6419
    assert len(payloads[0].measurements.instantaneous) == 2
    assert len(payloads[0].measurements.cumulative) == 1
    get_settings.cache_clear()
