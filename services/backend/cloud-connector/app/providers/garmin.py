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


class GarminProvider(BaseCloudProvider):
    """Garmin Health Cloud Provider
    Supports Garmin OAuth 2.0 PKCE user linking, PUSH webhook ingestion, and REST telemetry sync.
    """

    @property
    def provider_name(self) -> str:
        return "garmin"

    def __init__(self, base_url: Optional[str] = None):
        self._settings = get_settings()
        self.base_url = base_url or self._settings.garmin_api_base_url
        self.auth_url = self._settings.garmin_auth_url
        self.token_url = self._settings.garmin_token_url
        self.partner_gateway_url = self._settings.garmin_partner_gateway_url

    def _get_client_credentials(self) -> tuple[str, str]:
        settings = get_settings()
        client_id = settings.garmin_client_id.strip()
        client_secret = settings.garmin_client_secret.strip()
        if not client_id or not client_secret:
            raise ValueError(
                "GARMIN_CLIENT_ID and GARMIN_CLIENT_SECRET must be set in the environment (.env)"
            )
        return client_id, client_secret

    def _build_basic_auth_header(self, client_id: str, client_secret: str) -> str:
        raw = f"{client_id}:{client_secret}".encode("utf-8")
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generates a 64-char code_verifier and S256 code_challenge per Garmin OAuth2 PKCE spec"""
        code_verifier = secrets.token_urlsafe(48)  # 64 URL-safe characters (within 43..128 range)
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
        params = {
            "client_id": client_id,
            "response_type": "code",
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
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": effective_redirect,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, headers=headers, data=data)
            if resp.status_code != 200:
                logger.error("Garmin token exchange failed (%s): %s", resp.status_code, resp.text)
                raise ValueError(f"Garmin token exchange failed ({resp.status_code}): {resp.text}")
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        client_id, client_secret = self._get_client_credentials()
        headers = {
            "Authorization": self._build_basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, headers=headers, data=data)
            if resp.status_code != 200:
                logger.error("Garmin token refresh failed (%s): %s", resp.status_code, resp.text)
                raise ValueError(f"Garmin token refresh failed ({resp.status_code}): {resp.text}")
            return resp.json()

    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        user_id = ""
        permissions: List[str] = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            id_resp = await client.get(f"{self.partner_gateway_url}/user/id", headers=headers)
            if id_resp.status_code == 200:
                user_id = id_resp.json().get("userId", "")
            else:
                logger.warning("Failed to fetch Garmin userId (%s): %s", id_resp.status_code, id_resp.text)

            perm_resp = await client.get(
                f"{self.partner_gateway_url}/user/permissions", headers=headers
            )
            if perm_resp.status_code == 200:
                perm_data = perm_resp.json()
                if isinstance(perm_data, dict):
                    permissions = perm_data.get("permissions", [])
                elif isinstance(perm_data, list):
                    permissions = perm_data

        return {
            "provider_user_id": user_id,
            "permissions": permissions,
        }

    async def deregister_user(self, access_token: str) -> bool:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"{self.partner_gateway_url}/user/registration", headers=headers
            )
            return resp.status_code in (200, 204)

    def parse_webhook_payload(
        self,
        data: Dict[str, Any],
        resolve_patient_id: Callable[[str], Optional[str]],
        default_patient_id: Optional[str] = None,
    ) -> List[IngestPayload]:
        """Groups incoming Garmin PUSH webhook arrays by Garmin userId and builds normalized IngestPayloads"""
        summary_keys = [
            "pulseOx",
            "respiration",
            "allDayRespiration",
            "hrv",
            "hrvSummary",
            "hrvSummaries",
            "dailies",
            "epochs",
            "sleeps",
            "stressDetails",
            "bodyComps",
            "bloodPressures",
            "skinTemp",
            "userMetrics",
            "ecg",
        ]

        # Group items by resolved patient_id
        bundles_by_patient: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for key in summary_keys:
            if key not in data:
                continue
            raw_items = data[key]
            items = raw_items if isinstance(raw_items, list) else [raw_items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                garmin_user_id = item.get("userId") or item.get("userAccessToken")
                patient_id = (
                    resolve_patient_id(str(garmin_user_id)) if garmin_user_id else None
                ) or default_patient_id
                if not patient_id:
                    logger.warning(
                        "Skipping Garmin webhook item in '%s': unlinked Garmin userId='%s'",
                        key,
                        garmin_user_id,
                    )
                    continue
                patient_bundle = bundles_by_patient.setdefault(patient_id, {})
                patient_bundle.setdefault(key, []).append(item)

        now = datetime.now(timezone.utc)
        payloads: List[IngestPayload] = []
        for patient_id, patient_bundle in bundles_by_patient.items():
            inst, cum, dur, wav, steps = self._parse_garmin_bundle(patient_bundle)
            if not (inst or cum or dur or wav):
                continue
            payloads.append(
                IngestPayload(
                    deviceInfo=DeviceInfo(
                        platform="Garmin",
                        deviceId=patient_id,
                        authorizationToken="cloud-connector-garmin",
                    ),
                    batchInfo=BatchInfo(
                        collectionStart=now - timedelta(days=1),
                        collectionEnd=now,
                        lastSendTime=now,
                    ),
                    measurements=Measurements(
                        instantaneous=inst,
                        cumulative=cum,
                        duration=dur,
                        waveforms=wav,
                    ),
                    sourceName="Garmin Health Cloud",
                    sourcePlatform="Garmin Connect",
                    totalStepsToday=steps if steps > 0 else None,
                    timestamp=now,
                )
            )
        return payloads

    async def validate_credentials(self, credentials: Dict[str, Any]) -> bool:
        token = credentials.get("token") or credentials.get("personal_token")
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

        token = credentials.get("token") or credentials.get("personal_token", "")
        mock_data = credentials.get("mock_data")

        instantaneous_list: List[InstantaneousMeasurement] = []
        cumulative_list: List[CumulativeMeasurement] = []
        duration_list: List[DurationMeasurement] = []
        waveform_list: List[WaveformMeasurement] = []
        total_steps = 0

        if mock_data:
            inst, cum, dur, wav, steps = self._parse_garmin_bundle(mock_data)
            instantaneous_list.extend(inst)
            cumulative_list.extend(cum)
            duration_list.extend(dur)
            waveform_list.extend(wav)
            total_steps = steps
        else:
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "uploadStartTimeInSeconds": int(start.timestamp()),
                "uploadEndTimeInSeconds": int(end.timestamp()),
            }

            endpoints = [
                ("pulseOx", self._handle_pulse_ox),
                ("respiration", self._handle_respiration),
                ("hrv", self._handle_hrv),
                ("dailies", self._handle_dailies),
                ("epochs", self._handle_epochs),
                ("sleeps", self._handle_sleeps),
                ("stressDetails", self._handle_stress),
                ("bodyComps", self._handle_body_comps),
                ("bloodPressures", self._handle_blood_pressures),
                ("skinTemp", self._handle_skin_temp),
                ("userMetrics", self._handle_user_metrics),
                ("ecg", self._handle_ecg),
            ]

            async with httpx.AsyncClient(timeout=15.0) as client:
                for path, handler in endpoints:
                    try:
                        resp = await client.get(
                            f"{self.base_url}/{path}",
                            headers=headers,
                            params=params,
                        )
                        if resp.status_code == 200:
                            step_val = handler(
                                resp.json(),
                                instantaneous_list,
                                cumulative_list,
                                duration_list,
                                waveform_list,
                            )
                            if step_val and step_val > total_steps:
                                total_steps = step_val
                    except Exception as e:
                        logger.warning("Failed to fetch Garmin endpoint /%s: %s", path, e)

        return IngestPayload(
            deviceInfo=DeviceInfo(
                platform="Garmin",
                deviceId=patient_id,
                authorizationToken="cloud-connector-garmin",
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
            sourceName="Garmin Health Cloud",
            sourcePlatform="Garmin Connect",
            totalStepsToday=total_steps if total_steps > 0 else None,
            timestamp=now,
        )

    def _handle_pulse_ox(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_pulse_ox(data))
        return 0

    def _handle_respiration(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_respiration(data))
        return 0

    def _handle_hrv(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_hrv(data))
        return 0

    def _handle_dailies(self, data, inst, cum, dur, wav) -> int:
        i, c, d, steps = self._parse_dailies(data)
        inst.extend(i)
        cum.extend(c)
        dur.extend(d)
        return steps

    def _handle_epochs(self, data, inst, cum, dur, wav) -> int:
        i, c = self._parse_epochs(data)
        inst.extend(i)
        cum.extend(c)
        return 0

    def _handle_sleeps(self, data, inst, cum, dur, wav) -> int:
        dur.extend(self._parse_sleeps(data))
        return 0

    def _handle_stress(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_stress(data))
        return 0

    def _handle_body_comps(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_body_comps(data))
        return 0

    def _handle_blood_pressures(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_blood_pressures(data))
        return 0

    def _handle_skin_temp(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_skin_temp(data))
        return 0

    def _handle_user_metrics(self, data, inst, cum, dur, wav) -> int:
        inst.extend(self._parse_user_metrics(data))
        return 0

    def _handle_ecg(self, data, inst, cum, dur, wav) -> int:
        i, w = self._parse_ecg(data)
        inst.extend(i)
        wav.extend(w)
        return 0

    def _parse_pulse_ox(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            time_offsets = item.get("timeOffsetSpo2Values") or {}
            for offset_str, val in time_offsets.items():
                if val is not None and val > 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="BLOOD_OXYGEN",
                            value=float(val),
                            unit="PERCENTAGE",
                            timestamp=ts,
                        )
                    )
            for reading in item.get("spo2Readings", []):
                epoch = reading.get("epochTimestamp")
                val = reading.get("spo2Value")
                if epoch and val is not None:
                    ts = datetime.fromtimestamp(epoch, tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="BLOOD_OXYGEN",
                            value=float(val),
                            unit="PERCENTAGE",
                            timestamp=ts,
                        )
                    )
        return results

    def _parse_respiration(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            time_offsets = item.get("timeOffsetEpochToBreaths") or item.get("timeOffsetRespirationSamples") or {}
            for offset_str, val in time_offsets.items():
                if val is not None and val > 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="RESPIRATORY_RATE",
                            value=float(val),
                            unit="RESPIRATIONS_PER_MINUTE",
                            timestamp=ts,
                        )
                    )
        return results

    def _parse_hrv(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            time_offsets = item.get("hrvValues") or {}
            for offset_str, val in time_offsets.items():
                if val is not None and val > 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="HEART_RATE_VARIABILITY_RMSSD",
                            value=float(val),
                            unit="MILLISECONDS",
                            timestamp=ts,
                        )
                    )
            last_night_avg = item.get("lastNightAvg")
            if last_night_avg and start_ts > 0:
                ts = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                results.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE_VARIABILITY_RMSSD",
                        value=float(last_night_avg),
                        unit="MILLISECONDS",
                        timestamp=ts,
                    )
                )
        return results

    def _parse_dailies(
        self, data: Any
    ) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement], List[DurationMeasurement], int]:
        inst_results: List[InstantaneousMeasurement] = []
        cum_results: List[CumulativeMeasurement] = []
        dur_results: List[DurationMeasurement] = []
        latest_steps = 0

        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            duration = int(item.get("durationInSeconds", 86400))
            if start_ts <= 0:
                continue

            p_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            p_end = datetime.fromtimestamp(start_ts + duration, tz=timezone.utc)

            hr_samples = item.get("timeOffsetHeartRateSamples") or {}
            for offset_str, hr_val in hr_samples.items():
                if hr_val is not None and hr_val > 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    inst_results.append(
                        InstantaneousMeasurement(
                            type="HEART_RATE",
                            value=float(hr_val),
                            unit="BEATS_PER_MINUTE",
                            timestamp=ts,
                        )
                    )

            resting_hr = item.get("restingHeartRateInBeatsPerMinute")
            if resting_hr and resting_hr > 0:
                inst_results.append(
                    InstantaneousMeasurement(
                        type="RESTING_HEART_RATE",
                        value=float(resting_hr),
                        unit="BEATS_PER_MINUTE",
                        timestamp=p_start,
                    )
                )

            steps = item.get("steps")
            if steps is not None and steps > 0:
                latest_steps = max(latest_steps, int(steps))
                cum_results.append(
                    CumulativeMeasurement(
                        type="STEPS",
                        value=float(steps),
                        unit="COUNT",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            floors = item.get("floorsClimbed")
            if floors is not None and floors > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="FLIGHTS_CLIMBED",
                        value=float(floors),
                        unit="COUNT",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            active_kcal = item.get("activeKilocalories")
            if active_kcal is not None and active_kcal > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        value=float(active_kcal),
                        unit="KILOCALORIE",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            bmr_kcal = item.get("bmrKilocalories")
            if bmr_kcal is not None and bmr_kcal > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="BASAL_ENERGY_BURNED",
                        value=float(bmr_kcal),
                        unit="KILOCALORIE",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            distance_m = item.get("distanceInMeters")
            if distance_m is not None and distance_m > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        value=float(distance_m),
                        unit="METER",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            mod_sec = int(item.get("moderateIntensityDurationInSeconds", 0) or 0)
            vig_sec = int(item.get("vigorousIntensityDurationInSeconds", 0) or 0)
            total_ex_sec = mod_sec + vig_sec
            if total_ex_sec > 0:
                ex_min = round(total_ex_sec / 60.0, 2)
                dur_results.append(
                    DurationMeasurement(
                        type="EXERCISE_TIME",
                        value=float(ex_min),
                        unit="MINUTE",
                        startTime=p_start,
                        endTime=datetime.fromtimestamp(start_ts + total_ex_sec, tz=timezone.utc),
                        durationMinutes=int(round(ex_min)),
                    )
                )

        return inst_results, cum_results, dur_results, latest_steps

    def _parse_epochs(self, data: Any) -> tuple[List[InstantaneousMeasurement], List[CumulativeMeasurement]]:
        inst_results = []
        cum_results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            duration = int(item.get("durationInSeconds", 900))
            if start_ts <= 0:
                continue

            p_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            p_end = datetime.fromtimestamp(start_ts + duration, tz=timezone.utc)

            mean_hr = item.get("meanHeartRateInBeatsPerMinute")
            if mean_hr and mean_hr > 0:
                inst_results.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        value=float(mean_hr),
                        unit="BEATS_PER_MINUTE",
                        timestamp=p_start,
                    )
                )

            steps = item.get("steps")
            if steps and steps > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="STEPS",
                        value=float(steps),
                        unit="COUNT",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            active_kcal = item.get("activeKilocalories")
            if active_kcal and active_kcal > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="ACTIVE_ENERGY_BURNED",
                        value=float(active_kcal),
                        unit="KILOCALORIE",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )

            distance_m = item.get("distanceInMeters")
            if distance_m and distance_m > 0:
                cum_results.append(
                    CumulativeMeasurement(
                        type="DISTANCE_WALKING_RUNNING",
                        value=float(distance_m),
                        unit="METER",
                        periodStart=p_start,
                        periodEnd=p_end,
                        duration=duration,
                    )
                )
        return inst_results, cum_results

    def _parse_sleeps(self, data: Any) -> List[DurationMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            duration_sec = int(item.get("durationInSeconds", 0) or 0)
            if start_ts <= 0 or duration_sec <= 0:
                continue

            s_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            s_end = datetime.fromtimestamp(start_ts + duration_sec, tz=timezone.utc)
            total_min = round(duration_sec / 60.0, 2)

            results.append(
                DurationMeasurement(
                    type="SLEEP_ASLEEP",
                    value=float(total_min),
                    unit="MINUTE",
                    startTime=s_start,
                    endTime=s_end,
                    durationMinutes=int(round(total_min)),
                )
            )

            stage_fields = [
                ("deepSleepDurationInSeconds", "SLEEP_DEEP"),
                ("lightSleepDurationInSeconds", "SLEEP_LIGHT"),
                ("remSleepInSeconds", "SLEEP_REM"),
                ("awakeDurationInSeconds", "SLEEP_AWAKE"),
            ]
            for field_name, metric_type in stage_fields:
                stage_sec = int(item.get(field_name, 0) or 0)
                if stage_sec > 0:
                    stage_min = round(stage_sec / 60.0, 2)
                    results.append(
                        DurationMeasurement(
                            type=metric_type,
                            value=float(stage_min),
                            unit="MINUTE",
                            startTime=s_start,
                            endTime=datetime.fromtimestamp(start_ts + stage_sec, tz=timezone.utc),
                            durationMinutes=int(round(stage_min)),
                        )
                    )
        return results

    def _parse_stress(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds", 0)
            stress_offsets = item.get("timeOffsetStressLevelValues") or {}
            for offset_str, val in stress_offsets.items():
                if val is not None and val >= 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="STRESS_LEVEL",
                            value=float(val),
                            unit="SCORE",
                            timestamp=ts,
                        )
                    )
            bb_offsets = item.get("timeOffsetBodyBatteryValues") or {}
            for offset_str, val in bb_offsets.items():
                if val is not None and val >= 0:
                    ts = datetime.fromtimestamp(start_ts + int(offset_str), tz=timezone.utc)
                    results.append(
                        InstantaneousMeasurement(
                            type="BODY_BATTERY",
                            value=float(val),
                            unit="PERCENTAGE",
                            timestamp=ts,
                        )
                    )
        return results

    def _parse_body_comps(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            ts_sec = item.get("measurementTimeInSeconds") or item.get("startTimeInSeconds", 0)
            if ts_sec <= 0:
                continue
            ts = datetime.fromtimestamp(ts_sec, tz=timezone.utc)

            weight_g = item.get("weightInGrams")
            if weight_g and weight_g > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="WEIGHT",
                        value=round(float(weight_g) / 1000.0, 3),
                        unit="KILOGRAM",
                        timestamp=ts,
                    )
                )
            bmi = item.get("bodyMassIndex")
            if bmi and bmi > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="BODY_MASS_INDEX",
                        value=float(bmi),
                        unit="KG_PER_M2",
                        timestamp=ts,
                    )
                )
            body_fat = item.get("bodyFatInPercent")
            if body_fat is not None and body_fat >= 0:
                results.append(
                    InstantaneousMeasurement(
                        type="BODY_FAT_PERCENTAGE",
                        value=float(body_fat),
                        unit="PERCENTAGE",
                        timestamp=ts,
                    )
                )
        return results

    def _parse_blood_pressures(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            ts_sec = item.get("measurementTimeInSeconds") or item.get("startTimeInSeconds", 0)
            if ts_sec <= 0:
                continue
            ts = datetime.fromtimestamp(ts_sec, tz=timezone.utc)

            systolic = item.get("systolic")
            if systolic and systolic > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="BLOOD_PRESSURE_SYSTOLIC",
                        value=float(systolic),
                        unit="MILLIMETER_OF_MERCURY",
                        timestamp=ts,
                    )
                )
            diastolic = item.get("diastolic")
            if diastolic and diastolic > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="BLOOD_PRESSURE_DIASTOLIC",
                        value=float(diastolic),
                        unit="MILLIMETER_OF_MERCURY",
                        timestamp=ts,
                    )
                )
            pulse = item.get("pulse")
            if pulse and pulse > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="HEART_RATE",
                        value=float(pulse),
                        unit="BEATS_PER_MINUTE",
                        timestamp=ts,
                    )
                )
        return results

    def _parse_skin_temp(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            ts_sec = item.get("startTimeInSeconds", 0)
            if ts_sec <= 0:
                continue
            ts = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
            temp_val = item.get("avgDeviationCelsius") or item.get("temperatureCelsius")
            if temp_val is not None:
                results.append(
                    InstantaneousMeasurement(
                        type="BODY_TEMPERATURE",
                        value=float(temp_val),
                        unit="DEGREE_CELSIUS",
                        timestamp=ts,
                    )
                )
        return results

    def _parse_user_metrics(self, data: Any) -> List[InstantaneousMeasurement]:
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            ts_sec = item.get("startTimeInSeconds", 0)
            ts = datetime.fromtimestamp(ts_sec, tz=timezone.utc) if ts_sec > 0 else datetime.now(timezone.utc)
            vo2 = item.get("vo2Max") or item.get("vo2MaxCycling")
            if vo2 and vo2 > 0:
                results.append(
                    InstantaneousMeasurement(
                        type="VO2_MAX",
                        value=float(vo2),
                        unit="ML_PER_KG_MIN",
                        timestamp=ts,
                    )
                )
        return results

    def _parse_ecg(self, data: Any) -> tuple[List[InstantaneousMeasurement], List[WaveformMeasurement]]:
        """Parses on-demand or continuous ECG recordings of arbitrary duration"""
        inst_results: List[InstantaneousMeasurement] = []
        wav_results: List[WaveformMeasurement] = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            start_ts = item.get("startTimeInSeconds") or item.get("recordingTimestamp", 0)
            if start_ts <= 0:
                continue
            sampling_hz = float(item.get("samplingFrequencyHz", 250.0))
            samples = [float(s) for s in (item.get("samples") or item.get("waveformSamples") or [])]

            raw_duration = item.get("durationInSeconds")
            end_ts = item.get("endTimeInSeconds")
            if raw_duration is not None and float(raw_duration) > 0:
                duration_sec = float(raw_duration)
            elif end_ts is not None and float(end_ts) > start_ts:
                duration_sec = float(end_ts) - float(start_ts)
            elif samples and sampling_hz > 0:
                duration_sec = round(len(samples) / sampling_hz, 3)
            else:
                duration_sec = 30.0

            classification = item.get("rhythmClassification") or item.get("classification", "SINUS_RHYTHM")
            mean_hr = item.get("meanHeartRate") or item.get("averageHeartRateInBeatsPerMinute")

            s_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            s_end = datetime.fromtimestamp(start_ts + duration_sec, tz=timezone.utc)

            wav_results.append(
                WaveformMeasurement(
                    type="ELECTROCARDIOGRAM",
                    unit=item.get("unit", "MICROVOLTS"),
                    startTime=s_start,
                    endTime=s_end,
                    durationSeconds=duration_sec,
                    samplingFrequencyHz=sampling_hz,
                    classification=classification,
                    meanHeartRate=float(mean_hr) if mean_hr else None,
                    leadName=item.get("leadName", "LEAD_I"),
                    samples=samples,
                )
            )

            inst_results.append(
                InstantaneousMeasurement(
                    type="ELECTROCARDIOGRAM",
                    value=float(mean_hr) if mean_hr else 1.0,
                    unit="BEATS_PER_MINUTE" if mean_hr else "EVENT",
                    timestamp=s_start,
                    metadata={
                        "classification": classification,
                        "durationSeconds": duration_sec,
                        "samplingFrequencyHz": sampling_hz,
                        "sampleCount": len(samples),
                    },
                )
            )
        return inst_results, wav_results

    def _parse_garmin_bundle(
        self, bundle: Dict[str, Any]
    ) -> tuple[
        List[InstantaneousMeasurement],
        List[CumulativeMeasurement],
        List[DurationMeasurement],
        List[WaveformMeasurement],
        int,
    ]:
        inst: List[InstantaneousMeasurement] = []
        cum: List[CumulativeMeasurement] = []
        dur: List[DurationMeasurement] = []
        wav: List[WaveformMeasurement] = []
        steps = 0

        if "pulseOx" in bundle:
            inst.extend(self._parse_pulse_ox(bundle["pulseOx"]))
        if "respiration" in bundle:
            inst.extend(self._parse_respiration(bundle["respiration"]))
        if "allDayRespiration" in bundle:
            inst.extend(self._parse_respiration(bundle["allDayRespiration"]))
        if "hrv" in bundle:
            inst.extend(self._parse_hrv(bundle["hrv"]))
        if "hrvSummary" in bundle:
            inst.extend(self._parse_hrv(bundle["hrvSummary"]))
        if "hrvSummaries" in bundle:
            inst.extend(self._parse_hrv(bundle["hrvSummaries"]))
        if "dailies" in bundle:
            i, c, d, s = self._parse_dailies(bundle["dailies"])
            inst.extend(i)
            cum.extend(c)
            dur.extend(d)
            steps = max(steps, s)
        if "epochs" in bundle:
            i, c = self._parse_epochs(bundle["epochs"])
            inst.extend(i)
            cum.extend(c)
        if "sleeps" in bundle:
            dur.extend(self._parse_sleeps(bundle["sleeps"]))
        if "stressDetails" in bundle:
            inst.extend(self._parse_stress(bundle["stressDetails"]))
        if "bodyComps" in bundle:
            inst.extend(self._parse_body_comps(bundle["bodyComps"]))
        if "bloodPressures" in bundle:
            inst.extend(self._parse_blood_pressures(bundle["bloodPressures"]))
        if "skinTemp" in bundle:
            inst.extend(self._parse_skin_temp(bundle["skinTemp"]))
        if "userMetrics" in bundle:
            inst.extend(self._parse_user_metrics(bundle["userMetrics"]))
        if "ecg" in bundle:
            i, w = self._parse_ecg(bundle["ecg"])
            inst.extend(i)
            wav.extend(w)
        if "steps" in bundle:
            steps = max(steps, int(bundle["steps"]))

        return inst, cum, dur, wav, steps
