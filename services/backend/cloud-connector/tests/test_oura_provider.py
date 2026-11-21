import pytest
from app.providers.oura import OuraProvider


@pytest.mark.asyncio
async def test_oura_provider_validate_credentials():
    provider = OuraProvider()
    assert await provider.validate_credentials({"access_token": "oura_personal_live_token_839210"}) is True
    assert await provider.validate_credentials({"personal_token": "oura_pat_482910"}) is True
    assert await provider.validate_credentials({"token": "bearer_oauth_oura"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


def test_oura_authorization_url_generation(monkeypatch):
    monkeypatch.setenv("OURA_CLIENT_ID", "oura_client_live_7391")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "oura_sec_8392019a")

    provider = OuraProvider()
    url = provider.build_authorization_url(
        state="st_oura_4819",
        code_challenge="pkce_challenge_oura_991",
        redirect_uri="https://wearables.charite.de/cloud/callback",
    )

    assert "cloud.ouraring.com/oauth/authorize" in url
    assert "client_id=oura_client_live_7391" in url
    assert "scope=" in url
    assert "sleep" in url
    assert "heartrate" in url
    assert "daily" in url
    assert "state=st_oura_4819" in url
    assert "code_challenge=pkce_challenge_oura_991" in url
    assert "code_challenge_method=S256" in url


@pytest.mark.asyncio
async def test_oura_provider_parses_sleep_and_readiness():
    provider = OuraProvider()

    mock_bundle = {
        "sleep": {
            "data": [
                {
                    "id": "sleep_doc_839102",
                    "bedtime_start": "2024-11-08T22:42:15+01:00",
                    "bedtime_end": "2024-11-09T06:33:38+01:00",
                    "total_sleep_duration": 25740,  # 7h 9m
                    "deep_sleep_duration": 4860,    # 1h 21m
                    "light_sleep_duration": 14220,  # 3h 57m
                    "rem_sleep_duration": 6660,     # 1h 51m
                    "awake_time": 2543,
                    "score": 83,
                    "efficiency": 91,
                    "lowest_heart_rate": 52,
                    "average_hrv": 46,
                }
            ]
        },
        "daily_readiness": {
            "data": [
                {
                    "day": "2024-11-09",
                    "score": 86,
                    "temperature_deviation": -0.15,
                    "resting_heart_rate": 54,
                }
            ]
        },
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-oura-ring-019",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "p-oura-ring-019"
    assert payload.deviceInfo.platform == "Oura"
    assert payload.sourcePlatform == "oura"

    # Total sleep duration
    sleeps = [m for m in payload.measurements.duration if m.type == "SLEEP"]
    assert len(sleeps) == 1
    assert sleeps[0].duration == 25740.0
    assert sleeps[0].metadata.get("documentId") == "sleep_doc_839102"

    # Sleep stages
    deep = [m for m in payload.measurements.duration if m.type == "SLEEP_DEEP"]
    assert len(deep) == 1
    assert deep[0].duration == 4860.0

    light = [m for m in payload.measurements.duration if m.type == "SLEEP_LIGHT"]
    assert len(light) == 1
    assert light[0].duration == 14220.0

    rem = [m for m in payload.measurements.duration if m.type == "SLEEP_REM"]
    assert len(rem) == 1
    assert rem[0].duration == 6660.0

    awake = [m for m in payload.measurements.duration if m.type == "SLEEP_AWAKE"]
    assert len(awake) == 1
    assert awake[0].duration == 2543.0

    # Sleep Score & Readiness Score
    sleep_score = [m for m in payload.measurements.instantaneous if m.type == "SLEEP_SCORE"]
    assert len(sleep_score) == 1
    assert sleep_score[0].value == 83.0

    recovery = [m for m in payload.measurements.instantaneous if m.type == "RECOVERY_SCORE"]
    assert len(recovery) == 1
    assert recovery[0].value == 86.0
    assert recovery[0].metadata.get("temperature_deviation") == -0.15

    # Lowest sleep heart rate & HRV
    lowest_hr = [
        m for m in payload.measurements.instantaneous
        if m.type == "RESTING_HEART_RATE" and m.metadata.get("metric") == "lowest_sleep_heart_rate"
    ]
    assert len(lowest_hr) == 1
    assert lowest_hr[0].value == 52.0

    hrv = [m for m in payload.measurements.instantaneous if m.type == "HEART_RATE_VARIABILITY"]
    assert len(hrv) == 1
    assert hrv[0].value == 46.0
    assert hrv[0].unit == "ms"


@pytest.mark.asyncio
async def test_oura_provider_parses_heart_rate_workouts_and_spo2():
    provider = OuraProvider()

    mock_bundle = {
        "heartrate": {
            "data": [
                {"bpm": 58, "source": "rest", "timestamp": "2024-11-09T08:15:00+00:00"},
                {"bpm": 64, "source": "awake", "timestamp": "2024-11-09T08:20:00+00:00"},
                {"bpm": 71, "source": "awake", "timestamp": "2024-11-09T08:25:00+00:00"},
            ]
        },
        "workout": {
            "data": [
                {
                    "activity": "walking",
                    "calories": 142.5,
                    "distance": 2350.0,
                    "start_datetime": "2024-11-09T10:15:00+01:00",
                    "end_datetime": "2024-11-09T10:47:30+01:00",  # 32m 30s
                    "intensity": "easy",
                }
            ]
        },
        "daily_spo2": {
            "data": [
                {
                    "day": "2024-11-09",
                    "spo2_percentage": {"average": 98.3},
                }
            ]
        },
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-oura-ring-020",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "p-oura-ring-020"

    # Continuous HR
    hrs = [m for m in payload.measurements.instantaneous if m.type == "HEART_RATE"]
    assert len(hrs) == 3
    assert [m.value for m in hrs] == [58.0, 64.0, 71.0]

    # Workout duration
    work_dur = [m for m in payload.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(work_dur) == 1
    assert work_dur[0].duration == 1950.0
    assert work_dur[0].metadata.get("sport") == "WALKING"

    # Workout calories & distance
    cals = [m for m in payload.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(cals) == 1
    assert cals[0].value == 142.5
    assert cals[0].unit == "kcal"

    dists = [m for m in payload.measurements.cumulative if m.type == "DISTANCE_WALKING_RUNNING"]
    assert len(dists) == 1
    assert dists[0].value == 2350.0
    assert dists[0].unit == "m"

    # SpO2
    spo2 = [m for m in payload.measurements.instantaneous if m.type == "OXYGEN_SATURATION"]
    assert len(spo2) == 1
    assert spo2[0].value == 98.3
    assert spo2[0].unit == "%"
