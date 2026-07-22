"""Coordinator for the Weight Coach integration.

Owns Store I/O, listens for new readings from the configured source weight
sensor (plus manual entry and calorie-intake logging), and runs the trend/
regression/milestone/TDEE math in trend.py after every update. A plain class
rather than DataUpdateCoordinator: this is push-driven (state-change events
and a daily timer), not poll-based, so the poll-oriented base class would
just be fought rather than used.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfMass
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import MassConverter

from .const import (
    CONF_ACTIVITY_LEVEL,
    CONF_AGE,
    CONF_GENDER,
    CONF_GOAL_RATE,
    CONF_GOAL_TYPE,
    CONF_GOAL_WEIGHT,
    CONF_HEIGHT_CM,
    CONF_METABOLIC_SOURCE_ENTITY,
    CONF_MILESTONE_COUNT,
    CONF_SOURCE_ENTITY,
    CONF_START_WEIGHT,
    DEFAULT_ACTIVITY_LEVEL,
    DEFAULT_MILESTONE_COUNT,
    DOMAIN,
    GOAL_TYPE_MAINTAIN,
    HISTORY_ATTRIBUTE_MAX_DAYS,
    MAX_STORED_DAYS,
    MIN_LOGGED_DAYS,
    REGRESSION_WINDOW_DAYS,
    SIGNAL_WEIGHT_COACH_UPDATE,
    STORAGE_VERSION,
)
from .trend import (
    Milestone,
    Reading,
    compute_bmr,
    compute_formula_tdee,
    compute_milestones,
    compute_trend_series,
    effective_slope_kg_per_day,
    logged_intake_stats,
    next_milestone as trend_next_milestone,
    next_sunday_after,
    project_date,
    regression_slope_kg_per_day,
    suggest_target,
)

_LOGGER = logging.getLogger(__name__)


class WeightCoachCoordinator:
    """Owns state + math for one coached person."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.source_entity_id: str = entry.data[CONF_SOURCE_ENTITY]
        # Options (post-setup, via the options flow) take precedence over
        # the initial config-entry data, so an existing entry can attach
        # this later without losing its Store history.
        self.metabolic_source_entity_id: str | None = entry.options.get(
            CONF_METABOLIC_SOURCE_ENTITY, entry.data.get(CONF_METABOLIC_SOURCE_ENTITY)
        )
        self.gender: str = entry.data[CONF_GENDER]
        self.age: int = entry.data[CONF_AGE]
        self.height_cm: float = entry.data[CONF_HEIGHT_CM]
        self.goal_type: str = entry.data[CONF_GOAL_TYPE]
        self.milestone_count: int = entry.data.get(CONF_MILESTONE_COUNT, DEFAULT_MILESTONE_COUNT)
        self.goal_start_weight_kg: float = entry.data[CONF_START_WEIGHT]

        # Mutable "current" state. Live-editable via number/select entities,
        # so it's Store-backed (not config-entry options) - options changes
        # reload the whole entry, which would otherwise wipe these on every
        # edit. Config-entry data only supplies the first-run default.
        self.goal_weight_kg: float = entry.data[CONF_GOAL_WEIGHT]
        self.goal_rate_kg_week: float = entry.data[CONF_GOAL_RATE]
        self.activity_level: str = entry.data.get(CONF_ACTIVITY_LEVEL, DEFAULT_ACTIVITY_LEVEL)
        self.active_target_kcal: float | None = None

        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._readings: list[Reading] = []
        self._metabolic_readings: list[Reading] = []
        self._intake_log: dict[str, float] = {}
        self._target_log: list[dict[str, Any]] = []

        # Derived state, refreshed by _recompute().
        self.trend_kg: float | None = None
        self.actual_rate_kg_week: float | None = None
        self.tdee_estimate: float | None = None
        self.tdee_source: str | None = None
        self.suggested_target_kcal: float | None = None
        self.milestones: list[Milestone] = []
        self.next_milestone: Milestone | None = None
        self.projected_end_date: date | None = None
        self.last_reading_source: str | None = None
        self.next_checkin_date: date | None = None
        self.days_until_checkin: int | None = None
        self.latest_metabolic_kcal: float | None = None

        self._unsub_state: Callable[[], None] | None = None
        self._unsub_metabolic: Callable[[], None] | None = None
        self._unsub_daily: Callable[[], None] | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def async_start(self) -> None:
        await self._async_load()
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.source_entity_id], self._handle_source_event
        )
        if self.metabolic_source_entity_id:
            self._unsub_metabolic = async_track_state_change_event(
                self.hass, [self.metabolic_source_entity_id], self._handle_metabolic_source_event
            )
        self._unsub_daily = async_track_time_change(
            self.hass, self._handle_daily_tick, hour=0, minute=0, second=0
        )

    async def async_stop(self) -> None:
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_metabolic is not None:
            self._unsub_metabolic()
            self._unsub_metabolic = None
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None

    async def _async_load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._readings = [
                Reading(
                    ts=datetime.fromisoformat(r["ts"]),
                    weight_kg=r["weight_kg"],
                    source=r.get("source", "sensor"),
                )
                for r in stored.get("readings", [])
            ]
            self._metabolic_readings = [
                # Reusing Reading for a kcal series too rather than adding a
                # near-identical dataclass - .weight_kg just holds kcal here.
                Reading(
                    ts=datetime.fromisoformat(r["ts"]),
                    weight_kg=r["kcal"],
                    source=r.get("source", "sensor"),
                )
                for r in stored.get("metabolic_readings", [])
            ]
            self._intake_log = dict(stored.get("intake_log", {}))
            self._target_log = list(stored.get("target_log", []))
            self.goal_weight_kg = stored.get("goal_weight_kg", self.goal_weight_kg)
            self.goal_rate_kg_week = stored.get("goal_rate_kg_week", self.goal_rate_kg_week)
            self.activity_level = stored.get("activity_level", self.activity_level)
            self.active_target_kcal = stored.get("active_target_kcal")
            self.next_checkin_date = (
                date.fromisoformat(stored["next_checkin_date"])
                if stored.get("next_checkin_date")
                else None
            )
            if self._metabolic_readings:
                self.latest_metabolic_kcal = self._metabolic_readings[-1].weight_kg
        self._recompute()
        # Always persist after load: this may be a brand-new entry, or a
        # catch-up check-in that ran because HA was offline through a
        # scheduled Sunday (which advances next_checkin_date without
        # necessarily changing active_target_kcal) - simplest to just always
        # save rather than infer which fields changed.
        self._async_save()

    def _async_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 10)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "version": STORAGE_VERSION,
            "readings": [
                {"ts": r.ts.isoformat(), "weight_kg": r.weight_kg, "source": r.source}
                for r in self._readings
            ],
            "metabolic_readings": [
                {"ts": r.ts.isoformat(), "kcal": r.weight_kg, "source": r.source}
                for r in self._metabolic_readings
            ],
            "intake_log": self._intake_log,
            "target_log": self._target_log,
            "goal_weight_kg": self.goal_weight_kg,
            "goal_rate_kg_week": self.goal_rate_kg_week,
            "activity_level": self.activity_level,
            "active_target_kcal": self.active_target_kcal,
            "next_checkin_date": self.next_checkin_date.isoformat()
            if self.next_checkin_date
            else None,
        }

    @callback
    def _async_dispatch(self) -> None:
        async_dispatcher_send(
            self.hass, SIGNAL_WEIGHT_COACH_UPDATE.format(entry_id=self.entry.entry_id)
        )

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    @callback
    def _handle_source_event(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            raw_value = float(new_state.state)
        except ValueError:
            return
        unit = new_state.attributes.get("unit_of_measurement")
        weight_kg = self._to_kg(raw_value, unit)
        self.hass.async_create_task(
            self.async_ingest_weight(weight_kg, source="sensor"),
            f"weight_coach ingest {self.entry.entry_id}",
        )

    @staticmethod
    def _to_kg(value: float, unit: str | None) -> float:
        if unit in (None, UnitOfMass.KILOGRAMS):
            return value
        return MassConverter.convert(value, unit, UnitOfMass.KILOGRAMS)

    async def async_ingest_weight(
        self, weight_kg: float, ts: datetime | None = None, source: str = "sensor"
    ) -> None:
        """Record a new weight reading - from the source sensor OR manual entry.

        Both paths share this method so trend/regression/milestones treat a
        manual fallback entry identically to an automatic one.
        """
        self._readings.append(Reading(ts=ts or dt_util.utcnow(), weight_kg=weight_kg, source=source))
        self._prune_readings()
        self._recompute()
        self._async_save()
        self._async_dispatch()

    def _prune_readings(self) -> None:
        by_day: dict[date, Reading] = {}
        for reading in sorted(self._readings, key=lambda r: r.ts):
            # Group by the user's local day, not the UTC date, so a late-
            # evening weigh-in doesn't get bucketed into the wrong day.
            by_day[dt_util.as_local(reading.ts).date()] = reading  # last of each day wins
        pruned = sorted(by_day.values(), key=lambda r: r.ts)
        if len(pruned) > MAX_STORED_DAYS:
            pruned = pruned[-MAX_STORED_DAYS:]
        self._readings = pruned

    @callback
    def _handle_metabolic_source_event(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            kcal = float(new_state.state)
        except ValueError:
            return
        self.hass.async_create_task(
            self.async_ingest_metabolic_reading(kcal),
            f"weight_coach ingest metabolic {self.entry.entry_id}",
        )

    async def async_ingest_metabolic_reading(self, kcal: float, ts: datetime | None = None) -> None:
        """Record a raw metabolic-rate reading from the (optional) second source.

        Independent of the weight trend/check-in pipeline - just its own
        light history bookkeeping for later graphing.
        """
        self._metabolic_readings.append(Reading(ts=ts or dt_util.utcnow(), weight_kg=kcal))
        self._prune_metabolic_readings()
        self.latest_metabolic_kcal = self._metabolic_readings[-1].weight_kg
        self._async_save()
        self._async_dispatch()

    def _prune_metabolic_readings(self) -> None:
        by_day: dict[date, Reading] = {}
        for reading in sorted(self._metabolic_readings, key=lambda r: r.ts):
            by_day[dt_util.as_local(reading.ts).date()] = reading
        pruned = sorted(by_day.values(), key=lambda r: r.ts)
        if len(pruned) > MAX_STORED_DAYS:
            pruned = pruned[-MAX_STORED_DAYS:]
        self._metabolic_readings = pruned

    async def async_log_intake(self, calories: float, day: date | None = None) -> None:
        """Log a day's total calorie intake. Re-logging the same day overwrites it."""
        day = day or dt_util.now().date()
        self._intake_log[day.isoformat()] = calories
        self._prune_intake()
        self._recompute()
        self._async_save()
        self._async_dispatch()

    def _prune_intake(self) -> None:
        if len(self._intake_log) <= MAX_STORED_DAYS:
            return
        oldest = sorted(self._intake_log.keys())[: len(self._intake_log) - MAX_STORED_DAYS]
        for key in oldest:
            del self._intake_log[key]

    def get_intake_for_date(self, day: date) -> float | None:
        return self._intake_log.get(day.isoformat())

    async def async_set_goal_weight(self, value: float) -> None:
        self.goal_weight_kg = value
        # A goal change is a deliberate plan change, not a noisy data point -
        # reflect it in the suggestion immediately rather than waiting for
        # the next scheduled Sunday check-in.
        self._recompute(force_checkin=True)
        self._async_save()
        self._async_dispatch()

    async def async_set_goal_rate(self, value: float) -> None:
        self.goal_rate_kg_week = value
        self._recompute(force_checkin=True)
        self._async_save()
        self._async_dispatch()

    async def async_set_activity_level(self, value: str) -> None:
        self.activity_level = value
        self._recompute(force_checkin=True)
        self._async_save()
        self._async_dispatch()

    async def async_accept_suggested_target(self) -> None:
        """Promote the suggested target to active, logging the acceptance.

        This is the only path that changes active_target_kcal - the target_log
        entry it appends becomes the baseline the next Tier-1 recalibration's
        error is computed against.
        """
        if self.suggested_target_kcal is None:
            return
        if self.suggested_target_kcal == self.active_target_kcal:
            return  # nothing to accept
        self.active_target_kcal = self.suggested_target_kcal
        self._target_log.append(
            {
                "ts": dt_util.utcnow().isoformat(),
                "calories": self.active_target_kcal,
                "reason": "manual_accept",
                "tdee_source": self.tdee_source,
                "trend_kg": self.trend_kg,
                "trend_rate_kg_week": self.actual_rate_kg_week,
                "goal_rate_kg_week": self.goal_rate_kg_week,
            }
        )
        if len(self._target_log) > MAX_STORED_DAYS:
            self._target_log = self._target_log[-MAX_STORED_DAYS:]
        self._recompute()
        self._async_save()
        self._async_dispatch()

    @callback
    def _handle_daily_tick(self, now: datetime) -> None:
        """Refresh day-relative values (projections, milestone dates, the
        calories-consumed-today display rolling over) even if no new weight
        or intake data has come in."""
        self._recompute()
        self._async_dispatch()

    # ------------------------------------------------------------------ #
    # Math
    # ------------------------------------------------------------------ #

    def _recompute(self, force_checkin: bool = False) -> None:
        """Refresh continuous status every call; the calorie-target
        suggestion only on the weekly Sunday check-in (or when forced by a
        deliberate goal/activity change - see the setters above)."""
        today = dt_util.now().date()
        slope_kg_per_day = self._recompute_status(today)

        checkin_due = (
            self.next_checkin_date is None
            or today >= self.next_checkin_date
            or force_checkin
        )
        if checkin_due:
            self._recompute_checkin(today, slope_kg_per_day)

        self.days_until_checkin = max(0, (self.next_checkin_date - today).days)

    def _recompute_status(self, today: date) -> float | None:
        """Trend, actual rate, and date projections. Always runs.

        Returns the raw regression slope (kg/day, or None if there isn't
        enough history yet) for _recompute_checkin to use - projections use
        an effective (goal-rate-fallback) slope instead, computed here.
        """
        now = dt_util.utcnow()

        trend_series = compute_trend_series(self._readings)
        if trend_series:
            self.trend_kg = trend_series[-1].trend_kg
            self.last_reading_source = self._readings[-1].source if self._readings else None
        else:
            self.trend_kg = None
            self.last_reading_source = None

        slope_kg_per_day = (
            regression_slope_kg_per_day(trend_series, now) if trend_series else None
        )
        self.actual_rate_kg_week = slope_kg_per_day * 7 if slope_kg_per_day is not None else None

        if self.goal_type == GOAL_TYPE_MAINTAIN:
            self.projected_end_date = None
            self.milestones = []
            self.next_milestone = None
        else:
            # Before there's enough regression data (or even any readings
            # at all), project using the goal's own target rate from the
            # starting weight, so there's a sensible date from day one. This
            # shifts onto the real trend once regression_slope_kg_per_day
            # starts returning a value.
            anchor_weight = (
                self.trend_kg if self.trend_kg is not None else self.goal_start_weight_kg
            )
            effective_slope = effective_slope_kg_per_day(slope_kg_per_day, self.goal_rate_kg_week)
            self.projected_end_date = project_date(
                anchor_weight, self.goal_weight_kg, effective_slope, today
            )
            self.milestones = compute_milestones(
                self.goal_start_weight_kg,
                self.goal_weight_kg,
                self.milestone_count,
                anchor_weight,
                effective_slope,
                today,
            )
            self.next_milestone = trend_next_milestone(self.milestones)

        return slope_kg_per_day

    def _recompute_checkin(self, today: date, slope_kg_per_day: float | None) -> None:
        """TDEE + suggested calorie target. Only runs on a check-in day."""
        now = dt_util.utcnow()

        weight_for_bmr = self.trend_kg if self.trend_kg is not None else self.goal_start_weight_kg
        bmr = compute_bmr(weight_for_bmr, self.height_cm, self.age, self.gender)
        formula_tdee = compute_formula_tdee(bmr, self.activity_level)

        window_start = today - timedelta(days=REGRESSION_WINDOW_DAYS)
        logged_days, avg_intake = logged_intake_stats(self._intake_log, window_start, today)

        suggestion = suggest_target(
            formula_tdee=formula_tdee,
            bmr=bmr,
            active_target_kcal=self.active_target_kcal,
            goal_rate_kg_week=self.goal_rate_kg_week,
            actual_rate_kg_week=self.actual_rate_kg_week,
            logged_days_in_window=logged_days,
            avg_intake_kcal=avg_intake,
            slope_kg_per_day=slope_kg_per_day,
            min_logged_days=MIN_LOGGED_DAYS,
        )
        self.suggested_target_kcal = suggestion.suggested_kcal
        self.tdee_estimate = suggestion.tdee_estimate
        self.tdee_source = suggestion.tdee_source

        if self.active_target_kcal is None:
            # First run: seed the active target directly from the initial
            # suggestion so there's something to display before anyone has
            # pressed accept, and log it as the "initial" baseline.
            self.active_target_kcal = suggestion.suggested_kcal
            self._target_log.append(
                {
                    "ts": now.isoformat(),
                    "calories": self.active_target_kcal,
                    "reason": "initial",
                    "tdee_source": self.tdee_source,
                    "trend_kg": self.trend_kg,
                    "trend_rate_kg_week": self.actual_rate_kg_week,
                    "goal_rate_kg_week": self.goal_rate_kg_week,
                }
            )

        self.next_checkin_date = next_sunday_after(today)

    # ------------------------------------------------------------------ #
    # History, for graphing (see const.HISTORY_ATTRIBUTE_MAX_DAYS)
    # ------------------------------------------------------------------ #

    @property
    def weight_history(self) -> list[dict[str, Any]]:
        """Raw readings alongside the smoothed trend, one entry per reading.

        Carries both series so a chart can plot raw scatter points against
        the trend line from a single data source.
        """
        window_start = dt_util.now().date() - timedelta(days=HISTORY_ATTRIBUTE_MAX_DAYS)
        trend_series = compute_trend_series(self._readings)
        trend_by_ts = {point.ts: point.trend_kg for point in trend_series}
        history: list[dict[str, Any]] = []
        for reading in self._readings:
            local_date = dt_util.as_local(reading.ts).date()
            if local_date < window_start:
                continue
            history.append(
                {
                    "date": local_date.isoformat(),
                    "raw_weight_kg": round(reading.weight_kg, 2),
                    "trend_kg": round(trend_by_ts.get(reading.ts, reading.weight_kg), 2),
                    "source": reading.source,
                }
            )
        return history

    @property
    def metabolic_history(self) -> list[dict[str, Any]]:
        """Raw metabolic-rate readings, if a source is configured."""
        window_start = dt_util.now().date() - timedelta(days=HISTORY_ATTRIBUTE_MAX_DAYS)
        return [
            {"date": dt_util.as_local(reading.ts).date().isoformat(), "kcal": round(reading.weight_kg)}
            for reading in self._metabolic_readings
            if dt_util.as_local(reading.ts).date() >= window_start
        ]

    @property
    def intake_history(self) -> list[dict[str, Any]]:
        """Logged daily calorie intake."""
        window_start = dt_util.now().date() - timedelta(days=HISTORY_ATTRIBUTE_MAX_DAYS)
        return [
            {"date": day_str, "kcal": kcal}
            for day_str, kcal in sorted(self._intake_log.items())
            if date.fromisoformat(day_str) >= window_start
        ]

    @property
    def target_history(self) -> list[dict[str, Any]]:
        """When the active calorie target changed, to what, and why."""
        window_start = dt_util.now().date() - timedelta(days=HISTORY_ATTRIBUTE_MAX_DAYS)
        history: list[dict[str, Any]] = []
        for entry in self._target_log:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except (KeyError, ValueError):
                continue
            local_date = dt_util.as_local(ts).date()
            if local_date < window_start:
                continue
            history.append(
                {
                    "date": local_date.isoformat(),
                    "kcal": entry.get("calories"),
                    "reason": entry.get("reason"),
                }
            )
        return history
