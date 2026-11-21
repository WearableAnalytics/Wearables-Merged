import base64
import hashlib
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


class OuraProvider(BaseCloudProvider):
    """Oura Ring Cloud Provider
    Supports Oura OAuth 2.0 PKCE user authorization, token refresh and telemetry sync:
    - Sleep duration & sleep stages (Light, Deep, REM, Awake) + Sleep Score
    - Daily Readiness Score & Resting Heart Rate (HRV balance, body temp)
    - Continuous Heart Rate (5-minute bzw. live resolution)
    - Workouts (Active Calories, Distance, Duration)
    - Daily Blood Oxygen (SpO2)
    """

    @property
    def provider_name(self) -> str:
        return "oura"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.oura_api_base_url
        self.auth_url = self._settings.oura_auth_url
        self.token_url = self._settings.oura_token_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.oura_client_id.strip()
        client_secret = settings.oura_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "OURA_CLIENT_ID and OURA_CLIENT_SECRET must be set in the environment"
            )
        return client_id, client_secret

    def _build_basic_auth_header(self, client_id: str, client_secret: str) -> str:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a 64-char code_verifier and S256 code_challenge per RFC 7636."""
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
        scopes = ["daily", "heartrate", "personal", "session", "sleep", "workout", "email"]
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
            "Authorization": self._build_basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                logger.error("Oura token exchange failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Oura token exchange failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        headers = {
            "Authorization": self._build_basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                logger.error("Oura token refresh failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Oura token refresh failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/usercollection/personal_info"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    user_id = data.get("id") or "oura-user"
                    return {
                        "userId": str(user_id),
                        "email": data.get("email", ""),
                        "permissions": ["daily", "heartrate", "personal", "session", "sleep", "workout"],
                    }
        except Exception as e:
            logger.warning("Failed to fetch Oura personal_info: %s", e)

        return {"userId": "oura-user", "permissions": ["daily", "heartrate", "sleep"]}

    async def deregister_user(self, access_token: str) -> bool:
        url = "https://api.ouraring.com/oauth/revoke"
        data = {"token": access_token}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("Failed to revoke Oura token: %s", e)
            return False

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        token = credentials.get("token") or credentials.get("access_token") or credentials.get("personal_token")
        if not token or not isinstance(token, str):
            return False
        return len(token.strip()) > 0

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

        token = credentials.get("token") or credentials.get("access_token") or credentials.get("personal_token", "")
        mock_data = credentials.get("mock_data")

        instantaneous_list: List[InstantaneousMeasurement] = []
        cumulative_list: List[CumulativeMeasurement] = []
        duration_list: List[DurationMeasurement] = []
        waveform_list: List[WaveformMeasurement] = []

        if mock_data:
            inst, cum, dur = self._parse_oura_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
        else:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            start_date_str = start.strftime("%Y-%m-%d")
            end_date_str = end.strftime("%Y-%m-%d")
            start_dt_str = start.strftime("%Y-%m-%dT%H:%M:%S")
            end_dt_str = end.strftime("%Y-%m-%dT%H:%M:%S")

            async with httpx.AsyncClient(timeout=15.0) as client:
                # Sleep data (sleep periods & stages)
                try:
                    sleep_url = f"{self.base_url.rstrip('/')}/usercollection/sleep?start_date={start_date_str}&end_date={end_date_str}"
                    sleep_resp = await client.get(sleep_url, headers=headers)
                    if sleep_resp.status_code == 200:
                        inst, dur = self._parse_sleep(sleep_resp.json())
                        instantaneous_list.extend(inst)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Oura sleep: %s", e)

                # Daily Readiness & Daily Sleep score
                try:
                    readiness_url = f"{self.base_url.rstrip('/')}/usercollection/daily_readiness?start_date={start_date_str}&end_date={end_date_str}"
                    readiness_resp = await client.get(readiness_url, headers=headers)
                    if readiness_resp.status_code == 200:
                        inst = self._parse_daily_readiness(readiness_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Oura readiness: %s", e)

                # Continuous Heart Rate
                try:
                    hr_url = f"{self.base_url.rstrip('/')}/usercollection/heartrate?start_datetime={start_dt_str}&end_datetime={end_dt_str}"
                    hr_resp = await client.get(hr_url, headers=headers)
                    if hr_resp.status_code == 200:
                        inst = self._parse_heart_rate(hr_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Oura heart rate: %s", e)

                # Workouts
                try:
                    workout_url = f"{self.base_url.rstrip('/')}/usercollection/workout?start_date={start_date_str}&end_date={end_date_str}"
                    workout_resp = await client.get(workout_url, headers=headers)
                    if workout_resp.status_code == 200:
                        cum, dur = self._parse_workouts(workout_resp.json())
                        cumulative_list.extend(cum)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Oura workouts: %s", e)

                # SpO2
                try:
                    spo2_url = f"{self.base_url.rstrip('/')}/usercollection/daily_spo2?start_date={start_date_str}&end_date={end_date_str}"
                    spo2_resp = await client.get(spo2_url, headers=headers)
                    if spo2_resp.status_code == 200:
                        inst = self._parse_spo2(spo2_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Oura SpO2: %s", e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Oura",
                deviceId="cloud-connector:oura",
                authorizationToken="cloud-connector-oura",
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
            sourceName="Oura Cloud API (Oura Ring)",
            sourcePlatform="oura",
            sourceId="oura-cloud",
            participantId=patient_id,
            timestamp=now,
        )

    def _parse_oura_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        if "sleep" in bundle:
            s_inst, s_dur = self._parse_sleep(bundle["sleep"])
            inst.extend(s_inst)
            dur.extend(s_dur)

        if "daily_readiness" in bundle:
            inst.extend(self._parse_daily_readiness(bundle["daily_readiness"]))

        if "heartrate" in bundle:
            inst.extend(self._parse_heart_rate(bundle["heartrate"]))

        if "workout" in bundle:
            w_cum, w_dur = self._parse_workouts(bundle["workout"])
            cum.extend(w_cum)
            dur.extend(w_dur)

        if "daily_spo2" in bundle:
            inst.extend(self._parse_spo2(bundle["daily_spo2"]))

        return inst, cum, dur

    def _parse_sleep(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        dur: List[DurationMeasurement] = []

        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in items:
            if not isinstance(item, dict):
                continue

            start_str = item.get("bedtime_start")
            end_str = item.get("bedtime_end")
            if not (start_str and end_str):
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except Exception:
                continue

            total_sec = float(item.get("total_sleep_duration", (end_dt - start_dt).total_seconds()))
            meta = {
                "provider": "oura",
                "documentId": str(item.get("id", "")),
                "type": item.get("type", "long_sleep"),
            }

            dur.append(
                DurationMeasurement(
                    type="SLEEP",
                    start=start_dt,
                    end=end_dt,
                    duration=total_sec,
                    unit="s",
                    metadata=meta,
                )
            )

            # Sleep stages
            deep_sec = item.get("deep_sleep_duration")
            if isinstance(deep_sec, (int, float)) and deep_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_DEEP",
                        start=start_dt,
                        end=end_dt,
                        duration=float(deep_sec),
                        unit="s",
                        metadata=meta,
                    )
                )

            light_sec = item.get("light_sleep_duration")
            if isinstance(light_sec, (int, float)) and light_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_LIGHT",
                        start=start_dt,
                        end=end_dt,
                        duration=float(light_sec),
                        unit="s",
                        metadata=meta,
                    )
                )

            rem_sec = item.get("rem_sleep_duration")
            if isinstance(rem_sec, (int, float)) and rem_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_REM",
                        start=start_dt,
                        end=end_dt,
                        duration=float(rem_sec),
                        unit="s",
                        metadata=meta,
                    )
                )

            awake_sec = item.get("awake_time")
            if isinstance(awake_sec, (int, float)) and awake_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_AWAKE",
                        start=start_dt,
                        end=end_dt,
                        duration=float(awake_sec),
                        unit="s",
                        metadata=meta,
                    )
                )

            # Sleep score and efficiency
            score = item.get("score") or item.get("efficiency")
            if isinstance(score, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="SLEEP_SCORE",
                        timestamp=end_dt,
                        value=float(score),
                        unit="SCORE",
                        metadata={**meta, "efficiency": item.get("efficiency")},
                    )
                )

            # Sleep resting or lowest heart rate
            lowest_hr = item.get("lowest_heart_rate")
            if isinstance(lowest_hr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="RESTING_HEART_RATE",
                        timestamp=end_dt,
                        value=float(lowest_hr),
                        unit="count/min",
                        metadata={**meta, "metric": "lowest_sleep_heart_rate"},
                    )
                )

            # Average HRV during sleep (RMSSD)
            avg_hrv = item.get("average_hrv")
            if isinstance(avg_hrv, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE_VARIABILITY",
                        timestamp=end_dt,
                        value=float(avg_hrv),
                        unit="ms",
                        metadata={**meta, "metric": "average_sleep_hrv_rmssd"},
                    )
                )

        return inst, dur

    def _parse_daily_readiness(self, data: Any) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in items:
            if not isinstance(item, dict):
                continue

            day_str = item.get("day")
            if not day_str:
                continue

            try:
                ts = datetime.fromisoformat(f"{day_str}T08:00:00+00:00")
            except Exception:
                ts = datetime.now(timezone.utc)

            score = item.get("score")
            meta = {
                "provider": "oura",
                "temperature_deviation": item.get("temperature_deviation"),
                "temperature_trend_deviation": item.get("temperature_trend_deviation"),
            }

            if isinstance(score, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="RECOVERY_SCORE",
                        timestamp=ts,
                        value=float(score),
                        unit="SCORE",
                        metadata=meta,
                    )
                )

            # Resting heart rate if included
            rhr = item.get("resting_heart_rate")
            if isinstance(rhr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="RESTING_HEART_RATE",
                        timestamp=ts,
                        value=float(rhr),
                        unit="count/min",
                        metadata={"provider": "oura"},
                    )
                )

        return inst

    def _parse_heart_rate(self, data: Any) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in items:
            if not isinstance(item, dict):
                continue

            bpm = item.get("bpm")
            ts_str = item.get("timestamp")
            if bpm is None or not ts_str:
                continue

            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=ts,
                        value=float(bpm),
                        unit="count/min",
                        metadata={"provider": "oura", "source": item.get("source", "awake")},
                    )
                )
            except Exception:
                continue

        return inst

    def _parse_workouts(
        self, data: Any
    ) -> tuple[List[CumulativeMeasurement], List[DurationMeasurement]]:
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in items:
            if not isinstance(item, dict):
                continue

            start_str = item.get("start_datetime")
            end_str = item.get("end_datetime")
            if not (start_str and end_str):
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except Exception:
                continue

            duration_sec = (end_dt - start_dt).total_seconds()
            sport = str(item.get("activity", "WORKOUT")).upper()
            meta = {
                "sport": sport,
                "provider": "oura",
                "intensity": item.get("intensity", "moderate"),
            }

            if duration_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="EXERCISE_TIME",
                        start=start_dt,
                        end=end_dt,
                        duration=duration_sec,
                        unit="s",
                        metadata=meta,
                    )
                )

            # Calories
            cal = item.get("calories")
            if isinstance(cal, (int, float)) and cal > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        start=start_dt,
                        end=end_dt,
                        value=float(cal),
                        unit="kcal",
                        metadata=meta,
                    )
                )

            # Distance
            dist = item.get("distance")
            if isinstance(dist, (int, float)) and dist > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        start=start_dt,
                        end=end_dt,
                        value=float(dist),
                        unit="m",
                        metadata=meta,
                    )
                )

        return cum, dur

    def _parse_spo2(self, data: Any) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in items:
            if not isinstance(item, dict):
                continue

            day_str = item.get("day")
            pct_obj = item.get("spo2_percentage", {})
            avg_spo2 = pct_obj.get("average") if isinstance(pct_obj, dict) else None

            if day_str and isinstance(avg_spo2, (int, float)):
                try:
                    ts = datetime.fromisoformat(f"{day_str}T07:00:00+00:00")
                except Exception:
                    ts = datetime.now(timezone.utc)

                inst.append(
                    InstantaneousMeasurement(
                        type="OXYGEN_SATURATION",
                        timestamp=ts,
                        value=float(avg_spo2),
                        unit="%",
                        metadata={"provider": "oura"},
                    )
                )

        return inst

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        logger.info("Received Oura webhook notification: %s", data)
        return []
