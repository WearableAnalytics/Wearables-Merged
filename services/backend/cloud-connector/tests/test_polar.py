"""Synthetic examples shaped like the v4 responses. No cloud credentials needed."""

import json
from zoneinfo import ZoneInfo

from app.providers.polar import batches, normalize

DAY = "2026-10-30"
AT = DAY + "T11:15:00+01:00"
END = DAY + "T11:25:00+01:00"
DEVICE = "test-polar-360"
DOCS = {
    "pulse": {
        "continuousSamples": {
            "heartRateSamplesPerDay": [
                {
                    "date": DAY,
                    "deviceRef": {"deviceId": DEVICE},
                    "samples": [{"offsetMillis": 40500000, "heartRate": 72}],
                }
            ]
        }
    },
    "intervals": {
        "dailyPpiSamples": [
            {
                "date": DAY,
                "ppiSamplesPerDevice": [
                    {
                        "recordingDevice": {"uuid": DEVICE},
                        "ppiSamples": [
                            {
                                "offsetMillis": 40500000,
                                "ppInterval": 830,
                                "errorEstimateMillis": 8,
                                "skinContact": True,
                                "movement": False,
                            }
                        ],
                    }
                ],
            }
        ]
    },
    "activity": {
        "activities": {
            "activityDays": [
                {
                    "date": DAY,
                    "activitiesPerDevice": [
                        {
                            "deviceReference": {"deviceId": DEVICE},
                            "activitySamples": [
                                {
                                    "stepSamples": {
                                        "startTime": "11:15:00",
                                        "interval": "60000",
                                        "steps": [12],
                                    },
                                    "metSamples": {
                                        "startTime": "11:15:00",
                                        "interval": "60000",
                                        "mets": [1.2],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    },
    "temperature": {
        "temperatureMeasurementPeriod": [
            {
                "startTime": AT,
                "measurementType": "TM_SKIN_TEMPERATURE",
                "deviceReference": {"uuid": DEVICE},
                "temperatureMeasurementSamples": [
                    {"recordingTimeDeltaMilliseconds": 10, "temperatureCelsius": 33.2}
                ],
            }
        ]
    },
    "contact": {
        "skinContactPeriods": [
            {
                "startTime": AT,
                "deviceReference": {"uuid": DEVICE},
                "skinContactChanges": [{"recordingTimeDeltaMilliseconds": 0, "skinContact": True}],
            }
        ]
    },
    "sleep": {
        "nightSleeps": [
            {
                "sleepScore": {"sleepScore": 85},
                "sleepResult": {
                    "hypnogram": {
                        "sleepStart": AT,
                        "sleepEnd": END,
                        "deviceReference": {"uuid": DEVICE},
                        "sleepStateChanges": [
                            {"offsetFromStart": f"{i * 60}s", "newState": "SLEEP_STATE_" + level}
                            for i, level in enumerate(["WAKE", "NON_REM2", "NON_REM3", "REM"])
                        ],
                    }
                },
            }
        ]
    },
    "training": {
        "trainingSessions": [
            {
                "identifier": {"id": "test-session"},
                "deviceId": DEVICE,
                "startTime": AT,
                "stopTime": END,
                "distanceMeters": 1234,
                "calories": 42,
            }
        ]
    },
    "recovery": {
        "nightlyRechargeResults": {
            "nightlyRechargeResults": [
                {
                    "created": END,
                    "sleepResultDate": DAY,
                    "meanNightlyRecoveryRmssd": 58,
                    "breathingRateSamples": [
                        {"startTime": AT, "sampleInterval": "300s", "breathingRateValues": [12.5]}
                    ],
                }
            ]
        }
    },
}


def test_all_streams_have_distinct_stable_measurements():
    zone = ZoneInfo("Europe/Berlin")
    rows = [item for stream, data in DOCS.items() for item in normalize(stream, data, zone)]
    expected = {
        "HEART_RATE": (72, "/min"),
        "STEPS": (12, "1"),
        "POLAR_ACTIVITY_MET": (1.2, "1"),
        "WORKOUT_ELAPSED_TIME": (10, "min"),
        "POLAR_WORKOUT_ENERGY": (42, "kcal"),
        "DISTANCE_DELTA": (1234, "m"),
        "SLEEP_AWAKE": (1, "min"),
        "SLEEP_LIGHT": (1, "min"),
        "SLEEP_DEEP": (1, "min"),
        "SLEEP_REM": (7, "min"),
        "POLAR_SLEEP_SCORE": (85, "1"),
        "RESPIRATORY_RATE": (12.5, "/min"),
        "POLAR_NIGHTLY_MEAN_RMSSD": (58, "ms"),
        "SKIN_TEMPERATURE": (33.2, "Cel"),
        "PULSE_TO_PULSE_INTERVAL": (830, "ms"),
        "POLAR_PPI_ERROR_ESTIMATE": (8, "ms"),
        "POLAR_SKIN_CONTACT": (1, "1"),
    }
    assert {r["type"]: (r["value"], r["unit"]) for _, r in rows} == expected
    assert len({r["sourceRecordId"] for _, r in rows}) == len(rows)
    first, count = next(batches(rows, "test"))
    assert next(batches(reversed(rows), "test")) == (first, count)
    result = json.loads(first)
    pulse = next(r for r in result["measurements"]["instantaneous"] if r["type"] == "HEART_RATE")
    assert pulse["timestamp"] == "2026-10-30T10:15:00.000000Z"
    assert pulse["sourceDeviceId"] == DEVICE
    assert (
        sum(r["durationMinutes"] for r in result["measurements"]["duration"] if r["type"].startswith("SLEEP"))
        == 10
    )


def test_authorization_preview_and_idempotent_share(monkeypatch):
    import hashlib
    from urllib.parse import parse_qs, urlsplit
    from uuid import uuid4

    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import polar_sync
    from app.security import verify_case_verification_token

    application = FastAPI()
    application.include_router(polar_sync.router)
    claims = {"caseId": "test-case", "patientId": "test-participant"}
    application.dependency_overrides[verify_case_verification_token] = lambda: claims
    for key, value in {
        "POLAR_CLIENT_ID": "test",
        "POLAR_CLIENT_SECRET": "test-secret",
        "POLAR_REDIRECT_URI": "https://demo.local/cloud/polar/callback",
        "POLAR_INGEST_URL": "http://importer.local/ingest",
    }.items():
        monkeypatch.setenv(key, value)
    delivered = []
    attempts = []

    def transport(req):
        if req.url.host == "auth.polar.com":
            return httpx.Response(200, json={"access_token": "test-polar-only"})
        if req.url.host == "www.polaraccesslink.com":
            assert req.headers["authorization"] == "Bearer test-polar-only"
            stream = next(
                k for k, (path, *_) in polar_sync.STREAMS.items() if req.url.path == "/v4/data/" + path
            )
            return httpx.Response(200, json=DOCS[stream])
        assert req.url.host == "importer.local"
        assert req.headers["authorization"] == "Bearer study-test"
        digest = hashlib.sha256(req.content).hexdigest()
        assert req.headers["idempotency-key"] == digest
        attempts.append(digest)
        # A lost receipt in the middle must not resend the first archived batch.
        if len(attempts) == 2:
            return httpx.Response(202, json={})
        delivered.append(digest)
        count = sum(map(len, json.loads(req.content)["measurements"].values()))
        return httpx.Response(
            202,
            json={
                "status": "archived",
                "acceptanceId": str(uuid4()),
                "rawSha256": digest,
                "readingCount": count,
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw)
    )
    with TestClient(application, headers={"Authorization": "Bearer study-test"}) as client:
        started = client.post(
            "/polar/sessions", json={"day": DAY, "timezone": "Europe/Berlin", "streams": list(DOCS)}
        ).json()
        session = "/polar/sessions/" + started["session"]
        state = parse_qs(urlsplit(started["url"]).query)["state"][0]
        assert client.post(session + "/share").status_code == 409
        assert client.get("/polar/callback", params={"code": "test", "state": state}).status_code == 200
        assert client.get("/polar/callback", params={"code": "test", "state": state}).status_code == 400
        claims["caseId"] = "other"
        assert client.post(session + "/preview").status_code == 404
        claims["caseId"] = "test-case"
        counts = client.post(session + "/preview").json()
        assert len(counts) == 17 and not delivered
        assert client.post(session + "/share").status_code == 502
        receipts = client.post(session + "/share").json()
        assert attempts[0] != attempts[1] == attempts[2]
        assert len(receipts["receipts"]) == len(DOCS)
        assert client.post(session + "/share").json() == receipts
        assert len(delivered) == len(DOCS)
        assert client.delete(session).status_code == 204
        assert client.post(session + "/preview").status_code == 404
