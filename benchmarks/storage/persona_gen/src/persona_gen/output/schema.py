"""Arrow schemas for every generated table"""

import pyarrow as pa

STR = pa.string()
DSTR = pa.dictionary(pa.int32(), pa.string())
F64 = pa.float64()
F32 = pa.float32()
I64 = pa.int64()
I32 = pa.int32()
I16 = pa.int16()
BOOL = pa.bool_()
TS_S = pa.timestamp("s", tz="UTC")
TS_MS = pa.timestamp("ms", tz="UTC")

# Partition columns are appended by the writer: shard (all tables), month (large tables).
SCHEMAS: dict[str, pa.Schema] = {
    "observations": pa.schema(
        [
            ("record_id", STR),
            ("patient_id", DSTR),
            ("device_id", DSTR),
            ("wearable_id", DSTR),
            ("source_name", DSTR),
            ("device_model", DSTR),
            ("platform", DSTR),
            ("metric", DSTR),
            ("unit", DSTR),
            ("value", F64),
            ("category", DSTR),
            ("start", TS_S),
            ("end", TS_S),
            ("start_offset_min", I16),
            ("end_offset_min", I16),
            ("created_at", TS_S),
            ("truth_kind", DSTR),
            ("truth_seq", I64),
            ("readable", BOOL),
            ("duplicate_of", STR),
        ]
    ),
    "workouts": pa.schema(
        [
            ("record_id", STR),
            ("patient_id", DSTR),
            ("device_id", DSTR),
            ("wearable_id", DSTR),
            ("source_name", DSTR),
            ("platform", DSTR),
            ("activity", DSTR),
            ("start", TS_S),
            ("end", TS_S),
            ("start_offset_min", I16),
            ("created_at", TS_S),
            ("duration_s", F64),
            ("energy_kcal", F64),
            ("distance_m", F64),
            ("effort", I16),
            ("auto_detected", BOOL),
            ("pauses", I16),
            ("outdoors", BOOL),
            ("truth_workout", I64),
            ("workout_seq", I64),
        ]
    ),
    "truth_intervals": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I64),
            ("start", TS_MS),
            ("end", TS_MS),
            ("offset_min", I16),
            ("state", DSTR),
            ("activity", DSTR),
            ("met", F32),
            ("cadence_spm", F32),
            ("speed_mps", F32),
            ("hr_intensity", F32),
            ("hr_target", F32),
            ("hr_start", F32),
            ("outdoors", BOOL),
            ("upright", BOOL),
            ("workout_seq", I32),
            ("night_seq", I32),
            ("day_seq", I32),
            ("headphones", BOOL),
            ("flights", F32),
        ]
    ),
    "truth_days": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I32),
            ("date", pa.date32()),
            ("in_window", BOOL),
            ("workday", BOOL),
            ("wake", TS_MS),
            ("bed", TS_MS),
            ("vo2max", F64),
            ("rhr", F64),
            ("ln_rmssd", F64),
            ("activity_multiplier", F64),
            ("workout_multiplier", F64),
            ("sleep_hours", F64),
            ("sleep_debt_hours", F64),
            ("steps_true", F64),
            ("medication_rhr_delta", F64),
            ("condition_rhr_delta", F64),
            ("temperature_delta", F64),
            ("hrmax_multiplier", F64),
            ("stimulant_active", BOOL),
            ("illness", F64),
            ("injury", BOOL),
            ("mood", F64),
            ("vacation", BOOL),
            ("hospital", BOOL),
            ("hard_workout", BOOL),
        ]
    ),
    "truth_nights": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I32),
            ("day_seq", I32),
            ("in_bed", TS_MS),
            ("onset", TS_MS),
            ("wake", TS_MS),
            ("out_of_bed", TS_MS),
            ("asleep_seconds", F64),
            ("nap", BOOL),
        ]
    ),
    "truth_workouts": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I32),
            ("kind", DSTR),
            ("activity", DSTR),
            ("start", TS_MS),
            ("end", TS_MS),
            ("outdoors", BOOL),
            ("intends_record", BOOL),
            ("record_start", TS_MS),
            ("record_end", TS_MS),
            ("auto_detectable", BOOL),
            ("pauses", I16),
            ("segments", I16),
        ]
    ),
    "truth_wear": pa.schema(
        [
            ("patient_id", DSTR),
            ("device_id", DSTR),
            ("start", TS_MS),
            ("end", TS_MS),
            ("reason", DSTR),
        ]
    ),
    "truth_hrv": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I64),
            ("device_id", DSTR),
            ("start", TS_MS),
            ("end", TS_MS),
            ("mean_hr", F64),
            ("rmssd", F64),
            ("sdnn", F64),
            ("beats", I32),
        ]
    ),
    "events": pa.schema(
        [
            ("patient_id", DSTR),
            ("seq", I32),
            ("kind", DSTR),
            ("code", STR),
            ("start", TS_MS),
            ("end", TS_MS),
            ("detail", STR),
        ]
    ),
    "devices": pa.schema(
        [
            ("patient_id", DSTR),
            ("device_id", STR),
            ("wearable_id", STR),
            ("model", DSTR),
            ("hardware", DSTR),
            ("source_name", DSTR),
            ("kind", DSTR),
            ("archetype", DSTR),
            ("platform", DSTR),
            ("role", DSTR),
            ("start", TS_MS),
            ("end", TS_MS),
            ("reason", DSTR),
            ("motion_enabled", BOOL),
        ]
    ),
    "app_sync": pa.schema([("patient_id", DSTR), ("time", TS_S)]),
    "routes": pa.schema(
        [
            ("patient_id", DSTR),
            ("device_id", DSTR),
            ("truth_workout", I64),
            ("time", TS_MS),
            ("latitude", F64),
            ("longitude", F64),
            ("elevation_m", F32),
            ("speed_mps", F32),
            ("course_deg", F32),
            ("horizontal_accuracy_m", F32),
        ]
    ),
    "ecg": pa.schema(
        [
            ("record_id", STR),
            ("patient_id", DSTR),
            ("device_id", DSTR),
            ("source_name", DSTR),
            ("start", TS_S),
            ("start_offset_min", I16),
            ("created_at", TS_S),
            ("sampling_hz", F32),
            ("classification", DSTR),
            ("average_hr", F32),
            ("truth_seq", I64),
            ("voltage_uv", pa.list_(F32)),
        ]
    ),
    "personas": pa.schema(
        [
            ("patient_id", STR),
            ("synthea_reused", BOOL),
            ("index", I64),
            ("cohort", DSTR),
            ("anchor", DSTR),
            ("anchor_kind", DSTR),
            ("age", I16),
            ("sex", DSTR),
            ("height_cm", F64),
            ("weight_kg", F64),
            ("bmi", F64),
            ("timezone", DSTR),
            ("latitude", F64),
            ("longitude", F64),
            ("archetype", DSTR),
            ("occupation", DSTR),
            ("activity_level", F64),
            ("light_multiplier", F64),
            ("vo2max", F64),
            ("rhr", F64),
            ("ln_rmssd", F64),
            ("hrmax", F64),
            ("respiratory_rate", F64),
            ("spo2", F64),
            ("wrist_temperature", F64),
            ("hr_on_tau", F64),
            ("hr_off_tau", F64),
            ("recovery_slow_fraction", F64),
            ("recovery_slow_tau", F64),
            ("effort_gain", F64),
            ("sleep_debt_rhr", F64),
            ("medication_response", F64),
            ("lf_hf_ratio", F64),
            ("midsleep_hour", F64),
            ("weekend_shift_hours", F64),
            ("sleep_need_hours", F64),
            ("regularity_minutes", F64),
            ("nap_probability", F64),
            ("trajectory", DSTR),
            (
                "workout_plan",
                pa.list_(
                    pa.struct(
                        [
                            ("type", STR),
                            ("per_week", F64),
                            ("minutes", F64),
                            ("minutes_sigma", F64),
                            ("record_propensity", F64),
                        ]
                    )
                ),
            ),
            ("preferred_slots", pa.map_(STR, F64)),
            ("weekend_only", BOOL),
            ("double_session_probability", F64),
            ("abandonment_multiplier", F64),
            ("micro_workouts", BOOL),
            ("nutrition_logger", BOOL),
            ("weight_logger", DSTR),
            ("bp_cuff", BOOL),
            ("headphone_listener", BOOL),
            ("alcohol_drinks_per_day", F64),
            ("height_logger", BOOL),
            ("ecg_per_week", F64),
            ("afib_history", BOOL),
            ("stride_m", F64),
            ("double_support_pct", F64),
            ("asymmetry_pct", F64),
            ("conditions", pa.list_(STR)),
            ("medications", pa.list_(STR)),
            ("synthea_id", STR),
            ("platform", DSTR),
            ("enrollment", TS_S),
            ("app_sync_style", DSTR),
            ("history_permission", BOOL),
            ("signal_fit", F64),
            ("adherence", F64),
            ("night_wear", F64),
            ("wearables", pa.list_(STR)),
        ]
    ),
}
LARGE_TABLES = frozenset({"observations", "truth_intervals", "truth_hrv", "routes"})
