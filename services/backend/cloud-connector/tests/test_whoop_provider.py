from app.config import get_settings
import pytest
from app.providers.whoop import WhoopProvider


@pytest.mark.asyncio
async def test_whoop_provider_validate_credentials():
    provider = WhoopProvider()
    assert await provider.validate_credentials({"access_token": "whoop_oauth_token_94821a"}) is True
    assert await provider.validate_credentials({"token": "whoop_tok_839210"}) is True
    assert await provider.validate_credentials({"token": ""}) is False
    assert await provider.validate_credentials({}) is False


def test_whoop_authorization_url_generation(monkeypatch):
    monkeypatch.setenv("WHOOP_CLIENT_ID", "whoop_client_live_49102")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "whoop_sec_991823ab")
    get_settings.cache_clear()

    provider = WhoopProvider()
    url = provider.build_authorization_url(
        state="st_whoop_session_7718",
        code_challenge="pkce_challenge_whoop_s256_hash",
        redirect_uri="https://wearables.charite.de/cloud/callback",
    )

    assert "api.prod.whoop.com/oauth/oauth2/auth" in url
    assert "client_id=whoop_client_live_49102" in url
    assert "scope=" in url
    assert "read%3Arecovery" in url or "read:recovery" in url
    assert "read%3Asleep" in url or "read:sleep" in url
    assert "read%3Aworkout" in url or "read:workout" in url
    assert "state=st_whoop_session_7718" in url
    assert "code_challenge=pkce_challenge_whoop_s256_hash" in url
    assert "code_challenge_method=S256" in url


@pytest.mark.asyncio
async def test_whoop_provider_parses_recovery():
    provider = WhoopProvider()

    # Whoop API v2 recovery bundle
    mock_bundle = {
        "recovery": {
            "records": [
                {
                    "cycle_id": "771e8400-e29b-41d4-a716-446655440001",
                    "sleep_id": "882e8400-e29b-41d4-a716-446655440002",
                    "user_id": 98412,
                    "created_at": "2024-11-12T07:15:32.418Z",
                    "updated_at": "2024-11-12T07:16:01.102Z",
                    "score_state": "SCORED",
                    "score": {
                        "user_calibrating": False,
                        "recovery_score": 78.0,
                        "resting_heart_rate": 53.0,
                        "hrv_rmssd_milli": 64.8219,
                        "spo2_percentage": 97.4,
                        "skin_temp_celsius": 33.82,
                    },
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-whoop-strap-041",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    assert payload.participantId == "p-whoop-strap-041"
    assert payload.deviceInfo.platform == "Whoop"
    assert payload.sourcePlatform == "whoop"

    # Recovery score
    rec_score = [m for m in payload.measurements.instantaneous if m.type == "RECOVERY_SCORE"]
    assert len(rec_score) == 1
    assert rec_score[0].value == 78.0
    assert rec_score[0].unit == "SCORE"
    assert rec_score[0].metadata.get("cycle_id") == "771e8400-e29b-41d4-a716-446655440001"

    # Resting heart rate
    rhr = [m for m in payload.measurements.instantaneous if m.type == "RESTING_HEART_RATE"]
    assert len(rhr) == 1
    assert rhr[0].value == 53.0
    assert rhr[0].unit == "count/min"

    # HRV
    hrv = [m for m in payload.measurements.instantaneous if m.type == "HEART_RATE_VARIABILITY"]
    assert len(hrv) == 1
    assert hrv[0].value == 64.8219
    assert hrv[0].unit == "ms"

    # SpO2 percentage
    spo2 = [m for m in payload.measurements.instantaneous if m.type == "OXYGEN_SATURATION"]
    assert len(spo2) == 1
    assert spo2[0].value == 97.4
    assert spo2[0].unit == "%"

    # Skin temperature 
    skin_temp = [m for m in payload.measurements.instantaneous if m.type == "SKIN_TEMPERATURE"]
    assert len(skin_temp) == 1
    assert skin_temp[0].value == 33.82
    assert skin_temp[0].unit == "degC"


@pytest.mark.asyncio
async def test_whoop_provider_parses_sleep():
    provider = WhoopProvider()

    # Whoop API v2 sleep bundle
    mock_bundle = {
        "sleep": {
            "records": [
                {
                    "id": "882e8400-e29b-41d4-a716-446655440002",
                    "user_id": 98412,
                    "created_at": "2024-11-12T07:15:00.000Z",
                    "start": "2024-11-11T23:14:10.000Z",
                    "end": "2024-11-12T06:58:35.000Z",
                    "timezone_offset": "+01:00",
                    "nap": False,
                    "score_state": "SCORED",
                    "score": {
                        "stage_summary": {
                            "total_in_bed_time_milli": 27865000,          # 7h 44m 25s
                            "total_awake_time_milli": 2340000,            # 39m
                            "total_light_sleep_time_milli": 13925000,      # 3h 52m 5s
                            "total_slow_wave_sleep_time_milli": 5820000,  # 1h 37m
                            "total_rem_sleep_time_milli": 5780000,        # 1h 36m 20s
                            "sleep_cycle_count": 5,
                            "disturbance_count": 8,
                        },
                        "sleep_needed": {
                            "baseline_milli": 27000000,
                            "need_from_sleep_debt_milli": 1800000,
                            "need_from_recent_strain_milli": 1200000,
                            "need_from_recent_nap_milli": 0,
                        },
                        "respiratory_rate": 15.2,
                        "sleep_performance_percentage": 92.0,
                        "sleep_consistency_percentage": 88.0,
                        "sleep_efficiency_percentage": 91.6,
                    },
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-whoop-strap-042",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    # Total sleep
    sleep = [m for m in payload.measurements.duration if m.type == "SLEEP"]
    assert len(sleep) == 1
    assert sleep[0].durationMinutes == pytest.approx(464.42, abs=0.01)
    assert sleep[0].unit == "MINUTE"
    assert sleep[0].metadata.get("id") == "882e8400-e29b-41d4-a716-446655440002"

    # Sleep stages
    deep = [m for m in payload.measurements.duration if m.type == "SLEEP_DEEP"]
    assert len(deep) == 1
    assert deep[0].durationMinutes == pytest.approx(97.0, abs=0.01)

    light = [m for m in payload.measurements.duration if m.type == "SLEEP_LIGHT"]
    assert len(light) == 1
    assert light[0].durationMinutes == pytest.approx(232.08, abs=0.01)

    rem = [m for m in payload.measurements.duration if m.type == "SLEEP_REM"]
    assert len(rem) == 1
    assert rem[0].durationMinutes == pytest.approx(96.33, abs=0.01)

    awake = [m for m in payload.measurements.duration if m.type == "SLEEP_AWAKE"]
    assert len(awake) == 1
    assert awake[0].durationMinutes == pytest.approx(39.0, abs=0.01)

    # Sleep performance
    scores = [m for m in payload.measurements.instantaneous if m.type == "SLEEP_SCORE"]
    assert len(scores) == 1
    assert scores[0].value == 92.0
    assert scores[0].metadata.get("efficiency") == 91.6


@pytest.mark.asyncio
async def test_whoop_provider_parses_workouts():
    provider = WhoopProvider()

    # Whoop API v2 workout bundle
    mock_bundle = {
        "workout": {
            "records": [
                {
                    "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
                    "user_id": 98412,
                    "created_at": "2024-11-12T11:45:00.000Z",
                    "start": "2024-11-12T10:15:00.000Z",
                    "end": "2024-11-12T11:12:30.000Z",  # 57m 30s
                    "sport_name": "Running",
                    "score_state": "SCORED",
                    "score": {
                        "strain": 14.82,
                        "average_heart_rate": 154,
                        "max_heart_rate": 178,
                        "kilojoule": 2480.5,  # ca. 592.85 kcal
                        "percent_recorded": 100.0,
                        "distance_meter": 8450.0,
                        "altitude_gain_meter": 62.0,
                    },
                }
            ]
        }
    }

    payload = await provider.fetch_telemetry(
        patient_id="p-whoop-strap-043",
        credentials={"token": "dummy", "mock_data": mock_bundle},
    )

    # Exercise time
    work_dur = [m for m in payload.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(work_dur) == 1
    assert work_dur[0].durationMinutes == pytest.approx(57.5, abs=0.01)
    assert work_dur[0].metadata.get("sport") == "RUNNING"
    assert work_dur[0].metadata.get("strain") == "14.82"

    # Calories converted from kJ to kcal
    cals = [m for m in payload.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(cals) == 1
    assert cals[0].value == round(2480.5 * 0.239006, 1)
    assert cals[0].unit == "kcal"

    # Distance
    dist = [m for m in payload.measurements.cumulative if m.type == "DISTANCE_WALKING_RUNNING"]
    assert len(dist) == 1
    assert dist[0].value == 8450.0
    assert dist[0].unit == "m"

    # Avg and Max heart rate
    hrs = [m for m in payload.measurements.instantaneous if m.type == "HEART_RATE"]
    assert len(hrs) == 2
    avg_hr = [m for m in hrs if m.metadata.get("metric") == "average_heart_rate"][0]
    max_hr = [m for m in hrs if m.metadata.get("metric") == "max_heart_rate"][0]
    assert avg_hr.value == 154.0
    assert max_hr.value == 178.0


def test_whoop_webhook_signature_verification(monkeypatch):
    import base64
    import hashlib
    import hmac

    secret = "whoop_super_secret_test_key_8492"
    monkeypatch.setenv("WHOOP_CLIENT_ID", "whoop_client_99")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", secret)
    get_settings.cache_clear()

    provider = WhoopProvider()

    timestamp = "1731412800000"
    body = '{"user_id":10129,"id":"ecfc6a15-4661-442f-a9a4-f160dd7afae8","type":"workout.updated"}'

    # Compute valid signature
    msg = timestamp.encode("utf-8") + body.encode("utf-8")
    valid_sig = base64.b64encode(
        hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    ).decode("ascii")

    # Positive check
    assert provider.verify_webhook_signature(timestamp, body, valid_sig) is True
    assert provider.verify_webhook_signature(timestamp, body.encode("utf-8"), valid_sig) is True

    # Tampered body check
    tampered_body = '{"user_id":10129,"id":"ecfc6a15-4661-442f-a9a4-f160dd7afae8","type":"workout.deleted"}'
    assert provider.verify_webhook_signature(timestamp, tampered_body, valid_sig) is False

    # Bad signature check
    assert provider.verify_webhook_signature(timestamp, body, "bad_base64_sig==") is False


def test_whoop_v2_webhook_parsing_with_uuid():
    provider = WhoopProvider()

    # WHOOP v2 webhook format with UUID
    v2_webhook_event = {
        "user_id": 98412,
        "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
        "type": "workout.updated",
        "trace_id": "e369c784-5100-49e8-8098-75d35c47b31b",
        "data": {
            "workout": [
                {
                    "id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8",
                    "sport_name": "Cycling",
                    "start": "2024-11-12T14:00:00.000Z",
                    "end": "2024-11-12T14:45:00.000Z",
                    "score": {
                        "strain": 11.2,
                        "average_heart_rate": 142,
                        "max_heart_rate": 165,
                        "kilojoule": 1820.0,
                        "distance_meter": 16400.0,
                    },
                }
            ]
        },
    }

    def resolver(whoop_user_id: str):
        if whoop_user_id == "98412":
            return "patient-charite-whoop-984"
        return None

    payloads = provider.parse_webhook_payload(
        data=v2_webhook_event,
        resolve_patient_id=resolver,
    )

    assert len(payloads) == 1
    p = payloads[0]
    assert p.participantId == "patient-charite-whoop-984"
    assert p.sourcePlatform == "whoop"
    assert p.deviceInfo.platform == "Whoop"

    # Workout duration and metadata
    durs = [m for m in p.measurements.duration if m.type == "EXERCISE_TIME"]
    assert len(durs) == 1
    assert durs[0].durationMinutes == pytest.approx(45.0, abs=0.01)
    assert durs[0].metadata.get("id") == "ecfc6a15-4661-442f-a9a4-f160dd7afae8"
    assert durs[0].metadata.get("sport") == "CYCLING"
    assert durs[0].metadata.get("strain") == "11.2"

    # Energy burned
    cals = [m for m in p.measurements.cumulative if m.type == "ACTIVE_ENERGY_BURNED"]
    assert len(cals) == 1
    assert cals[0].value == round(1820.0 * 0.239006, 1)
