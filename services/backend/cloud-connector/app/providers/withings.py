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


class WithingsProvider(BaseCloudProvider):
    """Withings Health API Cloud Provider -> Supports Withings OAuth 2.0 user authorization, token refresh and telemetry sync:
    - Body Measurements (Smart Scales): Body weight (kg), Body fat (%), Blood pressure (systolic/diastolic),
      Resting heart rate, SpO2 and Body temperature
    - Sleep Tracking (Sleep Analyzer & Sleep Mat & ScanWatch):
      Total sleep duration, sleep stages (Deep, Light, REM, Awake) + Sleep score
    - Activity & Workouts (ScanWatch & Move):
      Step count, active calories burned, distance, exercise duration
    """

    @property
    def provider_name(self) -> str:
        return "withings"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.withings_api_base_url
        self.auth_url = self._settings.withings_auth_url
        self.token_url = self._settings.withings_token_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.withings_client_id.strip()
        client_secret = settings.withings_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET must be set in the environment"
            )
        return client_id, client_secret

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a 64-char code_verifier and S256 code_challenge per (RFC 7636)"""
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
            "user.info",
            "user.metrics",
            "user.activity",
            "user.sleepevents",
        ]
        params = {
            "response_type": "code",
            "client_id": client_id,
            "state": state,
            "scope": ",".join(scopes),
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

        data = {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data)
            if resp.status_code != 200:
                logger.error("Withings token exchange failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Withings token exchange failed (HTTP {resp.status_code}): {resp.text}")

            result = resp.json()
            if result.get("status", 0) != 0:
                error_msg = result.get("error", "Unknown Withings error")
                raise ValueError(f"Withings token exchange returned error status {result.get('status')}: {error_msg}")

            body = result.get("body", {})
            return {
                "access_token": body.get("access_token"),
                "refresh_token": body.get("refresh_token"),
                "expires_in": body.get("expires_in"),
                "token_type": "Bearer",
                "user_id": body.get("userid"),
                "scope": body.get("scope"),
            }

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        data = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=data)
            if resp.status_code != 200:
                logger.error("Withings token refresh failed: HTTP %s - %s", resp.status_code, resp.text)
                raise ValueError(f"Withings token refresh failed (HTTP {resp.status_code}): {resp.text}")

            result = resp.json()
            if result.get("status", 0) != 0:
                error_msg = result.get("error", "Unknown Withings refresh error")
                raise ValueError(f"Withings token refresh returned status {result.get('status')}: {error_msg}")

            body = result.get("body", {})
            return {
                "access_token": body.get("access_token"),
                "refresh_token": body.get("refresh_token"),
                "expires_in": body.get("expires_in"),
                "token_type": "Bearer",
                "user_id": body.get("userid"),
            }

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        return {
            "userId": "withings-user",
            "permissions": ["user.metrics", "user.activity", "user.sleepevents"],
        }

    async def deregister_user(self, access_token: str) -> bool:
        """Revokes Withings user token authorization."""
        client_id, client_secret = self._get_client_credentials()
        url = f"{self.base_url.rstrip('/')}/v2/oauth2"
        data = {
            "action": "revoke",
            "client_id": client_id,
            "client_secret": client_secret,
            "token": access_token,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=data)
                return resp.status_code == 200 and resp.json().get("status") == 0
        except Exception as e:
            logger.warning("Failed to revoke Withings token: %s", e)
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
            inst, cum, dur = self._parse_withings_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
        else:
            headers = {"Authorization": f"Bearer {token}"}
            start_epoch = int(start.timestamp())
            end_epoch = int(end.timestamp())

            async with httpx.AsyncClient(timeout=15.0) as client:
                # Body Measurements (/measure?action=getmeas)
                try:
                    meas_resp = await client.post(
                        f"{self.base_url.rstrip('/')}/measure",
                        data={
                            "action": "getmeas",
                            "startdate": start_epoch,
                            "enddate": end_epoch,
                        },
                        headers=headers,
                    )
                    if meas_resp.status_code == 200:
                        res = meas_resp.json()
                        if res.get("status") == 0:
                            inst = self._parse_measurements(res.get("body", {}))
                            instantaneous_list.extend(inst)
                except Exception as e:
                    logger.warning("Failed to fetch Withings body measurements: %s", e)

                # Sleep Summary (/v2/sleep?action=getsummary)
                try:
                    sleep_resp = await client.post(
                        f"{self.base_url.rstrip('/')}/v2/sleep",
                        data={
                            "action": "getsummary",
                            "startdateymd": start.strftime("%Y-%m-%d"),
                            "enddateymd": end.strftime("%Y-%m-%d"),
                        },
                        headers=headers,
                    )
                    if sleep_resp.status_code == 200:
                        res = sleep_resp.json()
                        if res.get("status") == 0:
                            inst, dur = self._parse_sleep_summary(res.get("body", {}))
                            instantaneous_list.extend(inst)
                            duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Withings sleep summary: %s", e)

                # Daily Activity (/v2/measure?action=getactivity)
                try:
                    act_resp = await client.post(
                        f"{self.base_url.rstrip('/')}/v2/measure",
                        data={
                            "action": "getactivity",
                            "startdateymd": start.strftime("%Y-%m-%d"),
                            "enddateymd": end.strftime("%Y-%m-%d"),
                        },
                        headers=headers,
                    )
                    if act_resp.status_code == 200:
                        res = act_resp.json()
                        if res.get("status") == 0:
                            inst, cum, dur = self._parse_activities(res.get("body", {}))
                            instantaneous_list.extend(inst)
                            cumulative_list.extend(cum)
                            duration_list.extend(dur)
                except Exception as e:
                    logger.warning("Failed to fetch Withings daily activity: %s", e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Withings",
                deviceId="cloud-connector:withings",
                authorizationToken="cloud-connector-withings",
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
            sourceName="Withings Health Cloud API",
            sourcePlatform="withings",
            sourceId="withings-cloud",
            participantId=patient_id,
            timestamp=now,
        )

    def _parse_withings_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        if "measuregrps" in bundle or "measure" in bundle:
            body_data = bundle.get("measure") or bundle
            inst.extend(self._parse_measurements(body_data))

        if "series" in bundle or "sleep" in bundle:
            sleep_data = bundle.get("sleep") or bundle
            s_inst, s_dur = self._parse_sleep_summary(sleep_data)
            inst.extend(s_inst)
            dur.extend(s_dur)

        if "activities" in bundle or "activity" in bundle:
            act_data = bundle.get("activity") or bundle
            a_inst, a_cum, a_dur = self._parse_activities(act_data)
            inst.extend(a_inst)
            cum.extend(a_cum)
            dur.extend(a_dur)

        return inst, cum, dur

    def _parse_measurements(self, data: Dict[str, Any]) -> List[InstantaneousMeasurement]:
        """Parses Withings /measure?action=getmeas groups
        Measure types:
        1: Weight (kg)
        6: Fat Ratio (%)
        9: Diastolic blood pressure (mmHg)
        10: Systolic blood pressure (mmHg)
        11: Heart Rate (bpm)
        54: SpO2 (%)
        71: Body Temperature (°C)
        73: Skin Temperature (°C)
        """
        inst: List[InstantaneousMeasurement] = []
        groups = data.get("measuregrps", [])

        # Mapping of Withings measure types
        type_mapping = {
            1: ("BODY_MASS", "kg"),
            6: ("BODY_FAT_PERCENTAGE", "%"),
            9: ("BLOOD_PRESSURE_DIASTOLIC", "mmHg"),
            10: ("BLOOD_PRESSURE_SYSTOLIC", "mmHg"),
            11: ("RESTING_HEART_RATE", "count/min"),
            54: ("OXYGEN_SATURATION", "%"),
            71: ("BODY_TEMPERATURE", "degC"),
            73: ("SKIN_TEMPERATURE", "degC"),
        }

        for grp in groups:
            if not isinstance(grp, dict):
                continue

            epoch = grp.get("date")
            if not epoch:
                continue
            ts = datetime.fromtimestamp(epoch, tz=timezone.utc)
            grp_id = str(grp.get("grpid", ""))
            category = grp.get("category", 1)  # 1 = real measurement, 2 = user goal

            if category != 1:
                continue

            measures = grp.get("measures", [])
            for m in measures:
                m_type = m.get("type")
                raw_val = m.get("value")
                unit_exp = m.get("unit", 0)

                if m_type not in type_mapping or not isinstance(raw_val, (int, float)):
                    continue

                real_value = float(raw_val) * (10 ** unit_exp)
                metric_name, unit_str = type_mapping[m_type]

                inst.append(
                    InstantaneousMeasurement(
                        type=metric_name,
                        timestamp=ts,
                        value=round(real_value, 2),
                        unit=unit_str,
                        metadata={
                            "provider": "withings",
                            "grpid": grp_id,
                            "withings_type": m_type,
                        },
                    )
                )

        return inst

    def _parse_sleep_summary(
        self, data: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[DurationMeasurement]]:
        """Parses Withings sleep summaries (/v2/sleep?action=getsummary)"""
        inst: List[InstantaneousMeasurement] = []
        dur: List[DurationMeasurement] = []

        series = data.get("series", [])
        for item in series:
            if not isinstance(item, dict):
                continue

            start_epoch = item.get("startdate")
            end_epoch = item.get("enddate")
            if not (start_epoch and end_epoch):
                continue

            start_dt = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
            data_obj = item.get("data", {})

            meta = {
                "provider": "withings",
                "id": str(item.get("id", "")),
                "model": str(item.get("model", "")),
            }

            # Total sleep duration
            total_sleep_sec = data_obj.get("total_sleep_time")
            if isinstance(total_sleep_sec, (int, float)) and total_sleep_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP",
                        value=round(float(float(total_sleep_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(total_sleep_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Deep sleep duration
            deep_sec = data_obj.get("deepsleepduration")
            if isinstance(deep_sec, (int, float)) and deep_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_DEEP",
                        value=round(float(float(deep_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(deep_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            #  Light sleep duration
            light_sec = data_obj.get("lightsleepduration")
            if isinstance(light_sec, (int, float)) and light_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_LIGHT",
                        value=round(float(float(light_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(light_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # REM sleep duration
            rem_sec = data_obj.get("remsleepduration")
            if isinstance(rem_sec, (int, float)) and rem_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_REM",
                        value=round(float(float(rem_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(rem_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Wake up duration
            wake_sec = data_obj.get("wakeupduration")
            if isinstance(wake_sec, (int, float)) and wake_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="SLEEP_AWAKE",
                        value=round(float(float(wake_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=start_dt,
                        endTime=end_dt,
                        durationMinutes=round(float(float(wake_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Sleep score (0-100)
            sleep_score = data_obj.get("sleep_score")
            if isinstance(sleep_score, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="SLEEP_SCORE",
                        timestamp=end_dt,
                        value=float(sleep_score),
                        unit="SCORE",
                        metadata=meta,
                    )
                )

            # Average heart rate during sleep
            avg_hr = data_obj.get("hr_average")
            if isinstance(avg_hr, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=end_dt,
                        value=float(avg_hr),
                        unit="count/min",
                        metadata={**meta, "metric": "sleep_hr_average"},
                    )
                )

        return inst, dur

    def _parse_activities(
        self, data: Dict[str, Any]
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement]]:
        """Parses Withings daily activity records (/v2/measure?action=getactivity)"""
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []

        activities = data.get("activities", [])
        for act in activities:
            if not isinstance(act, dict):
                continue

            date_str = act.get("date")
            if not date_str:
                continue

            try:
                day_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                day_end = day_start + timedelta(days=1)
            except Exception:
                continue

            meta = {"provider": "withings", "date": date_str}

            # Steps
            steps = act.get("steps")
            if isinstance(steps, (int, float)) and steps > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="STEP_COUNT",
                        value=float(steps),
                        unit="count",
                        periodStart=day_start,
                        periodEnd=day_end,
                        duration=max(0, int((day_end - day_start).total_seconds())),
                        metadata=meta,
                    )
                )

            # Distance in meters
            dist = act.get("distance")
            if isinstance(dist, (int, float)) and dist > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        value=float(dist),
                        unit="m",
                        periodStart=day_start,
                        periodEnd=day_end,
                        duration=max(0, int((day_end - day_start).total_seconds())),
                        metadata=meta,
                    )
                )

            # Calories
            cals = act.get("calories")
            if isinstance(cals, (int, float)) and cals > 0:
                cum.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        value=float(cals),
                        unit="kcal",
                        periodStart=day_start,
                        periodEnd=day_end,
                        duration=max(0, int((day_end - day_start).total_seconds())),
                        metadata=meta,
                    )
                )

            # Active time in seconds
            active_sec = act.get("active")
            if isinstance(active_sec, (int, float)) and active_sec > 0:
                dur.append(
                    DurationMeasurement(
                        type="EXERCISE_TIME",
                        value=round(float(float(active_sec)) / 60.0, 2),
                        unit="MINUTE",
                        startTime=day_start,
                        endTime=day_end,
                        durationMinutes=round(float(float(active_sec)) / 60.0, 2),
                        metadata=meta,
                    )
                )

            # Daily average heart rate
            hr_avg = act.get("hr_average")
            if isinstance(hr_avg, (int, float)):
                inst.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        timestamp=day_end,
                        value=float(hr_avg),
                        unit="count/min",
                        metadata={**meta, "metric": "daily_hr_average"},
                    )
                )

        return inst, cum, dur

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        logger.info("Received Withings webhook payload: %s", data)
        return []
