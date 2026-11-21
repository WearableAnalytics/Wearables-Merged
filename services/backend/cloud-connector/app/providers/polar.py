"""Normalize one authorized AccessLink v4 day. All wire times are UTC."""

import json
import math
from datetime import UTC, datetime, timedelta
from hashlib import sha256

# API path, OAuth scope, optional response features.
STREAMS = {
    "pulse": ("continuous-samples", "continuous_samples:read", ["heart-rate-samples"]),
    "activity": ("activity/list", "activity:read", ["samples"]),
    "sleep": ("sleeps", "sleep:read", ["sleep-result", "sleep-score"]),
    "training": ("training-sessions/list", "training_sessions:read", []),
    "temperature": ("temperature-measurements", "temperature_measurement:read", []),
    "intervals": ("ppi-samples", "ppi_data:read", ["samples"]),
    "contact": ("skin-contacts", "skin_contact:read", []),
    "recovery": ("nightly-recharge-results", "nightly_recharge:read", ["samples"]),
}
STAGES = {
    "SLEEP_STATE_WAKE": "SLEEP_AWAKE",
    "SLEEP_STATE_REM": "SLEEP_REM",
    "SLEEP_STATE_NON_REM1": "SLEEP_LIGHT",
    "SLEEP_STATE_NON_REM2": "SLEEP_LIGHT",
    "SLEEP_STATE_NON_REM3": "SLEEP_DEEP",
}


def instant(value, zone):
    dt = datetime.fromisoformat(value.replace(" +", "+").replace(" -", "-"))
    if dt.tzinfo is None:
        first, second = (dt.replace(tzinfo=zone, fold=f) for f in (0, 1))
        if first.utcoffset() != second.utcoffset():
            raise ValueError("Local timestamp needs an explicit offset at this clock change")
        dt = first
    return dt.astimezone(UTC)


def delta(value):
    seconds = str(value).removesuffix("s")
    return timedelta(seconds=float(seconds))


def stamp(t):
    return t.isoformat(timespec="microseconds").replace("+00:00", "Z")


def point(metric, value, unit, start, device, *, end=None, duration=False, identity=""):
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"Invalid {metric} measurement")
    key = [device, identity, metric, stamp(start)]
    row = {
        "type": metric,
        "unit": unit,
        "value": float(value),
        "sourceRecordId": sha256(json.dumps(key).encode()).hexdigest(),
    }
    if device:
        row["sourceDeviceId"] = device
    if end is None:
        return "instantaneous", dict(row, timestamp=stamp(start))
    elapsed = (end - start).total_seconds()
    if elapsed < 0:
        raise ValueError("Reversed measurement interval")
    if duration:
        return "duration", dict(row, startTime=stamp(start), endTime=stamp(end), durationMinutes=elapsed / 60)
    return "cumulative", dict(row, periodStart=stamp(start), periodEnd=stamp(end), duration=elapsed)


def normalize(stream, data, zone):
    if stream == "pulse":
        for day in data.get("continuousSamples", {}).get("heartRateSamplesPerDay", []):
            start = instant(day["date"], zone)
            for sample in day.get("samples", []):
                if int(sample["heartRate"]) > 0:
                    yield point(
                        "HEART_RATE",
                        sample["heartRate"],
                        "/min",
                        start + timedelta(milliseconds=int(sample["offsetMillis"])),
                        day["deviceRef"]["deviceId"],
                    )
    elif stream == "activity":
        for day in data.get("activities", {}).get("activityDays", []):
            for device in day.get("activitiesPerDevice", []):
                for recording in device.get("activitySamples", []):
                    for field, values, metric, unit in [
                        ("stepSamples", "steps", "STEPS", "1"),
                        ("metSamples", "mets", "POLAR_ACTIVITY_MET", "1"),
                    ]:
                        series = recording.get(field)
                        if not series:
                            continue
                        start = instant(day["date"] + "T" + series["startTime"], zone)
                        interval = timedelta(milliseconds=int(series["interval"]))
                        if interval <= timedelta(0):
                            raise ValueError("Invalid activity sample interval")
                        for value in series.get(values, []):
                            end = start + interval
                            yield point(
                                metric, value, unit, start, device["deviceReference"]["deviceId"], end=end
                            )
                            start = end
    elif stream == "training":
        for session in data.get("trainingSessions", []):
            start, end = (instant(session[key], zone) for key in ("startTime", "stopTime"))
            device = session.get("deviceId")
            key = session["identifier"]["id"]
            yield point(
                "WORKOUT_ELAPSED_TIME",
                (end - start).total_seconds() / 60,
                "min",
                start,
                device,
                end=end,
                duration=True,
                identity=key,
            )
            for field, metric, unit in [
                ("calories", "POLAR_WORKOUT_ENERGY", "kcal"),
                ("distanceMeters", "DISTANCE_DELTA", "m"),
            ]:
                if session.get(field) is not None:
                    yield point(metric, session[field], unit, start, device, end=end, identity=key)
    elif stream == "sleep":
        for night in data.get("nightSleeps", []):
            hyp = night.get("sleepResult", {}).get("hypnogram")
            if not hyp:
                continue
            start, end = (instant(hyp[k], zone) for k in ("sleepStart", "sleepEnd"))
            device = hyp.get("deviceReference", {}).get("uuid")
            states = [
                (start + delta(s["offsetFromStart"]), s["newState"]) for s in hyp.get("sleepStateChanges", [])
            ]
            for (begin, state), (until, _) in zip(states, states[1:] + [(end, None)]):
                if not start <= begin <= until <= end:
                    raise ValueError("Sleep stage falls outside sleep window")
                if state in STAGES and until > begin:
                    yield point(
                        STAGES[state],
                        (until - begin).total_seconds() / 60,
                        "min",
                        begin,
                        device,
                        end=until,
                        duration=True,
                    )
            score = night.get("sleepScore", {}).get("sleepScore")
            if score is not None:
                yield point("POLAR_SLEEP_SCORE", score, "1", end, device)
    elif stream == "intervals":
        for day in data.get("dailyPpiSamples", []):
            start = instant(day["date"], zone)
            for recording in day.get("ppiSamplesPerDevice", []):
                for sample in recording.get("ppiSamples", []):
                    if sample.get("skinContact") is not True or sample.get("movement") is not False:
                        continue
                    at = start + timedelta(milliseconds=int(sample["offsetMillis"]))
                    device = recording["recordingDevice"]["uuid"]
                    yield point("PULSE_TO_PULSE_INTERVAL", sample["ppInterval"], "ms", at, device)
                    if "errorEstimateMillis" in sample:
                        yield point(
                            "POLAR_PPI_ERROR_ESTIMATE", sample["errorEstimateMillis"], "ms", at, device
                        )
    elif stream in ("temperature", "contact"):
        skin = stream == "temperature"
        for period in data.get("temperatureMeasurementPeriod" if skin else "skinContactPeriods", []):
            if skin and period.get("measurementType") != "TM_SKIN_TEMPERATURE":
                continue
            start = instant(period["startTime"], zone)
            for sample in period.get("temperatureMeasurementSamples" if skin else "skinContactChanges", []):
                at = start + timedelta(milliseconds=int(sample["recordingTimeDeltaMilliseconds"]))
                device = period["deviceReference"]["uuid"]
                if skin:
                    yield point("SKIN_TEMPERATURE", sample["temperatureCelsius"], "Cel", at, device)
                elif isinstance(sample.get("skinContact"), bool):
                    yield point("POLAR_SKIN_CONTACT", int(sample["skinContact"]), "1", at, device)
    elif stream == "recovery":
        for result in data.get("nightlyRechargeResults", {}).get("nightlyRechargeResults", []):
            if result.get("meanNightlyRecoveryRmssd") is not None:
                yield point(
                    "POLAR_NIGHTLY_MEAN_RMSSD",
                    result["meanNightlyRecoveryRmssd"],
                    "ms",
                    instant(result["created"], zone),
                    None,
                    identity=result["sleepResultDate"],
                )
            for series in result.get("breathingRateSamples", []):
                at = instant(series["startTime"], zone)
                interval = delta(series["sampleInterval"])
                if interval <= timedelta(0):
                    raise ValueError("Invalid recovery sample interval")
                for rate in series.get("breathingRateValues", []):
                    yield point("RESPIRATORY_RATE", rate, "/min", at, None)
                    at += interval


def batches(rows, account):
    # Stable ordering and request bytes allow replay after a network interruption.
    rows = sorted(rows, key=lambda pair: pair[1]["sourceRecordId"])
    for pos in range(0, len(rows), 200):
        group = rows[pos : pos + 200]
        measurements = {"instantaneous": [], "cumulative": [], "duration": []}
        times = []
        for category, row in group:
            measurements[category].append(row)
            times.extend(
                row[k] for k in ("timestamp", "periodStart", "periodEnd", "startTime", "endTime") if k in row
            )
        payload = {
            "contractVersion": "wearables-numeric/1",
            "sourceId": "polar-accesslink:" + account,
            "sourceName": "Polar Flow",
            "sourcePlatform": "polar-accesslink",
            "deviceInfo": {"platform": "polar-cloud", "deviceId": "polar-accesslink"},
            "batchInfo": {"collectionStart": min(times), "collectionEnd": max(times)},
            "timestamp": max(times),
            "measurements": measurements,
        }
        yield json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), len(group)
