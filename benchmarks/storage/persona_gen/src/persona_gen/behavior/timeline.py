"""Continuous-time behaviour timeline.

Each local day is planned from fixed blocks (work, commutes, structured workouts, travel)
and the gaps are filled by a semi-Markov process whose state durations, minimums and
transitions depend on the regime (time of day, work type), the persona and the day's
latent activity drive. Nights come from the sleep-architecture model. The result is a
gap-free sequence of intervals with arbitrary start and end times (no time grid).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from ..model import (
    ASLEEP_STATES,
    BED_AWAKE,
    COMMUTE,
    LIGHT,
    SEDENTARY,
    SLEEP_LIGHT,
    WALK,
    WORKOUT,
)
from ..persona.sampler import Persona
from ..physiology.daily import DailyState
from ..timeutil import HOUR, MINUTE, ZoneTimeline, offsets_minutes
from ..util import choice, lognormal
from . import sleep as sleep_model
from . import workouts as workout_model
from .events import EventPlan

ACTIVITIES = (
    "none",
    "walk",
    "run",
    "cycle",
    "strength",
    "hiit",
    "yoga",
    "swim",
    "hike",
    "commute_walk",
    "commute_cycle",
    "transit",
    "car",
    "flight",
    "nap",
)
ACTIVITY_INDEX = {name: i for i, name in enumerate(ACTIVITIES)}
UPRIGHT_ACTIVITIES = frozenset({"walk", "run", "strength", "hiit", "yoga", "hike", "commute_walk"})
COLUMNS = (
    "start",
    "end",
    "state",
    "activity",
    "met",
    "cadence",
    "speed",
    "intensity",
    "arm",
    "outdoors",
    "upright",
    "workout",
    "night",
    "day",
    "audio_db",
    "headphones",
    "flights",
)


@dataclass(slots=True)
class Night:
    id: int
    day: int  # index of the local day the night ends on
    in_bed: float
    onset: float
    wake: float
    out_of_bed: float
    asleep_seconds: float
    nap: bool = False


@dataclass(slots=True)
class Dose:
    time: float
    day: int
    tmax_hours: float
    half_life_hours: float
    awake_hr_delta: float


@dataclass(slots=True)
class Timeline:
    columns: dict[str, np.ndarray]
    workouts: list[workout_model.Workout]
    nights: list[Night]
    doses: list[Dose]
    wake: np.ndarray  # per day: UTC wake (out of bed) time
    bed: np.ndarray  # per day: UTC in-bed time of the night starting that evening
    workday: np.ndarray
    hard_workout: np.ndarray
    events: list[tuple[str, float, float | None, str, dict[str, Any]]] = field(default_factory=list)

    @property
    def start(self) -> np.ndarray:
        return self.columns["start"]

    @property
    def end(self) -> np.ndarray:
        return self.columns["end"]

    def __len__(self) -> int:
        return len(self.columns["start"])


class _Rows:
    def __init__(self) -> None:
        self.rows: list[tuple[Any, ...]] = []

    def add(
        self,
        start: float,
        end: float,
        state: int,
        activity: str,
        met: float,
        cadence: float,
        speed: float,
        intensity: float,
        arm: float,
        outdoors: bool,
        upright: bool,
        workout: int,
        night: int,
        day: int,
        audio: float,
        headphones: bool,
        flights: float,
    ) -> None:
        if end - start <= 0.5:
            return
        self.rows.append(
            (
                start,
                end,
                state,
                ACTIVITY_INDEX[activity],
                met,
                cadence,
                speed,
                intensity,
                arm,
                outdoors,
                upright,
                workout,
                night,
                day,
                audio,
                headphones,
                flights,
            )
        )

    def columns(self) -> dict[str, np.ndarray]:
        self.rows.sort(key=lambda r: r[0])
        # Enforce a gap-free, non-overlapping timeline (defensive: blocks may run long).
        fixed: list[tuple[Any, ...]] = []
        for row in self.rows:
            if fixed and row[0] < fixed[-1][1]:
                row = (fixed[-1][1], *row[1:])
                if row[1] - row[0] <= 0.5:
                    continue
            if fixed and row[0] > fixed[-1][1]:
                fixed[-1] = (fixed[-1][0], row[0], *fixed[-1][2:])
            fixed.append(row)
        self.rows = fixed
        dtypes = (
            np.float64,
            np.float64,
            np.int8,
            np.int8,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            np.float32,
            np.bool_,
            np.bool_,
            np.int32,
            np.int32,
            np.int32,
            np.float32,
            np.bool_,
            np.float32,
        )
        if not self.rows:
            return {name: np.zeros(0, dtype=t) for name, t in zip(COLUMNS, dtypes, strict=True)}
        transposed = list(zip(*self.rows, strict=True))
        return {name: np.asarray(col, dtype=t) for name, col, t in zip(COLUMNS, transposed, dtypes, strict=True)}


@dataclass(slots=True)
class _Block:
    start: float
    end: float
    kind: str
    payload: Any = None


class TimelineBuilder:
    def __init__(
        self,
        persona: Persona,
        daily: DailyState,
        plan: EventPlan,
        tz: ZoneTimeline,
        params: Mapping[str, Any],
        rng: np.random.Generator,
    ) -> None:
        self.p = persona
        self.daily = daily
        self.plan = plan
        self.tz = tz
        self.params = params
        self.rng = rng
        self.behavior = params["behavior"]
        self.states = self.behavior["states"]
        self.rows = _Rows()
        self.workouts: list[workout_model.Workout] = []
        self.nights: list[Night] = []
        self.doses: list[Dose] = []
        pop = params["population"]
        occupation = pop["occupation"][persona.occupation]
        self.occupation = occupation
        self.commute_mode = choice(rng, occupation["commute"])
        self.commute_minutes = float(lognormal(rng, occupation["commute_minutes"]))
        self.work_start = float(rng.normal(*occupation["work_start_hour"])) if occupation["workdays"] else 0.0
        self.work_hours = float(max(2.0, rng.normal(*occupation["work_hours"]))) if occupation["workdays"] else 0.0
        self.record_propensity = {
            str(w[0]): float(np.clip(w[4] + rng.normal(0, 0.12), 0.0, 1.0)) for w in persona.workout_plan
        }
        self.walk_cadence = float(rng.normal(self.states["cadence_spm"][2], 6.0))
        self.workout_id = 0
        n = len(plan.days)
        self.workday = np.zeros(n, dtype=bool)
        self.work_window: list[tuple[float, float] | None] = [None] * n
        self.hard = np.zeros(n)
        self.body_offset = 0.0
        self.hours_cache: dict[int, tuple[float, float]] = {}
        self.last_zone_offset: int | None = None

    def local(self, day: date, hours: float, zone: str) -> float:
        return self.tz.local_to_utc(day, hours, zone)

    def _is_workday(self, i: int) -> bool:
        if i >= len(self.plan.days):
            return False
        occ = self.occupation
        day = self.plan.days[i]
        if not occ["workdays"] or self.plan.vacation[i] or self.plan.hospital[i] or self.plan.illness[i] > 0.6:
            return False
        return day.weekday() < int(occ["workdays"])

    def _shift(self, i: int) -> str:
        if "rotation_days" not in self.occupation:
            return "day"
        phases = tuple(self.occupation.get("rotation", ("early", "late", "night")))
        return str(phases[(i // int(self.occupation["rotation_days"])) % len(phases)])

    def _work_hours(self, i: int) -> tuple[float, float]:
        """Local start/end hours of day ``i``'s work (cached so every caller agrees)."""
        if i not in self.hours_cache:
            start = self.work_start + self.rng.normal(0, 0.15)
            start += {"late": 8.0, "night": 16.0}.get(self._shift(i), 0.0)
            self.hours_cache[i] = (start, start + self.work_hours + self.rng.normal(0, 0.3))
        return self.hours_cache[i]

    def _night_shift(self, i: int) -> bool:
        return self._is_workday(i) and self._shift(i) == "night"

    def _plan_night(self, i: int, earliest_bed: float, dose_today: bool) -> tuple[float, float]:
        """In-bed and wake instants for the night that ends on day ``i + 1``.

        After a night shift the main sleep happens in the morning: shorter, starting soon
        after the commute home.
        """
        p, spec = self.p, self.behavior["sleep"]
        if self._night_shift(i):
            duration = float(np.clip(p.sleep_need_hours - 1.0 + self.rng.normal(0, 0.7), 4.0, 9.0))
            in_bed = earliest_bed + float(lognormal(self.rng, (20.0, 0.5))) * MINUTE
            return in_bed, in_bed + duration * HOUR
        days = self.plan.days
        next_index = min(i + 1, len(days) - 1)
        next_day = days[next_index] if i + 1 < len(days) else days[-1].fromordinal(days[-1].toordinal() + 1)
        zone = self.tz.zone_for_day(next_day)
        next_work = self._is_workday(i + 1)
        free = not next_work
        mid = p.midsleep_hour + (p.weekend_shift_hours if free else 0.0) + self.body_offset
        mid += self.rng.normal(0, p.regularity_minutes / 60)
        debt = self.daily.sleep_debt[min(i, len(days) - 1)]
        need = p.sleep_need_hours + self.daily.sleep_extra_hours[next_index]
        duration = (
            need
            + (spec["sleep_debt_repayment"] * debt if free else 0.0)
            + self.rng.normal(0, spec["duration_sigma_hours"])
        )
        duration = float(np.clip(duration, 3.5, spec["max_sleep_hours"]))
        onset = mid - duration / 2
        wake = mid + duration / 2
        if next_work and spec["workday_alarm"]:
            start, _ = self._work_hours(i + 1)
            prep = float(lognormal(self.rng, spec["prep_minutes_before_commute"])) / 60
            commute = self.commute_minutes / 60 if self.commute_mode != "none" else 0.0
            alarm = start - commute - prep
            if alarm < wake:
                # People with early starts go to bed earlier, recovering part of the lost sleep.
                onset -= float(self.behavior["sleep"]["alarm_bedtime_advance"]) * (wake - alarm)
                wake = alarm
        latency = 0.2
        in_bed = self.local(next_day, onset - latency, zone)
        wake_t = self.local(next_day, wake, zone)
        in_bed = max(in_bed, earliest_bed)
        if wake_t - in_bed < 3 * HOUR:
            wake_t = in_bed + 3 * HOUR + abs(self.rng.normal(0, 0.5)) * HOUR
        return in_bed, wake_t

    def _add_night(self, in_bed: float, wake: float, day: int, latency_extra: float, nap: bool = False) -> float:
        age = self.p.age
        segments = sleep_model.night(
            in_bed,
            wake,
            age=age,
            awakenings_multiplier=float(self.daily.awakenings_multiplier[min(day, len(self.plan.days) - 1)]),
            latency_extra_minutes=latency_extra,
            params=self.params,
            rng=self.rng,
        )
        night_id = len(self.nights)
        asleep = 0.0
        onset = next((s for s, _, st in segments if st in ASLEEP_STATES), in_bed)
        for start, end, state in segments:
            if state in ASLEEP_STATES:
                asleep += end - start
            self.rows.add(
                start,
                end,
                state,
                "nap" if nap else "none",
                1.0,
                0.0,
                0.0,
                0.0,
                0.02,
                False,
                False,
                -1,
                night_id,
                max(0, day),
                38.0,
                False,
                0.0,
            )
        out = segments[-1][1]
        self.nights.append(Night(night_id, day, in_bed, onset, wake, out, asleep, nap))
        return out

    # Awake fill
    def _regime(self, instant: float, day: int, zone: str) -> str:
        offset = offsets_minutes(zone, np.asarray([instant]))[0]
        hour = ((instant + offset * MINUTE) % 86400) / HOUR
        return "free_morning" if hour < 12 else "free_afternoon" if hour < 18 else "free_evening"

    def _fill(self, start: float, end: float, regime: str, day: int) -> None:
        # TODO(realism): Fit hourly activity and step-bout patterns from LifeSnaps.
        if end - start <= 0:
            return
        spec = self.behavior["regimes"][regime]
        st = self.states
        mins = np.asarray(st["min_minutes"]) * MINUTE
        drive = float(self.daily.activity[day]) * (0.7 + 0.6 * self.p.activity_level) * self.p.light_multiplier
        drive *= float(self.p.traits.get("activity_scale", 1.0))
        scale = np.asarray([1 / np.sqrt(drive), drive, drive])
        transitions = np.asarray(spec["transitions"], dtype=float)
        transitions[:, 1:] *= np.sqrt(drive)
        transitions /= transitions.sum(axis=1, keepdims=True)
        state = int(self.rng.choice(3, p=[0.6, 0.3, 0.1]))
        cursor = start
        audio_base = (50.0, 58.0, 64.0)
        while cursor < end:
            median = spec["median_minutes"][state] * MINUTE * scale[state]
            length = max(mins[state], float(self.rng.lognormal(np.log(median), spec["log_sigma"][state])))
            if end - (cursor + length) < mins.min():
                length = end - cursor
            stop = min(end, cursor + length)
            outdoors = bool(self.rng.random() < st["outdoor_probability"][state])
            cadence = st["cadence_spm"][state] * float(np.exp(self.rng.normal(0, st["cadence_sigma"][state])))
            if state == 2:
                cadence = self.walk_cadence * float(np.exp(self.rng.normal(0, st["cadence_sigma"][state])))
            speed = cadence / 60 * self.p.stride_m if state == 2 else cadence / 60 * self.p.stride_m * 0.6
            flights = float(
                self.rng.poisson((stop - cursor) / MINUTE * (0.04 if state == 2 else 0.02 if state == 1 else 0.0))
            )
            phones = bool(self.p.headphone_listener and state == 2 and self.rng.random() < 0.35)
            self.rows.add(
                cursor,
                stop,
                (SEDENTARY, LIGHT, WALK)[state],
                "none",
                st["met"][state],
                cadence,
                speed,
                st["hr_intensity"][state],
                st["arm_motion"][state],
                outdoors,
                st["upright"][state],
                -1,
                -1,
                day,
                audio_base[state] + self.rng.normal(0, 6) + (6 if outdoors else 0),
                phones,
                flights,
            )
            cursor = stop
            state = int(self.rng.choice(3, p=transitions[state]))

    def _commute(self, start: float, day: int, length: float) -> float:
        mode = self.commute_mode
        if mode == "none":
            return start
        spec = self.behavior["commute"]
        listen = self.p.headphone_listener and self.rng.random() < 0.6
        if mode == "transit":
            walk = length * spec["transit_walk_fraction"] / 2
            w = spec["walk"]
            t = spec["transit"]
            self.rows.add(
                start,
                start + walk,
                COMMUTE,
                "commute_walk",
                w[0],
                w[1],
                w[2],
                w[3],
                w[4],
                True,
                True,
                -1,
                -1,
                day,
                68,
                listen,
                0.0,
            )
            self.rows.add(
                start + walk,
                start + length - walk,
                COMMUTE,
                "transit",
                t[0],
                t[1],
                t[2],
                t[3],
                t[4],
                False,
                False,
                -1,
                -1,
                day,
                74,
                listen,
                0.0,
            )
            self.rows.add(
                start + length - walk,
                start + length,
                COMMUTE,
                "commute_walk",
                w[0],
                w[1],
                w[2],
                w[3],
                w[4],
                True,
                True,
                -1,
                -1,
                day,
                68,
                listen,
                0.0,
            )
        else:
            m = spec[mode]
            name = {"walk": "commute_walk", "cycle": "commute_cycle", "car": "car"}[mode]
            self.rows.add(
                start,
                start + length,
                COMMUTE,
                name,
                m[0],
                m[1],
                m[2],
                m[3],
                m[4],
                mode != "car",
                mode == "walk",
                -1,
                -1,
                day,
                70,
                listen and mode != "car",
                0.0,
            )
        return start + length

    def _add_workout(self, kind: str, start: float, minutes: float, propensity: float, day: int) -> float:
        spec = self.behavior["workouts"]["types"][kind]
        activity, segments, outdoors = workout_model.build(kind, start, minutes, spec, rng=self.rng)
        wid = self.workout_id
        self.workout_id += 1
        upright = activity in UPRIGHT_ACTIVITIES
        listen = self.p.headphone_listener and self.rng.random() < 0.7
        audio = 66.0 if outdoors else 75.0
        for seg in segments:
            flights = float(self.rng.poisson((seg.end - seg.start) / MINUTE * (0.15 if activity == "hike" else 0.02)))
            self.rows.add(
                seg.start,
                seg.end,
                WORKOUT,
                activity,
                seg.met,
                seg.cadence,
                seg.speed,
                seg.intensity,
                seg.arm,
                outdoors,
                upright,
                wid,
                -1,
                day,
                audio + self.rng.normal(0, 4),
                listen,
                flights,
            )
        end = segments[-1].end
        intends, rec_start, rec_end, pauses = workout_model.recording(
            start, end, propensity, self.behavior["recording"], self.rng
        )
        self.workouts.append(
            workout_model.Workout(
                wid,
                kind,
                activity,
                start,
                end,
                outdoors,
                intends,
                rec_start,
                rec_end,
                bool(spec["auto_detectable"]),
                pauses,
                segments,
            )
        )
        if kind in workout_model.HARD and minutes >= 20:
            self.hard[day] = 1.0
        return end

    def _day_blocks(self, i: int, wake: float, latest: float, zone: str) -> list[_Block]:
        p, rng = self.p, self.rng
        day = self.plan.days[i]
        blocks: list[_Block] = []

        def free(a: float, b: float) -> bool:
            return wake <= a < b <= latest and all(b <= x.start or a >= x.end for x in blocks)

        if self.plan.hospital[i]:
            return blocks
        if self._is_workday(i):
            start_h, end_h = self._work_hours(i)
            work_start = self.local(day, start_h, zone)
            work_end = self.local(day, end_h, zone)
            commute = self.commute_minutes * MINUTE if self.commute_mode != "none" else 0.0
            there = commute * float(np.exp(rng.normal(0, 0.15)))
            back = commute * float(np.exp(rng.normal(0, 0.15)))
            if work_start - there > wake and work_end + back < latest:
                if there:
                    blocks.append(_Block(work_start - there, work_start, "commute"))
                blocks.append(_Block(work_start, work_end, "work"))
                if back:
                    blocks.append(_Block(work_end, work_end + back, "commute"))
                self.workday[i] = True
                self.work_window[i] = (work_start, work_end)
        for travel in self.plan.travels:
            if day in (travel.depart, travel.back):
                flight = (2.0 + rng.uniform(0, 8.0)) * HOUR
                start = self.local(day, 10.0 + rng.normal(0, 1.5), zone)
                if free(start, start + flight):
                    blocks.append(_Block(start, start + flight, "flight"))
        weekend = day.weekday() >= 5 or bool(self.plan.vacation[i])
        sessions = workout_model.sessions_for_day(
            p.workout_plan,
            weekend=weekend,
            weekend_only=p.weekend_only,
            multiplier=float(self.daily.workout[i]),
            fatigued=bool(i > 0 and self.hard[i - 1]),
            injured=bool(self.plan.injury[i]),
            blocked=self.behavior["events"]["injury"]["blocks"],
            double_probability=p.double_session_probability,
            rng=rng,
            fatigue_multiplier=self.behavior["workouts"]["fatigue_hard_next_day_multiplier"],
        )
        slots = list(p.preferred_slots)
        for kind, minutes, sigma, _ in sessions:
            length = max(
                self.behavior["workouts"]["types"][kind]["min_minutes"], float(rng.lognormal(np.log(minutes), sigma))
            )
            weights = np.asarray([p.preferred_slots[s] for s in slots], dtype=float)
            order = [
                slots[j] for j in rng.choice(len(slots), size=len(slots), replace=False, p=weights / weights.sum())
            ]
            for slot in order:
                if slot == "morning":
                    a = wake + rng.uniform(15, 90) * MINUTE
                elif slot == "lunch":
                    a = self.local(day, rng.uniform(12.0, 13.5), zone)
                else:
                    work = self.work_window[i]
                    base = (work[1] + self.commute_minutes * MINUTE) if work else self.local(day, 17.0, zone)
                    a = base + rng.uniform(30, 150) * MINUTE
                b = a + length * MINUTE * 1.25
                if free(a - self.behavior["workouts"]["min_gap_minutes"] * MINUTE * 0.3, b):
                    blocks.append(_Block(a, b, "workout", (kind, length, self.record_propensity.get(kind, 0.5))))
                    break
        if p.micro_workouts:
            for _ in range(int(rng.integers(1, 5))):
                a = rng.uniform(wake + HOUR, max(wake + HOUR + 1, latest - HOUR))
                length = rng.uniform(1.0, 3.0)
                if free(a, a + length * MINUTE + 60):
                    blocks.append(_Block(a, a + length * MINUTE, "workout", ("micro_strength", length, 0.95)))
        if i > 0 and self._night_shift(i) and not self._night_shift(i - 1):
            # First night of a block: nap in the afternoon before the shift.
            start_h, _ = self._work_hours(i)
            a = self.local(day, start_h - 5.5 + rng.normal(0, 0.5), zone)
            length = float(rng.uniform(60, 120)) * MINUTE
            if free(a, a + length):
                blocks.append(_Block(a, a + length, "nap"))
        elif weekend and rng.random() < p.nap_probability:
            a = self.local(day, rng.uniform(13.5, 16.0), zone)
            length = float(lognormal(rng, self.behavior["sleep"]["nap_minutes"])) * MINUTE
            if free(a, a + length):
                blocks.append(_Block(a, a + length, "nap"))
        return sorted(blocks, key=lambda b: b.start)

    def _stimulant(self, i: int, wake: float) -> bool:
        med = self.daily.stimulant[i]
        if med is None:
            return False
        spec = self.params["clinical"]["medications"][med.cls]
        day = self.plan.days[i]
        log = self.p.dose_log
        if log and min(log) <= day <= max(log):
            # Twins replay the owner's real dose days (and times, when logged).
            if day not in log:
                return False
            hour = log[day]
            time = (
                self.local(day, hour, self.tz.zone_for_day(day))
                if hour is not None
                else wake + med.params["dose_after_wake_hours"] * HOUR
            )
            self.doses.append(
                Dose(time, i, med.params["tmax_hours"], med.params["half_life_hours"], med.params["awake_hr_delta"])
            )
            return True
        weekend = day.weekday() >= 5
        if self.rng.random() < spec["skip_probability"]["weekend" if weekend else "weekday"]:
            return False
        time = wake + med.params["dose_after_wake_hours"] * HOUR * float(np.exp(self.rng.normal(0, 0.3)))
        self.doses.append(
            Dose(time, i, med.params["tmax_hours"], med.params["half_life_hours"], med.params["awake_hr_delta"])
        )
        return True

    def build(self) -> Timeline:
        days = self.plan.days
        n = len(days)
        wakes = np.zeros(n)
        beds = np.zeros(n)
        self.behavior["sleep"]
        # Night before the first day.
        first_zone = self.tz.zone_for_day(days[0])
        mid = self.p.midsleep_hour
        dur = self.p.sleep_need_hours
        in_bed = self.local(days[0], mid - dur / 2 - 0.2, first_zone)
        wake = self.local(days[0], mid + dur / 2, first_zone)
        out = self._add_night(in_bed, wake, 0, 0.0)
        self.daily.sleep_hours[0] = self.nights[-1].asleep_seconds / HOUR
        for i, day in enumerate(days):
            zone = self.tz.zone_for_day(day)
            offset = int(offsets_minutes(zone, np.asarray([out]))[0])
            if (self.last_zone_offset is not None and offset != self.last_zone_offset and zone != self.tz.home) or (
                self.last_zone_offset is not None and abs(offset - self.last_zone_offset) > 90
            ):
                self.body_offset += (offset - self.last_zone_offset) / 60
            self.body_offset = float(np.sign(self.body_offset) * max(0.0, abs(self.body_offset) - self.behavior_rate()))
            self.body_offset = float(np.clip(self.body_offset, -6, 6))
            self.last_zone_offset = offset
            wakes[i] = out
            dosed = self._stimulant(i, out)
            # Latest time the day's activities may end (provisional bed estimate).
            provisional = self.local(day, self.p.midsleep_hour + 24 - self.p.sleep_need_hours / 2 - 0.5, zone)
            latest = max(out + 4 * HOUR, provisional)
            if self._night_shift(i):
                _, end_h = self._work_hours(i)
                latest = self.local(day, end_h + 2.0, zone)
            blocks = self._day_blocks(i, out, latest, zone)
            cursor = out
            for block in blocks:
                if block.start < cursor:
                    if block.kind in ("workout", "nap", "flight") or block.end <= cursor:
                        continue  # an earlier block ran long; drop optional blocks
                    block.start = cursor
                self._fill(cursor, block.start, self._regime(cursor, i, zone), i)
                cursor = self._block(block, i, zone)
            last = cursor
            latency_extra = (
                self.params["clinical"]["medications"]["stimulant"]["sleep_latency_minutes"] if dosed else 0.0
            )
            in_bed, wake = self._plan_night(i, last + 10 * MINUTE, dosed)
            if in_bed > cursor:
                self._fill(cursor, in_bed, self._regime(cursor, i, zone), i)
            beds[i] = in_bed
            out = self._add_night(in_bed, wake, min(i + 1, n - 1), latency_extra)
            slept = self.nights[-1].asleep_seconds / HOUR
            if i + 1 < n:
                self.daily.sleep_hours[i + 1] = slept
                need = self.p.sleep_need_hours + self.daily.sleep_extra_hours[i + 1]
                self.daily.sleep_debt[i + 1] = float(np.clip(self.daily.sleep_debt[i] * 0.85 + need - slept, 0, 15))
        return Timeline(
            self.rows.columns(), self.workouts, self.nights, self.doses, wakes, beds, self.workday, self.hard
        )

    def behavior_rate(self) -> float:
        """Jet-lag adjustment in hours per day (``events.travel.jetlag_hours_per_day``)."""
        return float(self.behavior["events"]["travel"]["jetlag_hours_per_day"])

    def _block(self, block: _Block, i: int, zone: str) -> float:
        if block.kind == "commute":
            return self._commute(block.start, i, block.end - block.start)
        if block.kind == "work":
            regime = self.occupation["regime"]
            self._fill(block.start, block.end, regime if regime != "free" else self._regime(block.start, i, zone), i)
            return block.end
        if block.kind == "workout":
            kind, minutes, propensity = block.payload
            # Short walk to and from the session location, then the session.
            end = self._add_workout(kind, block.start, minutes, propensity, i)
            return end
        if block.kind == "flight":
            self.rows.add(
                block.start,
                block.end,
                SEDENTARY,
                "flight",
                1.4,
                3.0,
                0.0,
                0.05,
                0.05,
                False,
                False,
                -1,
                -1,
                i,
                78.0,
                self.p.headphone_listener,
                0.0,
            )
            return block.end
        if block.kind == "nap":
            onset = block.start + float(self.rng.uniform(3, 10)) * MINUTE
            night_id = len(self.nights)
            self.rows.add(
                block.start,
                onset,
                BED_AWAKE,
                "nap",
                1.0,
                0.0,
                0.0,
                0.0,
                0.02,
                False,
                False,
                -1,
                night_id,
                i,
                40.0,
                False,
                0.0,
            )
            self.rows.add(
                onset,
                block.end,
                SLEEP_LIGHT,
                "nap",
                1.0,
                0.0,
                0.0,
                0.0,
                0.02,
                False,
                False,
                -1,
                night_id,
                i,
                40.0,
                False,
                0.0,
            )
            self.nights.append(Night(night_id, i, block.start, onset, block.end, block.end, block.end - onset, True))
            return block.end
        raise ValueError(block.kind)


def build_timeline(
    persona: Persona,
    daily: DailyState,
    plan: EventPlan,
    tz: ZoneTimeline,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> Timeline:
    return TimelineBuilder(persona, daily, plan, tz, params, rng).build()
