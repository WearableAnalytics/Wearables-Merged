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


class GoogleHealthProvider(BaseCloudProvider):
    """Google Health API:
    Supports unified Google Health API on Google Cloud. Telemetry from Fitbit (Charge, Inspire, Sense) and Google Pixel Watches with Google OAuth 2.0 PKCE:
    - Sleep stages (Light, Deep, REM, Awake) & Sleep Score
    - 24/7 Heart Rate & Resting Heart Rate
    - Activities & Workouts (Duration, Distance, Calories, Workout HR)
    - Blood Oxygen/SpO2 and Respiratory Rate
    """

    @property
    def provider_name(self) -> str:
        return "google_health"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.google_health_api_base_url
        self.auth_url = self._settings.google_health_auth_url
        self.token_url = self._settings.google_health_token_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.google_health_client_id.strip()
        client_secret = settings.google_health_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "GOOGLE_HEALTH_CLIENT_ID and GOOGLE_HEALTH_CLIENT_SECRET must be set in the environment"
            )
        return client_id, client_secret

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a 64-char code_verifier and S256 code_challenge per Google OAuth RFC 7636"""
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
            "openid",
            "email",
            "https://www.googleapis.com/auth/fitness.activity.read",
            "https://www.googleapis.com/auth/fitness.heart_rate.read",
            "https://www.googleapis.com/auth/fitness.sleep.read",
            "https://www.googleapis.com/auth/fitness.oxygen_saturation.read",
        ]
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "redirect_uri": effective_redirect,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
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

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data)
            if resp.status_code != 200:
                logger.error("Google Health token exchange failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Google Health token exchange failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data)
            if resp.status_code != 200:
                logger.error("Google Health token refresh failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Google Health token refresh failed (HTTP {resp.status_code}): {resp.text}")
            return resp.json()

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    info = resp.json()
                    return {
                        "userId": str(info.get("sub", "google-health-user")),
                        "email": info.get("email", ""),
                        "permissions": ["fitness.activity.read", "fitness.heart_rate.read", "fitness.sleep.read"],
                    }
        except Exception as e:
            logger.warning("Failed to fetch Google Health user info: %s", e)

        return {"userId": "google-health-user", "permissions": ["fitness.read"]}

    async def deregister_user(self, access_token: str) -> bool:
        """Revokes the user's Google OAuth 2.0 token."""
        url = "https://oauth2.googleapis.com/revoke"
        data = {"token": access_token}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("Failed to revoke Google Health token: %s", e)
            return False

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        token = credentials.get("token") or credentials.get("access_token")
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

        token = credentials.get("token") or credentials.get("access_token", "")
        mock_data = credentials.get("mock_data")

        instantaneous_list: List[InstantaneousMeasurement] = []
        cumulative_list: List[CumulativeMeasurement] = []
        duration_list: List[DurationMeasurement] = []
        waveform_list: List[WaveformMeasurement] = []

        if mock_data:
            inst, cum, dur = self._parse_google_health_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
        else:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            start_ns = int(start.timestamp() * 1e9)
            end_ns = int(end.timestamp() * 1e9)

            # Google Health & Fitness dataset query
            dataset_range = f"{start_ns}-{end_ns}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Sleep sessions and stages
                try:
                    sleep_url = f"{self.base_url.rstrip('/')}/users/me/sessions?startTime={start.isoformat()}&endTime={end.isoformat()}&activityType=72"
                    sleep_resp = await client.get(sleep_url, headers=headers)
                    if sleep_resp.status_code == 200:
                        inst, dur = self._parse_sleep(sleep_resp.json())
                        instantaneous_list.extend(inst)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Google Health sleep: %s", e)

                # Heart Rate (continuous/derived)
                try:
                    hr_ds = "derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm"
                    hr_url = f"{self.base_url.rstrip('/')}/users/me/dataSources/{hr_ds}/datasets/{dataset_range}"
                    hr_resp = await client.get(hr_url, headers=headers)
                    if hr_resp.status_code == 200:
                        inst = self._parse_heart_rate(hr_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Google Health heart rate: %s", e)

                #  Activities & Workouts
                try:
                    act_url = f"{self.base_url.rstrip('/')}/users/me/sessions?startTime={start.isoformat()}&endTime={end.isoformat()}"
                    act_resp = await client.get(act_url, headers=headers)
                    if act_resp.status_code == 200:
                        inst, cum, dur = self._parse_activities(act_resp.json())
                        instantaneous_list.extend(inst)
                        cumulative_list.extend(cum)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Google Health activities: %s", e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Fitbit",
                deviceId="cloud-connector:google-health",
                authorizationToken="cloud-connector-google-health",
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
            sourceName="Google Health API (Fitbit & Pixel Watch)",
            sourcePlatform="google-health",
            sourceId="google-health-cloud",
            participantId=patient_id,
            timestamp=now,
        )

    def _parse_google_health_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        if "sleep" in bundle:
            s_inst, s_dur = self._parse_sleep(bundle["sleep"])
            inst.extend(s_inst)
            dur.extend(s_dur)

        if "heart_rate" in bundle:
            inst.extend(self._parse_heart_rate(bundle["heart_rate"]))

        if "activities" in bundle:
            a_inst, a_cum, a_dur = self._parse_activities(bundle["activities"])
            inst.extend(a_inst)
            cum.extend(a_cum)
            dur.extend(a_dur)

        return inst, cum, dur

    def _parse_sleep(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        dur: List[DurationMeasurement] = []

        sessions = data.get("session", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        # Google Health sleep stage codes:
        # 1: Awake, 2: Sleep, 3: Out of bed, 4: Light sleep, 5: Deep sleep, 6: REM sleep
        stage_map = {
            1: "SLEEP_AWAKE",
            2: "SLEEP",
            3: "SLEEP_AWAKE",
            4: "SLEEP_LIGHT",
            5: "SLEEP_DEEP",
            6: "SLEEP_REM",
        }

        for session in sessions:
            if not isinstance(session, dict):
                continue

            start_ms = session.get("startTimeMillis")
            end_ms = session.get("endTimeMillis")
            if not (start_ms and end_ms):
                continue

            try:
                start_dt = datetime.fromtimestamp(float(start_ms) / 1000.0, tz=timezone.utc)
                end_dt = datetime.fromtimestamp(float(end_ms) / 1000.0, tz=timezone.utc)
            except Exception:
                continue

            duration_sec = (end_dt - start_dt).total_seconds()
            meta = {
                "provider": "google_health",
                "source": "fitbit-pixelwatch",
                "sessionId": session.get("id", ""),
            }

            dur.append(
                DurationMeasurement(
                    type="SLEEP",
                    value=float(duration_sec) / 60.0,
                    unit="MINUTE",
                    startTime=start_dt,
                    endTime=end_dt,
                    durationMinutes=float(duration_sec) / 60.0,
                    metadata=meta,
                )
            )

            # Sleep score and quality
            score = session.get("sleepScore") or session.get("efficiency")
            if isinstance(score, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="SLEEP_SCORE",
                        timestamp=end_dt,
                        value=float(score),
                        unit="SCORE",
                        metadata=meta,
                    )
                )

            # Stages breakdown
            stages = session.get("stages", [])
            for stage in stages:
                s_type = stage.get("stage")
                s_duration = stage.get("durationSeconds")
                if s_type in stage_map and isinstance(s_duration, (int, float)) and s_duration > 0:
                    dur.append(
                        DurationMeasurement(
                            type=stage_map[s_type],
                            value=round(float(float(s_duration)) / 60.0, 2),
                            unit="MINUTE",
                            startTime=start_dt,
                            endTime=end_dt,
                            durationMinutes=round(float(float(s_duration)) / 60.0, 2),
                            metadata=meta,
                        )
                    )

        return inst, dur

    def _parse_heart_rate(self, data: Dict[str, Any]) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        points = data.get("point", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for pt in points:
            if not isinstance(pt, dict):
                continue

            end_ns = pt.get("endTimeNanos")
            val_list = pt.get("value", [])
            if not (end_ns and val_list and isinstance(val_list, list)):
                continue

            hr_val = val_list[0].get("fpVal") or val_list[0].get("intVal")
            if hr_val is None:
                continue

            try:
                ts = datetime.fromtimestamp(float(end_ns) / 1e9, tz=timezone.utc)
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=ts,
                        value=float(hr_val),
                        unit="count/min",
                        metadata={"provider": "google_health", "source": "fitbit-pixelwatch"},
                    )
                )
            except Exception:
                continue

        return inst

    def _parse_activities(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        sessions = data.get("session", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for session in sessions:
            if not isinstance(session, dict):
                continue

            # Skip sleep sessions
            if session.get("activityType") == 72:
                continue

            start_ms = session.get("startTimeMillis")
            end_ms = session.get("endTimeMillis")
            if not (start_ms and end_ms):
                continue

            try:
                start_dt = datetime.fromtimestamp(float(start_ms) / 1000.0, tz=timezone.utc)
                end_dt = datetime.fromtimestamp(float(end_ms) / 1000.0, tz=timezone.utc)
            except Exception:
                continue

            duration_sec = (end_dt - start_dt).total_seconds()
            sport = str(session.get("name", "WORKOUT")).upper()
            meta = {
                "sport": sport,
                "provider": "google_health",
                "sessionId": session.get("id", ""),
            }

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

            # Calories
            calories = session.get("calories")
            if isinstance(calories, (int, float)) and calories > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        value=float(calories),
                        unit="kcal",
                        periodStart=start_dt,
                        periodEnd=end_dt,
                        duration=max(0, int((end_dt - start_dt).total_seconds())),
                        metadata=meta,
                    )
                )

            # Distance
            distance = session.get("distanceMeters")
            if isinstance(distance, (int, float)) and distance > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        value=float(distance),
                        unit="m",
                        periodStart=start_dt,
                        periodEnd=end_dt,
                        duration=max(0, int((end_dt - start_dt).total_seconds())),
                        metadata=meta,
                    )
                )

            # Average HR
            avg_hr = session.get("averageHeartRate")
            if isinstance(avg_hr, (int, float)) and avg_hr > 0:
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=end_dt,
                        value=float(avg_hr),
                        unit="count/min",
                        metadata={**meta, "metric": "average_heart_rate"},
                    )
                )

        return inst, cum, dur

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        logger.info("Received Google Health Cloud Pub/Sub webhook notification: %s", data)
        return []
