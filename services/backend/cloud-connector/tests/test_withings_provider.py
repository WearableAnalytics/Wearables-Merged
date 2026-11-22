from app.config import get_settings
import pytest
from datetime import datetime, timezone
from app.providers.withings import WithingsProvider


@pytest.mark.asyncio
async def test_withings_provider_validate_credentials():
    provider = WithingsProvider()
    assert await provider.validate_credentials({"access_token": "withings_tok_849201"}) is True
    assert await provider.validate_credentials({"token": "withings_tok_391029"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


def test_withings_authorization_url_generation(monkeypatch):
    monkeypatch.setenv("WITHINGS_CLIENT_ID", "withings_client_live_7718")
    monkeypatch.setenv("WITHINGS_CLIENT_SECRET", "withings_sec_49102")
    get_settings.cache_clear()

    provider = WithingsProvider()
    url = provider.build_authorization_url(
        state="st_withings_session_102",
        code_challenge="pkce_code_challenge_s256_hash",
        redirect_uri="https://wearables.charite.de/cloud/callback",
    )

    assert "account.withings.com/oauth2_user/authorize2" in url
    assert "client_id=withings_client_live_7718" in url
    assert "response_type=code" in url
    assert "scope=" in url
    assert "user.metrics" in url
    assert "user.activity" in url
    assert "user.sleepevents" in url
    assert "state=st_withings_session_102" in url
    assert "code_challenge=pkce_code_challenge_s256_hash" in url
    assert "code_challenge_method=S256" in url


@pytest.mark.asyncio
async def test_withings_provider_parses_body_measurements():
    provider = WithingsProvider()

    # Withings /measure?action=getmeas response bundle
    # Values with 10^unit exponent scaling, e.g.: 75400 * 10^-3 = 75.40 kg
    mock_bundle = {
        "measure": {
            "measuregrps": [
                {
                    "grpid": 8920194,
                    "date": 1731405600, 
                    "category": 1,
                    "measures": [
                        {"value": 75400, "type": 1, "unit": -3},
                        {"value": 182, "type": 6, "unit": -1},
                        {"value": 122, "type": 10, "unit": 0},
                        {"value": 81, "type": 9, "unit": 0},
                        {"value": 62, "type": 11, "unit": 0},
                        {"value": 985, "type": 54, "unit": -1},
                    ],
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-withings-patient-001",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "p-withings-patient-001"
    assert payload.deviceInfo.platform == "Withings"
    assert payload.sourcePlatform == "withings"

    # Weight
    weight = [m for m in payload.measurements.instantaneous if m.type == "BODY_MASS"]
    assert len(weight) == 1
    assert weight[0].value == 75.4
    assert weight[0].unit == "kg"

    # Body fat %
    fat = [m for m in payload.measurements.instantaneous if m.type == "BODY_FAT_PERCENTAGE"]
    assert len(fat) == 1
    assert fat[0].value == 18.2
    assert fat[0].unit == "%"

    # Blood pressure systolic & diastolic
    sys = [m for m in payload.measurements.instantaneous if m.type == "BLOOD_PRESSURE_SYSTOLIC"]
    assert len(sys) == 1
    assert sys[0].value == 122.0
    assert sys[0].unit == "mmHg"

    dia = [m for m in payload.measurements.instantaneous if m.type == "BLOOD_PRESSURE_DIASTOLIC"]
    assert len(dia) == 1
    assert dia[0].value == 81.0
    assert dia[0].unit == "mmHg"

    # Resting heart rate
    rhr = [m for m in payload.measurements.instantaneous if m.type == "RESTING_HEART_RATE"]
    assert len(rhr) == 1
    assert rhr[0].value == 62.0
    assert rhr[0].unit == "count/min"

    # SpO2
    spo2 = [m for m in payload.measurements.instantaneous if m.type == "OXYGEN_SATURATION"]
    assert len(spo2) == 1
    assert spo2[0].value == 98.5
    assert spo2[0].unit == "%"


@pytest.mark.asyncio
async def test_withings_provider_parses_sleep_and_activity():
    provider = WithingsProvider()

    # Withings /v2/sleep and /v2/measure bundles
    mock_bundle = {
        "sleep": {
            "series": [
                {
                    "id": 99281,
                    "model": "Sleep Analyzer",
                    "startdate": 1731366000,
                    "enddate": 1731394800,  # 8 hours
                    "data": {
                        "total_sleep_time": 25200,   # 7h
                        "deepsleepduration": 5400,   # 1.5h
                        "lightsleepduration": 13800, # 3h 50m
                        "remsleepduration": 6000,    # 1h 40m
                        "wakeupduration": 3600,      # 1h
                        "sleep_score": 85,
                        "hr_average": 56,
                    },
                }
            ]
        },
        "activity": {
            "activities": [
                {
                    "date": "2024-11-12",
                    "steps": 9482,
                    "distance": 7120.5,
                    "calories": 420.0,
                    "active": 3120,  # 52 min
                    "hr_average": 72,
                }
            ]
        },
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-withings-patient-002",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    # Total sleep
    sleep = [m for m in payload.measurements.duration if m.type == "SLEEP"]
    assert len(sleep) == 1
    assert sleep[0].durationMinutes == pytest.approx(420.0, abs=0.01)

    # Sleep stages
    deep = [m for m in payload.measurements.duration if m.type == "SLEEP_DEEP"]
    assert len(deep) == 1
    assert deep[0].durationMinutes == pytest.approx(90.0, abs=0.01)

    light = [m for m in payload.measurements.duration if m.type == "SLEEP_LIGHT"]
    assert len(light) == 1
    assert light[0].durationMinutes == pytest.approx(230.0, abs=0.01)

    rem = [m for m in payload.measurements.duration if m.type == "SLEEP_REM"]
    assert len(rem) == 1
    assert rem[0].durationMinutes == pytest.approx(100.0, abs=0.01)

    awake = [m for m in payload.measurements.duration if m.type == "SLEEP_AWAKE"]
    assert len(awake) == 1
    assert awake[0].durationMinutes == pytest.approx(60.0, abs=0.01)

    # Sleep score
    score = [m for m in payload.measurements.instantaneous if m.type == "SLEEP_SCORE"]
    assert len(score) == 1
    assert score[0].value == 85.0

    # Steps & distance
    steps = [m for m in payload.measurements.cumulative if m.type == "STEP_COUNT"]
    assert len(steps) == 1
    assert steps[0].value == 9482.0

    dist = [m for m in payload.measurements.cumulative if m.type == "DISTANCE_WALKING_RUNNING"]
    assert len(dist) == 1
    assert dist[0].value == 7120.5

    # Calories & exercise time
    cals = [m for m in payload.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(cals) == 1
    assert cals[0].value == 420.0

    ex_time = [m for m in payload.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(ex_time) == 1
    assert ex_time[0].durationMinutes == pytest.approx(52.0, abs=0.01)
