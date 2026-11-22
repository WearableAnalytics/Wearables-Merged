import pytest
from app.providers.polar import PolarProvider


@pytest.mark.asyncio
async def test_polar_provider_validate_credentials():
    provider = PolarProvider()
    assert await provider.validate_credentials({"access_token": "pol_acc_4892c9f1a0e84b2c"}) is True
    assert await provider.validate_credentials({"token": "oauth2_bearer_polar_live_token"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


def test_polar_authorization_url_generation(monkeypatch):
    monkeypatch.setenv("POLAR_CLIENT_ID", "pol_client_live_8a7f92b")
    monkeypatch.setenv("POLAR_CLIENT_SECRET", "pol_sec_99182fa34b")

    provider = PolarProvider()
    url = provider.build_authorization_url(
        state="st_738491_dev",
        code_challenge="dummy_challenge",
        redirect_uri="https://wearables.charite.de/cloud/callback",
    )

    assert "flow.polar.com/oauth2/authorization" in url
    assert "client_id=pol_client_live_8a7f92b" in url
    assert "scope=accesslink.read_all" in url
    assert "state=st_738491_dev" in url
    assert "response_type=code" in url


@pytest.mark.asyncio
async def test_polar_provider_parses_sleep_and_scores():
    provider = PolarProvider()

    mock_bundle = {
        "sleep": {
            "nights": [
                {
                    "polar_user": "https://www.polaraccesslink.com/v3/users/837261",
                    "date": "2024-11-05",
                    "sleep_start_time": "2024-11-04T22:47:19+01:00",
                    "sleep_end_time": "2024-11-05T06:38:42+01:00",
                    "device_id": "Polar Vantage V2",
                    "continuity": 3.8,
                    "continuity_class": 3,
                    "light_sleep": 13860,
                    "deep_sleep": 4920,
                    "rem_sleep": 6840,
                    "total_interruption_duration": 2663,
                    "sleep_score": 79,
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="pat-9182-berlin",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "pat-9182-berlin"
    assert payload.deviceInfo.platform == "Polar"
    assert payload.sourcePlatform == "polar-flow"

    # Verify sleep duration (7h 51m 23s = 28283.0 seconds)
    sleep_durations = [m for m in payload.measurements.duration if m.type == "SLEEP"]
    assert len(sleep_durations) == 1
    assert sleep_durations[0].duration == 28283.0
    assert sleep_durations[0].metadata.get("device_id") == "Polar Vantage V2"

    # Verify sleep stages
    light_durations = [m for m in payload.measurements.duration if m.type == "SLEEP_LIGHT"]
    assert len(light_durations) == 1
    assert light_durations[0].duration == 13860.0

    deep_durations = [m for m in payload.measurements.duration if m.type == "SLEEP_DEEP"]
    assert len(deep_durations) == 1
    assert deep_durations[0].duration == 4920.0

    rem_durations = [m for m in payload.measurements.duration if m.type == "SLEEP_REM"]
    assert len(rem_durations) == 1
    assert rem_durations[0].duration == 6840.0

    awake_durations = [m for m in payload.measurements.duration if m.type == "SLEEP_AWAKE"]
    assert len(awake_durations) == 1
    assert awake_durations[0].duration == 2663.0

    # Verify sleep score
    sleep_scores = [m for m in payload.measurements.instantaneous if m.type == "SLEEP_SCORE"]
    assert len(sleep_scores) == 1
    assert sleep_scores[0].value == 79.0
    assert sleep_scores[0].unit == "SCORE"
    assert sleep_scores[0].metadata.get("continuity") == "3.8"
    assert sleep_scores[0].metadata.get("continuity_class") == "3"


@pytest.mark.asyncio
async def test_polar_provider_parses_continuous_hr_and_exercises():
    provider = PolarProvider()

    mock_bundle = {
        "continuous_heart_rate": {
            "polar_user": 837261,
            "date": "2024-11-05",
            "heart_rate_samples": [
                {"heart_rate": 61, "sample_time": "2024-11-05T08:14:15Z"},
                {"heart_rate": 67, "sample_time": "2024-11-05T08:19:15Z"},
                {"heart_rate": 72, "sample_time": "2024-11-05T08:24:15Z"},
                {"heart_rate": 65, "sample_time": "2024-11-05T08:29:15Z"},
            ],
        },
        "exercises": [
            {
                "id": 749102831,
                "start_time": "2024-11-05T17:12:44Z",
                "duration": "PT43M18S",
                "calories": 387,
                "distance": 5420.8,
                "heart_rate": {
                    "average": 151,
                    "maximum": 178,
                },
                "sport": "RUNNING",
                "device": "Polar Pacer Pro",
            }
        ],
    }

    payload = await provider.fetch_telemetry(
        patient_id="pat-9182-berlin",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "pat-9182-berlin"

    # Continuous HR checks
    continuous_hrs = [
        m for m in payload.measurements.instantaneous
        if m.type == "HEART_RATE" and m.metadata.get("source") == "continuous_heart_rate"
    ]
    assert len(continuous_hrs) == 4
    assert [m.value for m in continuous_hrs] == [61.0, 67.0, 72.0, 65.0]

    # Exercise duration (43 min 18 sec)
    exercise_durations = [m for m in payload.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(exercise_durations) == 1
    assert exercise_durations[0].duration == 2598.0
    assert exercise_durations[0].metadata.get("sport") == "RUNNING"
    assert exercise_durations[0].metadata.get("exercise_id") == "749102831"
    assert exercise_durations[0].metadata.get("device") == "Polar Pacer Pro"

    # Exercise distance
    distances = [m for m in payload.measurements.cumulative if m.type == "DISTANCE_WALKING_RUNNING"]
    assert len(distances) == 1
    assert distances[0].value == 5420.8
    assert distances[0].unit == "m"

    # Exercise calories
    calories = [m for m in payload.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(calories) == 1
    assert calories[0].value == 387.0
    assert calories[0].unit == "kcal"

    # Exercise average & max HR
    avg_hrs = [
        m for m in payload.measurements.instantaneous
        if m.type == "HEART_RATE" and m.metadata.get("metric") == "average_heart_rate"
    ]
    assert len(avg_hrs) == 1
    assert avg_hrs[0].value == 151.0

    max_hrs = [
        m for m in payload.measurements.instantaneous
        if m.type == "HEART_RATE" and m.metadata.get("metric") == "max_heart_rate"
    ]
    assert len(max_hrs) == 1
    assert max_hrs[0].value == 178.0
