import pytest
from app.providers.google_health import GoogleHealthProvider


@pytest.mark.asyncio
async def test_google_health_provider_validate_credentials():
    provider = GoogleHealthProvider()
    assert await provider.validate_credentials({"access_token": "ya29.a0AfH6SMD_real_oauth_token_1849"}) is True
    assert await provider.validate_credentials({"token": "ya29.bearer_live_token"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


def test_google_health_authorization_url_generation(monkeypatch):
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_ID", "4820194820-apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRET", "GOCSPX-real_secret_key_8492")

    provider = GoogleHealthProvider()
    url = provider.build_authorization_url(
        state="st_google_7491",
        code_challenge="pkce_code_challenge_xyz",
        redirect_uri="https://wearables.charite.de/cloud/callback",
    )

    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=4820194820-apps.googleusercontent.com" in url
    assert "scope=" in url
    assert "fitness.heart_rate.read" in url
    assert "fitness.sleep.read" in url
    assert "state=st_google_7491" in url
    assert "code_challenge=pkce_code_challenge_xyz" in url
    assert "code_challenge_method=S256" in url


@pytest.mark.asyncio
async def test_google_health_provider_parses_sleep_and_stages():
    provider = GoogleHealthProvider()


    # Sleep test: 4: Light (13860s), 5: Deep (4920s), 6: REM (6840s), 1: Awake (2663s)
    mock_bundle = {
        "sleep": {
            "session": [
                {
                    "id": "sleep_session_748291",
                    "startTimeMillis": 1730843239000,  # 2024-11-05 21:47:19 
                    "endTimeMillis": 1730871522000,    # 2024-11-06 05:38:42  (duration 28283s)
                    "sleepScore": 84.0,
                    "stages": [
                        {"stage": 4, "durationSeconds": 13860.0},
                        {"stage": 5, "durationSeconds": 4920.0},
                        {"stage": 6, "durationSeconds": 6840.0},
                        {"stage": 1, "durationSeconds": 2663.0},
                    ],
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="pat-gh-charite-831",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "pat-gh-charite-831"
    assert payload.deviceInfo.platform == "Fitbit"
    assert payload.sourcePlatform == "google-health"

    # Sleep total duration
    sleep_durations = [m for m in payload.measurements.duration if m.type == "SLEEP"]
    assert len(sleep_durations) == 1
    assert sleep_durations[0].duration == 28283.0

    # Sleep score
    sleep_scores = [m for m in payload.measurements.instantaneous if m.type == "SLEEP_SCORE"]
    assert len(sleep_scores) == 1
    assert sleep_scores[0].value == 84.0
    assert sleep_scores[0].unit == "SCORE"

    # Sleep stages
    light = [m for m in payload.measurements.duration if m.type == "SLEEP_LIGHT"]
    assert len(light) == 1
    assert light[0].duration == 13860.0

    deep = [m for m in payload.measurements.duration if m.type == "SLEEP_DEEP"]
    assert len(deep) == 1
    assert deep[0].duration == 4920.0

    rem = [m for m in payload.measurements.duration if m.type == "SLEEP_REM"]
    assert len(rem) == 1
    assert rem[0].duration == 6840.0

    awake = [m for m in payload.measurements.duration if m.type == "SLEEP_AWAKE"]
    assert len(awake) == 1
    assert awake[0].duration == 2663.0


@pytest.mark.asyncio
async def test_google_health_provider_parses_heart_rate_and_workouts():
    provider = GoogleHealthProvider()

    mock_bundle = {
        "heart_rate": {
            "point": [
                {"endTimeNanos": 1730880855000000000, "value": [{"fpVal": 63.4}]},
                {"endTimeNanos": 1730881155000000000, "value": [{"fpVal": 68.1}]},
                {"endTimeNanos": 1730881455000000000, "value": [{"fpVal": 72.8}]},
            ]
        },
        "activities": [
            {
                "id": "act_fitbit_charge6_bike_891",
                "name": "Outdoor Cycling",
                "startTimeMillis": 1730913164000,
                "endTimeMillis": 1730915762000,  # 2598s
                "calories": 387.0,
                "distanceMeters": 5420.8,
                "averageHeartRate": 151.0,
            }
        ],
    }

    payload = await provider.fetch_telemetry(
        patient_id="pat-gh-charite-832",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "pat-gh-charite-832"

    # HR points
    hrs = [m for m in payload.measurements.instantaneous if m.type == "HEART_RATE"]
    assert len(hrs) == 4  # 3 continuous + 1 workout avg
    continuous_hrs = [m for m in hrs if m.metadata.get("source") == "fitbit-pixelwatch"]
    assert len(continuous_hrs) == 3
    assert [m.value for m in continuous_hrs] == [63.4, 68.1, 72.8]

    # Workout duration
    work_dur = [m for m in payload.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(work_dur) == 1
    assert work_dur[0].duration == 2598.0
    assert work_dur[0].metadata.get("sport") == "OUTDOOR CYCLING"

    # Workout distance & calories
    dist = [m for m in payload.measurements.cumulative if m.type == "DISTANCE_WALKING_RUNNING"]
    assert len(dist) == 1
    assert dist[0].value == 5420.8
    assert dist[0].unit == "m"

    cal = [m for m in payload.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(cal) == 1
    assert cal[0].value == 387.0
    assert cal[0].unit == "kcal"
