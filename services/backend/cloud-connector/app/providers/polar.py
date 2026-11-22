import base64
import logging
import re
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


class PolarProvider(BaseCloudProvider):
    """Polar AccessLink Cloud Provider
    Supports Polar OAuth 2.0 user authorization, mandatory AccessLink user registration (POST /v3/users), webhook ping processing and telemetry sync (sleep, continuous HR, exercises)
    """

    @property
    def provider_name(self) -> str:
        return "polar"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.polar_api_base_url
        self.auth_url = self._settings.polar_auth_url
        self.token_url = self._settings.polar_token_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.polar_client_id.strip()
        client_secret = settings.polar_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "POLAR_CLIENT_ID and POLAR_CLIENT_SECRET must be set in the environment"
            )
        return client_id, client_secret

    def _build_basic_auth_header(self, client_id: str, client_secret: str) -> str:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Polar AccessLink uses standard OAuth 2.0. Return random state for compatibility"""
        verifier = secrets.token_urlsafe(32)
        return verifier, verifier

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None,
    ) -> str:
        client_id, _ = self._get_client_credentials()
        effective_redirect = redirect_uri or get_settings().oauth_redirect_uri
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": "accesslink.read_all",
            "state": state,
            "redirect_uri": effective_redirect,
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
            "Accept": "application/json",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data, headers=headers)
            if resp.status_code != 200:
                logger.error(
                    "Polar token exchange failed: HTTP %s - %s",
                    resp.status_code,
                    resp.text,
                )
                raise ValueError(f"Polar token exchange failed (HTTP {resp.status_code}): {resp.text}")

            token_payload = resp.json()

            # Polar requirement
            access_token = token_payload.get("access_token")
            x_user_id = token_payload.get("x_user_id")
            if access_token:
                await self._register_user(access_token)

            return token_payload

    async def _register_user(self, access_token: str) -> None:
        """Mandatory Polar AccessLink registration (POST /v3/users)

        Polar requires calling POST /v3/users after OAuth token grant -> If already registered, Polar returns 409 Conflict, which is  accepted
        """
        reg_url = f"{self.base_url.rstrip('/')}/users"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                reg_resp = await client.post(reg_url, json={}, headers=headers)
                if reg_resp.status_code in (200, 201):
                    logger.info("Polar AccessLink user successfully registered")
                elif reg_resp.status_code == 409:
                    logger.info("Polar AccessLink user is already registered (HTTP 409 Conflict)")
                else:
                    logger.warning(
                        "Polar AccessLink user registration returned HTTP %s: %s",
                        reg_resp.status_code,
                        reg_resp.text,
                    )
        except Exception as e:
            logger.warning("Failed to register user at Polar AccessLink: %s", e)

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetches basic user info from Polar AccessLink"""
        url = f"{self.base_url.rstrip('/')}/users"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    user_id = str(data.get("polar-user-id", ""))
                    return {
                        "userId": user_id,
                        "permissions": ["accesslink.read_all"],
                        "memberId": data.get("member-id"),
                    }
        except Exception as e:
            logger.warning("Could not fetch Polar user info via GET /users: %s", e)

        return {"userId": "polar-user", "permissions": ["accesslink.read_all"]}

    async def deregister_user(self, access_token: str) -> bool:
        """Deregisters a user at Polar AccessLink (DELETE /v3/users/{user-id})"""
        user_info = await self.fetch_user_info(access_token)
        user_id = user_info.get("userId")
        if not user_id or user_id == "polar-user":
            return True

        url = f"{self.base_url.rstrip('/')}/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(url, headers=headers)
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning("Failed to deregister user at Polar AccessLink: %s", e)
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
            inst, cum, dur, wav = self._parse_polar_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
            waveform_list.extend(wav)
        else:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Sleep data
                try:
                    sleep_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/users/sleep",
                        headers=headers,
                    )
                    if sleep_resp.status_code == 200:
                        inst, dur = self._parse_sleep(sleep_resp.json())
                        instantaneous_list.extend(inst)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Polar sleep: %s", e)

                # Continuous Heart Rate for current date
                try:
                    date_str = start.strftime("%Y-%m-%d")
                    chr_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/users/continuous-heart-rate/{date_str}",
                        headers=headers,
                    )
                    if chr_resp.status_code == 200:
                        inst = self._parse_continuous_hr(chr_resp.json())
                        instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Polar continuous heart rate: %s", e)

                # Exercises/Training Sessions
                try:
                    exercises_resp = await client.get(
                        f"{self.base_url.rstrip('/')}/exercises",
                        headers=headers,
                    )
                    if exercises_resp.status_code == 200:
                        inst, cum, dur = self._parse_exercises(exercises_resp.json())
                        instantaneous_list.extend(inst)
                        cumulative_list.extend(cum)
                        duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Polar exercises: %s", e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Polar",
                deviceId="cloud-connector:polar",
                authorizationToken="cloud-connector-polar",
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
            sourceName="Polar Flow Cloud",
            sourcePlatform="polar-flow",
            sourceId="polar-accesslink",
            participantId=patient_id,
            timestamp=now,
        )

    def _parse_polar_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[
        List[InstantaneousMeasurement],
        List[CumulativeMeasurement],
        List[DurationMeasurement],
        List[WaveformMeasurement],
    ]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []
        wav: List[WaveformMeasurement] = []

        if "sleep" in bundle:
            s_inst, s_dur = self._parse_sleep(bundle["sleep"])
            inst.extend(s_inst)
            dur.extend(s_dur)

        if "continuous_heart_rate" in bundle:
            inst.extend(self._parse_continuous_hr(bundle["continuous_heart_rate"]))

        if "exercises" in bundle:
            e_inst, e_cum, e_dur = self._parse_exercises(bundle["exercises"])
            inst.extend(e_inst)
            cum.extend(e_cum)
            dur.extend(e_dur)

        return inst, cum, dur, wav

    def _parse_sleep(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        dur: List[DurationMeasurement] = []

        nights = data.get("nights", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for night in nights:
            if not isinstance(night, dict):
                continue

            start_str = night.get("sleep_start_time")
            end_str = night.get("sleep_end_time")
            if not (start_str and end_str):
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except Exception:
                continue

            total_seconds = (end_dt - start_dt).total_seconds()
            device_id = night.get("device_id")
            meta = {"provider": "polar", "device_id": device_id} if device_id else {"provider": "polar"}

            dur.append(
                DurationMeasurement(
                    type="SLEEP",
                    value=float(total_seconds) / 60.0,
                    unit="MINUTE",
                    startTime=start_dt,
                    endTime=end_dt,
                    durationMinutes=float(total_seconds) / 60.0,
                    metadata=meta,
                )
            )

            # Sleep stages
            light_sleep = night.get("light_sleep")
            if isinstance(light_sleep, (int, float)) and light_sleep > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_LIGHT",
                        value=round(float(float(light_sleep)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(light_sleep)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            deep_sleep = night.get("deep_sleep")
            if isinstance(deep_sleep, (int, float)) and deep_sleep > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_DEEP",
                        value=round(float(float(deep_sleep)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(deep_sleep)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            rem_sleep = night.get("rem_sleep")
            if isinstance(rem_sleep, (int, float)) and rem_sleep > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_REM",
                        value=round(float(float(rem_sleep)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(rem_sleep)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            interruptions = night.get("total_interruption_duration")
            if isinstance(interruptions, (int, float)) and interruptions > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_AWAKE",
                        value=round(float(float(interruptions)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(interruptions)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Sleep score
            sleep_score = night.get("sleep_score")
            if isinstance(sleep_score, (int, float)):
                score_meta = {"provider": "polar"}
                if "continuity" in night:
                    score_meta["continuity"] = str(night["continuity"])
                if "continuity_class" in night:
                    score_meta["continuity_class"] = str(night["continuity_class"])

                inst.append(
                    InstantaneousMeasurement(
                        type="SLEEP_SCORE",
                        timestamp=end_dt,
                        value=float(sleep_score),
                        unit="SCORE",
                        metadata=score_meta,
                    )
                )

        return inst, dur

    def _parse_continuous_hr(self, data: Any) -> List[InstantaneousMeasurement]:
        inst: List[InstantaneousMeasurement] = []
        samples = data.get("heart_rate_samples", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for sample in samples:
            if not isinstance(sample, dict):
                continue
            hr = sample.get("heart_rate")
            sample_time_str = sample.get("sample_time")
            if hr is None or not sample_time_str:
                continue

            try:
                sample_dt = datetime.fromisoformat(sample_time_str.replace("Z", "+00:00"))
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=sample_dt,
                        value=float(hr),
                        unit="count/min",
                        metadata={"provider": "polar", "source": "continuous_heart_rate"},
                    )
                )
            except Exception:
                continue

        return inst

    def _parse_exercises(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        exercises = data if isinstance(data, list) else data.get("exercises", [])

        for ex in exercises:
            if not isinstance(ex, dict):
                continue

            start_str = ex.get("start_time")
            if not start_str:
                continue

            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except Exception:
                continue

            # Duration can be ISO 8601 (e.g. PT43M18S, PT3600S) or seconds integer/float
            duration_val = ex.get("duration", 0)
            duration_sec = 0.0
            if isinstance(duration_val, (int, float)):
                duration_sec = float(duration_val)
            elif isinstance(duration_val, str):
                match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", duration_val.strip())
                if match:
                    h, m, s = match.groups()
                    duration_sec = float(h or 0) * 3600 + float(m or 0) * 60 + float(s or 0)
                else:
                    try:
                        duration_sec = float(duration_val.replace("PT", "").replace("S", ""))
                    except ValueError:
                        duration_sec = 0.0

            end_dt = start_dt + timedelta(seconds=duration_sec) if duration_sec > 0 else start_dt
            sport = str(ex.get("sport", "WORKOUT")).upper()
            device = ex.get("device")
            meta = {"sport": sport, "provider": "polar"}
            if device:
                meta["device"] = str(device)
            if "id" in ex:
                meta["exercise_id"] = str(ex["id"])

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

            # Distance
            distance = ex.get("distance")
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

            # Calories
            calories = ex.get("calories") or ex.get("kiloCalories")
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

            # Heart rate average & max
            hr_info = ex.get("heart_rate")
            if isinstance(hr_info, dict):
                avg_hr = hr_info.get("average")
                max_hr = hr_info.get("maximum")
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
        """Parses Polar webhook notification ping

        Polar webhook alerts follow the structure:
        {"event": "EXERCISE"|"SLEEP"|"CONTINUOUS_HEART_RATE", "user_id": 12345, "entity_id": "...", ...}
        """
        logger.info("Received Polar webhook payload: %s", data)
        return []
