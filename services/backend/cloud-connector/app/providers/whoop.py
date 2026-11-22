import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
from urllib.parse import urlencode
import httpx

from .base import BaseCloudProvider
from ..models import (
    IngestPayload,
    DeviceInfo,
    BatchInfo,
    Measurements,
    InstantaneousMeasurement,
    CumulativeMeasurement,
    DurationMeasurement,
    WaveformMeasurement,
)
from ..config import get_settings

logger = logging.getLogger(__name__)


class WhoopProvider(BaseCloudProvider):
    """Whoop Developer API v2 Cloud Provider: Built only for WHOOP API v2 (not v1!):
    - Recovery: Recovery score, resting heart rate, HRV (RMSSD), SpO2 and skin temperature
    - Sleep: Total sleep duration, sleep stages (Deep / Slow Wave, Light, REM, Awake) + Sleep Performance and Score
    - Workouts: Exercise duration, active calories (converted from kJ), distance, avg/max heart rate, strain
    - Cycles: Daily strain and physiological cycle tracking
    """

    @property
    def provider_name(self) -> str:
        return "whoop"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.whoop_api_base_url
        self.auth_url = self._settings.whoop_auth_url
        self.token_url = self._settings.whoop_token_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.whoop_client_id.strip()
        client_secret = settings.whoop_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET must be set in the environment"
            )
        return client_id, client_secret

    def _build_basic_auth_header(self, client_id: str, client_secret: str) -> str:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a 64 char code_verifier and S256 code_challenge"""
        code_verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None,
    ) -> str:
        client_id, _ = self._get_client_credentials()
        effective_redirect = redirect_uri or get_settings().oauth_redirect_uri
        scopes = [
            "offline",
            "read:recovery",
            "read:cycles",
            "read:workout",
            "read:sleep",
            "read:profile",
            "read:body_measurement",
        ]
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "redirect_uri": effective_redirect,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        effective_redirect = redirect_uri or get_settings().oauth_redirect_uri

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": code_verifier,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                logger.error("Whoop token exchange failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Whoop token exchange failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "offline",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                logger.error("Whoop token refresh failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Whoop token refresh failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/user/profile/basic"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    user_id = data.get("user_id") or "whoop-user"
                    return {
                        "userId": str(user_id),
                        "email": data.get("email", ""),
                        "firstName": data.get("first_name", ""),
                        "lastName": data.get("last_name", ""),
                        "permissions": ["read:recovery", "read:cycles", "read:workout", "read:sleep"],
                    }
        except Exception as e:
            logger.warning("Failed to fetch Whoop user profile: %s", e)

        return {"userId": "whoop-user", "permissions": ["read:recovery", "read:sleep", "read:workout"]}

    async def deregister_user(self, access_token: str) -> bool:
        """Revokes the user's Whoop access token."""
        client_id, client_secret = self._get_client_credentials()
        url = "https://api.prod.whoop.com/oauth/oauth2/revoke"
        data = {
            "token": access_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("Failed to revoke Whoop token: %s", e)
            return False

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        token = credentials.get("token") or credentials.get("access_token")
        if not token or not isinstance(token, str):
            return False
        return len(token.strip()) > 0

    def verify_webhook_signature(
        self,
        timestamp: str,
        raw_body: bytes | str,
        signature: str,
    ) -> bool:
        """Verifies WHOOP v2 webhook request with HMAC-SHA256 and WHOOP_CLIENT_SECRET
        WHOOP signs each webhook delivery: calculated_signature = Base64(HMAC-SHA256(timestamp_header + raw_body, client_secret))

        Header 'X-WHOOP-Signature-Timestamp' contains the timestamp in ms epoch
        Header 'X-WHOOP-Signature' contains the base64-encoded signature
        """
        _, client_secret = self._get_client_credentials()
        body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
        msg = timestamp.encode("utf-8") + body_bytes
        computed = base64.b64encode(
            hmac.new(client_secret.encode("utf-8"), msg, hashlib.sha256).digest()
        ).decode("ascii")
        return secrets.compare_digest(computed, signature.strip())

    async def fetch_workout_by_id(
        self,
        workout_id: str,
        access_token: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetches a specific workout by its UUID"""
        url = f"{self.base_url.rstrip('/')}/activity/workout/{workout_id}"
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.warning("Failed to fetch Whoop workout %s: %s", workout_id, e)
        return None

    async def fetch_sleep_by_id(
        self,
        sleep_id: str,
        access_token: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetches a specific sleep session by its UUID"""
        url = f"{self.base_url.rstrip('/')}/activity/sleep/{sleep_id}"
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.warning("Failed to fetch Whoop sleep %s: %s", sleep_id, e)
        return None

    async def fetch_telemetry(
        self,
        patient_id: str,
        credentials: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> IngestPayload:
        now = datetime.now(timezone.utc)
        start = start_time or (now - timedelta(days=1))
        end = end_time or now

        token = credentials.get("token") or credentials.get("access_token", "")
        mock_data = credentials.get("mock_data")

        instantaneous_list: List[InstantaneousMeasurement] = []
        cumulative_list: List[CumulativeMeasurement] = []
        duration_list: List[DurationMeasurement] = []
        waveform_list: List[WaveformMeasurement] = []

        if mock_data:
            inst, cum, dur = self._parse_whoop_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
        else:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
            params = {"start": start_iso, "end": end_iso, "limit": 25}

            async with httpx.AsyncClient(timeout=15.0) as client:
                # Recovery (recovery score, RHR, HRV, SpO2, skin temp)
                try:
                    rec_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/recovery",
                        headers=headers,
                        params=params,
                    )
                    if rec_resp.status_code == 200:
                        inst = self._parse_recovery(rec_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Whoop recovery: %s", e)

                # Sleep (duration, stages, sleep performance score)
                try:
                    sleep_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/activity/sleep",
                        headers=headers,
                        params=params,
                    )
                    if sleep_resp.status_code == 200:
                        inst, dur = self._parse_sleep(sleep_resp.json())
                        instantaneous_list.extend(inst)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Whoop sleep: %s", e)

                # Workouts (strain, calories, distance, avg/max HR)
                try:
                    workout_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/activity/workout",
                        headers=headers,
                        params=params,
                    )
                    if workout_resp.status_code == 200:
                        inst, cum, dur = self._parse_workouts(workout_resp.json())
                        instantaneous_list.extend(inst)
                        cumulative_list.extend(cum)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Whoop workouts: %s", e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Whoop",
                deviceId="cloud-connector:whoop",
                authorizationToken="cloud-connector-whoop",
            ),
            batchInfo=BatchInfo(
                collectionStart=start,
                collectionEnd=end,
                lastSendTime=now,
            ),
            measurements=Measurements(
                instantaneous=instantaneous_list,
                cumulative=cumulative_list,
                duration=duration_list,
                waveforms=waveform_list,
            ),
            sourceName="Whoop Cloud API (Whoop Strap)",
            sourcePlatform="whoop",
            sourceId="whoop-cloud",
            participantId=patient_id,
            timestamp=now,
        )

    def _parse_whoop_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        if "recovery" in bundle:
            inst.extend(self._parse_recovery(bundle["recovery"]))

        if "sleep" in bundle:
            s_inst, s_dur = self._parse_sleep(bundle["sleep"])
            inst.extend(s_inst)
            dur.extend(s_dur)

        if "workout" in bundle:
            w_inst, w_cum, w_dur = self._parse_workouts(bundle["workout"])
            inst.extend(w_inst)
            cum.extend(w_cum)
            dur.extend(w_dur)

        return inst, cum, dur

    def _parse_recovery(self, data: Any) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for rec in records:
            if not isinstance(rec, dict):
                continue

            created_at_str = rec.get("created_at") or rec.get("timestamp")
            if not created_at_str:
                continue

            try:
                ts = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)

            score_obj = rec.get("score", {})
            if not isinstance(score_obj, dict):
                continue

            meta = {
                "provider": "whoop",
                "cycle_id": str(rec.get("cycle_id", "")),
                "score_state": rec.get("score_state", "SCORED"),
            }

            # Recovery Score (0-100)
            rec_score = score_obj.get("recovery_score")
            if isinstance(rec_score, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="RECOVERY_SCORE",
                        timestamp=ts,
                        value=float(rec_score),
                        unit="SCORE",
                        metadata=meta,
                    )
                )

            # Resting Heart Rate
            rhr = score_obj.get("resting_heart_rate")
            if isinstance(rhr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="RESTING_HEART_RATE",
                        timestamp=ts,
                        value=float(rhr),
                        unit="count/min",
                        metadata=meta,
                    )
                )

            # Heart Rate Variability (RMSSD in ms)
            hrv = score_obj.get("hrv_rmssd_milli")
            if isinstance(hrv, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE_VARIABILITY",
                        timestamp=ts,
                        value=float(hrv),
                        unit="ms",
                        metadata={**meta, "metric": "hrv_rmssd"},
                    )
                )

            #  SpO2 percentage
            spo2 = score_obj.get("spo2_percentage")
            if isinstance(spo2, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="OXYGEN_SATURATION",
                        timestamp=ts,
                        value=float(spo2),
                        unit="%",
                        metadata=meta,
                    )
                )

            # Skin temperature
            skin_temp = score_obj.get("skin_temp_celsius")
            if isinstance(skin_temp, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="SKIN_TEMPERATURE",
                        timestamp=ts,
                        value=float(skin_temp),
                        unit="degC",
                        metadata=meta,
                    )
                )

        return inst

    def _parse_sleep(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        dur: List[DurationMeasurement] = []

        records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for rec in records:
            if not isinstance(rec, dict):
                continue

            start_str = rec.get("start")
            end_str = rec.get("end")
            if not (start_str and end_str):
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except Exception:
                continue

            meta = {
                "provider": "whoop",
                "id": str(rec.get("id", "")),
                "nap": rec.get("nap", False),
            }

            score_obj = rec.get("score", {})
            stage_summary = score_obj.get("stage_summary", {}) if isinstance(score_obj, dict) else {}

            total_in_bed_ms = stage_summary.get("total_in_bed_time_milli")
            total_sec = (
                float(total_in_bed_ms) / 1000.0
                if isinstance(total_in_bed_ms, (int, float)) and total_in_bed_ms > 0
                else (end_dt - start_dt).total_seconds()
            )

            dur.append(
                DurationMeasurement(
                    type="SLEEP",
                    value=float(total_sec) / 60.0,
                    unit="MINUTE",
                    startTime=start_dt,
                    endTime=end_dt,
                    durationMinutes=float(total_sec) / 60.0,
                    metadata=meta,
                )
            )

            # Sleep stages
            deep_ms = stage_summary.get("total_slow_wave_sleep_time_milli")
            if isinstance(deep_ms, (int, float)) and deep_ms > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_DEEP",
                        value=round(float(float(deep_ms) / 1000.0) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(deep_ms) / 1000.0) / 60.0, 2),
                        metadata=meta,
                    )
                )

            light_ms = stage_summary.get("total_light_sleep_time_milli")
            if isinstance(light_ms, (int, float)) and light_ms > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_LIGHT",
                        value=round(float(float(light_ms) / 1000.0) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(light_ms) / 1000.0) / 60.0, 2),
                        metadata=meta,
                    )
                )

            rem_ms = stage_summary.get("total_rem_sleep_time_milli")
            if isinstance(rem_ms, (int, float)) and rem_ms > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_REM",
                        value=round(float(float(rem_ms) / 1000.0) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(rem_ms) / 1000.0) / 60.0, 2),
                        metadata=meta,
                    )
                )

            awake_ms = stage_summary.get("total_awake_time_milli")
            if isinstance(awake_ms, (int, float)) and awake_ms > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_AWAKE",
                        value=round(float(float(awake_ms) / 1000.0) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(awake_ms) / 1000.0) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Sleep performance percentage
            if isinstance(score_obj, dict):
                sleep_score = score_obj.get("sleep_performance_percentage")
                if isinstance(sleep_score, (int, float)):
                    inst.append(
                        InstantaneousMeasurement(
                            type="SLEEP_SCORE",
                            timestamp=end_dt,
                            value=float(sleep_score),
                            unit="SCORE",
                            metadata={
                                **meta,
                                "efficiency": score_obj.get("sleep_efficiency_percentage"),
                            },
                        )
                    )

        return inst, dur

    def _parse_workouts(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for rec in records:
            if not isinstance(rec, dict):
                continue

            start_str = rec.get("start")
            end_str = rec.get("end")
            if not (start_str and end_str):
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except Exception:
                continue

            duration_sec = (end_dt - start_dt).total_seconds()
            sport = str(rec.get("sport_name") or rec.get("sport_id") or "WORKOUT").upper()
            score_obj = rec.get("score", {}) if isinstance(rec.get("score"), dict) else {}

            meta = {
                "sport": sport,
                "provider": "whoop",
                "id": str(rec.get("id", "")),
            }
            if "strain" in score_obj:
                meta["strain"] = str(score_obj["strain"])

            if duration_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="EXERCISE_TIME",
                        value=float(duration_sec) / 60.0,
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=float(duration_sec) / 60.0,
                        metadata=meta,
                    )
                )

            # Calories: Whoop reports kilojoules instead of kcal
            kj = score_obj.get("kilojoule")
            if isinstance(kj, (int, float)) and kj > 0:
                kcal = float(kj) * 0.239006
                cum.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        value=round(kcal, 1),
                        unit="kcal",
                        periodStart=start_dt,
                        periodEnd=end_dt,
                        duration=max(0, int((end_dt - start_dt).total_seconds())),
                        metadata=meta,
                    )
                )

            # Distance in meters
            dist = score_obj.get("distance_meter")
            if isinstance(dist, (int, float)) and dist > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        value=float(dist),
                        unit="m",
                        periodStart=start_dt,
                        periodEnd=end_dt,
                        duration=max(0, int((end_dt - start_dt).total_seconds())),
                        metadata=meta,
                    )
                )

            # Average & max heart rate during workout
            avg_hr = score_obj.get("average_heart_rate")
            if isinstance(avg_hr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=end_dt,
                        value=float(avg_hr),
                        unit="count/min",
                        metadata={**meta, "metric": "average_heart_rate"},
                    )
                )

            max_hr = score_obj.get("max_heart_rate")
            if isinstance(max_hr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=end_dt,
                        value=float(max_hr),
                        unit="count/min",
                        metadata={**meta, "metric": "max_heart_rate"},
                    )
                )

        return inst, cum, dur

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        """Parses incoming WHOOP v2 webhook events

        Notifications with schema:
        {
            "user_id": 10129,
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "sleep.updated",  # or workout.updated, recovery.updated
            "trace_id": "e369c784-5100-49e8-8098-75d35c47b31b"
        }
        In recovery.updated, 'id' points to the UUID of the associated sleep
        """
        logger.info("Received Whoop v2 webhook payload: %s", data)
        payloads: List[IngestPayload] = []

        events = data if isinstance(data, list) else [data]

        for event in events:
            if not isinstance(event, dict):
                continue

            user_id = event.get("user_id")
            event_id = event.get("id")
            event_type = event.get("type", "")
            trace_id = event.get("trace_id")

            if not user_id:
                continue

            patient_id = resolve_patient_id(str(user_id)) or default_patient_id
            if not patient_id:
                logger.warning("No patient mapping found for Whoop user %s", user_id)
                continue

            # If the event payload contains embedded telemetry records
            embedded = event.get("data") or event.get("record") or event.get("payload")
            if embedded and isinstance(embedded, dict):
                inst, cum, dur = self._parse_whoop_bundle(embedded)
                if inst or cum or dur:
                    now = datetime.now(timezone.utc)
                    payloads.append(
                        IngestPayload(
                            deviceInfo=DeviceInfo(
                                platform="Whoop",
                                deviceId=f"cloud-connector:whoop:{user_id}",
                                authorizationToken="cloud-connector-whoop",
                            ),
                            batchInfo=BatchInfo(
                                collectionStart=now,
                                collectionEnd=now,
                                lastSendTime=now,
                            ),
                            measurements=Measurements(
                                instantaneous=inst,
                                cumulative=cum,
                                duration=dur,
                                waveforms=[],
                            ),
                            sourceName="Whoop Cloud API v2 (Webhook)",
                            sourcePlatform="whoop",
                            sourceId=f"whoop-{event_id or user_id}",
                            participantId=patient_id,
                            timestamp=now,
                        )
                    )

        return payloads
