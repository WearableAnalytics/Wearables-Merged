#!/usr/bin/env python3
"""Synthetic wearable data generator for the local stack.

Sends batches to importservice (/import/ingest via Traefik) in the same shape the
mobile app produces (lib/health_data_formatter.dart), so the whole pipeline runs
without a phone. Standard library only.

  # token copied from a case created in the web UI (recommended: the patient exists in db_lord)
  python3 generate.py --token <case-token> --backfill-hours 24 --live 60

  # or sign a token locally with the same secret as wearables-bff / importservice
  python3 generate.py --patient-id demo-patient-1 --backfill-hours 6
"""

import argparse
import base64
import hashlib
import hmac
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_case_token(patient_id: str, case_id: str, secret: str, issuer: str, ttl: int) -> str:
    """HS256 JWT with the claims wearables-bff puts into case tokens (tokenService.ts)."""
    # Backdated: the Docker VM clock can lag the host (e.g. after sleep), and importservice
    # rejects tokens "issued in the future".
    now = int(time.time()) - 60
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "caseId": case_id,
        "patientId": patient_id,
        "type": "case-verification",
        "iss": issuer,
        "sub": case_id,
        "iat": now,
        "exp": now + ttl,
    }
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(claims).encode())}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(signature)}"


def iso(ts: datetime) -> str:
    # The app sends UTC wall-clock time without offset; the mapper appends "Z".
    return ts.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="milliseconds")


def is_asleep(ts: datetime) -> bool:
    return ts.hour >= 23 or ts.hour < 7


def heart_rate(ts: datetime, active: bool) -> float:
    circadian = 6 * math.sin((ts.hour + ts.minute / 60 - 10) / 24 * 2 * math.pi)
    base = 56 if is_asleep(ts) else 68
    return round(base + circadian + (35 if active else 0) + random.gauss(0, 3))


def generate_window(start: datetime, end: datetime) -> dict:
    """Readings for [start, end): HR every ~5 min, activity per minute, sleep at night."""
    instantaneous, cumulative, duration = [], [], []

    ts = start
    while ts < end:
        active = not is_asleep(ts) and random.random() < 0.15
        instantaneous.append(
            {"type": "HEART_RATE", "value": heart_rate(ts, active), "unit": "BEATS_PER_MINUTE", "timestamp": iso(ts)}
        )
        if random.random() < 0.3:
            instantaneous.append(
                {"type": "RESPIRATORY_RATE", "value": round(random.uniform(12, 18), 1),
                 "unit": "RESPIRATIONS_PER_MINUTE", "timestamp": iso(ts)}
            )
        if is_asleep(ts) and random.random() < 0.2:
            instantaneous.append(
                {"type": "HEART_RATE_VARIABILITY_SDNN", "value": round(random.uniform(30, 80), 1),
                 "unit": "MILLISECOND", "timestamp": iso(ts)}
            )

        if not is_asleep(ts):
            period_end = ts + timedelta(minutes=1)
            steps = random.randint(60, 120) if active else random.randint(0, 15)
            for type_, value, unit in (
                ("STEPS", steps, "COUNT"),
                ("DISTANCE_WALKING_RUNNING", round(steps * 0.75, 1), "METER"),
                ("ACTIVE_ENERGY_BURNED", round(steps * 0.04 + random.uniform(0, 0.2), 3), "KILOCALORIE"),
                ("BASAL_ENERGY_BURNED", round(random.uniform(1.0, 1.2), 3), "KILOCALORIE"),
            ):
                cumulative.append(
                    {"type": type_, "value": value, "unit": unit, "periodStart": iso(ts),
                     "periodEnd": iso(period_end), "duration": 60}
                )

        ts += timedelta(minutes=5) + timedelta(seconds=random.randint(-30, 30))

    # One sleep stage block per 30 min of night inside the window.
    ts = start
    while ts < end:
        if is_asleep(ts):
            stage = random.choice(["SLEEP_ASLEEP_CORE", "SLEEP_ASLEEP_DEEP", "SLEEP_ASLEEP_REM", "SLEEP_AWAKE"])
            stage_end = min(ts + timedelta(minutes=30), end)
            minutes = int((stage_end - ts).total_seconds() // 60)
            if minutes > 0:
                duration.append(
                    {"type": stage, "value": float(minutes), "unit": "MINUTE", "startTime": iso(ts),
                     "endTime": iso(stage_end), "durationMinutes": minutes}
                )
        ts += timedelta(minutes=30)

    return {"instantaneous": instantaneous, "cumulative": cumulative, "duration": duration}


def send(url: str, token: str, start: datetime, end: datetime, device_name: str) -> None:
    measurements = generate_window(start, end)
    payload = {
        "deviceInfo": {"platform": "iOS", "deviceId": "generator"},  # replaced by patientId server-side
        "batchInfo": {"collectionStart": iso(start), "collectionEnd": iso(end), "lastSendTime": None},
        "measurements": measurements,
        "sourceName": device_name,
        "sourcePlatform": "generator",
        "totalStepsToday": None,
        "timestamp": iso(datetime.now(timezone.utc)),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"{iso(start)} -> {iso(end)}: {response.status} {response.read().decode()}")
    except urllib.error.HTTPError as err:
        sys.exit(f"{err.code} from {url}: {err.read().decode()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost/import/ingest")
    auth = parser.add_mutually_exclusive_group(required=True)
    auth.add_argument("--token", help="case token from the web UI (QR code content)")
    auth.add_argument("--patient-id", help="sign a token locally for this patient id")
    parser.add_argument("--case-id", help="case id for a locally signed token (default: case-<patient-id>)")
    parser.add_argument("--secret", default="dev-secret", help="JWT_SECRET of the stack")
    parser.add_argument("--issuer", default="wearables-bff")
    parser.add_argument("--backfill-hours", type=float, default=24, help="history to send first (0 = none)")
    parser.add_argument("--batch-minutes", type=int, default=60, help="window size per request")
    parser.add_argument("--live", type=int, default=0, metavar="SECONDS",
                        help="after backfill, keep sending the last SECONDS of data every SECONDS")
    parser.add_argument("--device-name", default="Synthetic Apple Watch")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
    token = args.token or sign_case_token(
        args.patient_id, args.case_id or f"case-{args.patient_id}", args.secret, args.issuer, ttl=8 * 24 * 3600
    )

    now = datetime.now(timezone.utc)
    cursor = now - timedelta(hours=args.backfill_hours)
    while cursor < now:
        window_end = min(cursor + timedelta(minutes=args.batch_minutes), now)
        send(args.url, token, cursor, window_end, args.device_name)
        cursor = window_end

    while args.live > 0:
        time.sleep(args.live)
        window_end = datetime.now(timezone.utc)
        send(args.url, token, cursor, window_end, args.device_name)
        cursor = window_end


if __name__ == "__main__":
    main()
