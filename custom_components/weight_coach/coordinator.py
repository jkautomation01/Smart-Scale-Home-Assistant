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
    CONF_MILESTONE_COUNT,
    CONF_SOURCE_ENTITY,
    CONF_START_WEIGHT,
    DEFAULT_ACTIVITY_LEVEL,
    DEFAULT_MILESTONE_COUNT,
    DOMAIN,
    GOAL_TYPE_MAINTAIN,
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
    logged_intake_stats,
    next_milestone as trend_next_milestone,
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

        self._unsub_state: Callable[[], None] | None = None
        self._unsub_daily: Callable[[], None] | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def async_start(self) -> None:
        await self._async_load()
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.source_entity_id], self._handle_source_event
        )
        self._unsub_daily = async_track_time_change(
            self.hass, self._handle_daily_tick, hour=0, minute=0, second=0
        )

    async def async_stop(self) -> None:
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
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
            self._intake_log = dict(stored.get("intake_log", {}))
            self._target_log = list(stored.get("target_log", []))
            self.goal_weight_kg = stored.get("goal_weight_kg", self.goal_weight_kg)
            self.goal_rate_kg_week = stored.get("goal_rate_kg_week", self.goal_rate_kg_week)
            self.activity_level = stored.get("activity_level", self.activity_level)
            self.active_target_kcal = stored.get("active_target_kcal")
        self._recompute()
        if not stored or self.active_target_kcal != stored.get("active_target_kcal"):
            # Either a brand-new entry, or _recompute() just seeded the
            # initial active target - persist it now rather than leaving it
            # only in memory until the next ingestion event.
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
            "intake_log": self._intake_log,
            "target_log": self._target_log,
            "goal_weight_kg": self.goal_weight_kg,
            "goal_rate_kg_week": self.goal_rate_kg_week,
            "activity_level": self.activity_level,
            "active_target_kcal": self.active_target_kcal,
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
        self._recompute()
        self._async_save()
        self._async_dispatch()

    async def async_set_goal_rate(self, value: float) -> None:
        self.goal_rate_kg_week = value
        self._recompute()
        self._async_save()
        self._async_dispatch()

    async def async_set_activity_level(self, value: str) -> None:
        self.activity_level = value
        self._recompute()
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

    def _recompute(self) -> None:
        now = dt_util.utcnow()
        today = dt_util.now().date()

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

        if self.goal_type == GOAL_TYPE_MAINTAIN or self.trend_kg is None:
            self.projected_end_date = None
            self.milestones = []
            self.next_milestone = None
        else:
            self.projected_end_date = project_date(
                self.trend_kg, self.goal_weight_kg, slope_kg_per_day, today
            )
            self.milestones = compute_milestones(
                self.goal_start_weight_kg,
                self.goal_weight_kg,
                self.milestone_count,
                self.trend_kg,
                slope_kg_per_day,
                today,
            )
            self.next_milestone = trend_next_milestone(self.milestones)

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
