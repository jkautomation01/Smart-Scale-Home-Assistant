"""Pure math for Weight Coach: trend smoothing, regression, TDEE, milestones.

Kept free of Home Assistant/asyncio/storage concerns so the math can be
reasoned about (and tested) in isolation from the coordinator's I/O glue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math

from .const import (
    ACTIVITY_MULTIPLIERS,
    DEFAULT_ACTIVITY_LEVEL,
    KCAL_PER_KG,
    KP,
    MAX_ADJUSTMENT_KCAL,
    MAX_GAP_DAYS,
    MIN_CALORIE_FLOOR,
    MIN_REGRESSION_READINGS,
    MIN_REGRESSION_SPAN_DAYS,
    REGRESSION_WINDOW_DAYS,
    TAU_DAYS,
)


@dataclass
class Reading:
    """One weight observation, from the automatic source or manual entry."""

    ts: datetime
    weight_kg: float
    source: str = "sensor"


@dataclass
class TrendPoint:
    ts: datetime
    trend_kg: float


@dataclass
class Milestone:
    number: int
    weight_kg: float
    projected_date: date | None
    reached: bool


@dataclass
class TargetSuggestion:
    suggested_kcal: int
    tdee_estimate: int
    tdee_source: str  # "formula" | "logged_intake"


def compute_trend_series(readings: list[Reading]) -> list[TrendPoint]:
    """Replay readings in chronological order into a continuous-time EMA.

    Handles irregular sampling: the smoothing factor depends on the actual
    gap since the previous reading, and a gap longer than MAX_GAP_DAYS resets
    the trend to the new raw reading instead of blending across it.
    """
    ordered = sorted(readings, key=lambda r: r.ts)
    trend: list[TrendPoint] = []
    prev_trend: float | None = None
    prev_ts: datetime | None = None

    for reading in ordered:
        if prev_trend is None or prev_ts is None:
            value = reading.weight_kg
        else:
            gap_days = (reading.ts - prev_ts).total_seconds() / 86400
            if gap_days <= 0:
                continue  # duplicate/out-of-order event, ignore
            if gap_days > MAX_GAP_DAYS:
                value = reading.weight_kg
            else:
                alpha = 1 - math.exp(-gap_days / TAU_DAYS)
                value = prev_trend + alpha * (reading.weight_kg - prev_trend)
        trend.append(TrendPoint(ts=reading.ts, trend_kg=value))
        prev_trend = value
        prev_ts = reading.ts

    return trend


def regression_slope_kg_per_day(
    trend: list[TrendPoint],
    now: datetime,
    window_days: int = REGRESSION_WINDOW_DAYS,
) -> float | None:
    """Least-squares slope of trend-vs-time over a trailing window.

    Returns None ("insufficient data") rather than a noisy/garbage slope
    when there aren't enough points spanning enough time in the window.
    """
    window_start = now - timedelta(days=window_days)
    points = [p for p in trend if window_start <= p.ts <= now]
    if len(points) < MIN_REGRESSION_READINGS:
        return None

    span_days = (points[-1].ts - points[0].ts).total_seconds() / 86400
    if span_days < MIN_REGRESSION_SPAN_DAYS:
        return None

    origin = points[0].ts
    xs = [(p.ts - origin).total_seconds() / 86400 for p in points]
    ys = [p.trend_kg for p in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)

    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return numerator / denominator


def project_date(
    current_trend_kg: float,
    target_kg: float,
    slope_kg_per_day: float | None,
    today: date,
) -> date | None:
    """Project the date the trend reaches target_kg at the current slope.

    None means "not currently converging" - either there's no reliable slope
    yet, or the trend is moving away from the target.
    """
    if slope_kg_per_day is None or slope_kg_per_day == 0:
        return None
    days = (target_kg - current_trend_kg) / slope_kg_per_day
    if days <= 0:
        return None
    return today + timedelta(days=days)


def compute_milestones(
    start_weight_kg: float,
    goal_weight_kg: float,
    milestone_count: int,
    current_trend_kg: float,
    slope_kg_per_day: float | None,
    today: date,
) -> list[Milestone]:
    """Split the start->goal change into milestone_count equal steps."""
    losing = goal_weight_kg < start_weight_kg
    milestones: list[Milestone] = []

    for i in range(1, milestone_count + 1):
        fraction = i / milestone_count
        target = start_weight_kg - fraction * (start_weight_kg - goal_weight_kg)
        reached = current_trend_kg <= target if losing else current_trend_kg >= target
        projected = (
            None if reached else project_date(current_trend_kg, target, slope_kg_per_day, today)
        )
        milestones.append(
            Milestone(number=i, weight_kg=round(target, 1), projected_date=projected, reached=reached)
        )

    return milestones


def next_milestone(milestones: list[Milestone]) -> Milestone | None:
    for milestone in milestones:
        if not milestone.reached:
            return milestone
    return milestones[-1] if milestones else None


def compute_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor BMR."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender == "male" else base - 161


def compute_formula_tdee(bmr: float, activity_level: str) -> float:
    multiplier = ACTIVITY_MULTIPLIERS.get(
        activity_level, ACTIVITY_MULTIPLIERS[DEFAULT_ACTIVITY_LEVEL]
    )
    return bmr * multiplier


def compute_implied_tdee(avg_intake_kcal: float, slope_kg_per_day: float) -> float:
    """Back-calculate TDEE from the energy-balance identity.

    change_in_stores (kcal) = calories_in - calories_out, over the window:
    avg_intake - implied_tdee ~= slope_kg_per_day * KCAL_PER_KG
    """
    return avg_intake_kcal - (slope_kg_per_day * KCAL_PER_KG)


def logged_intake_stats(
    intake_log: dict[str, float], window_start: date, window_end: date
) -> tuple[int, float | None]:
    """Count of logged days and their average, within [window_start, window_end]."""
    values = [
        kcal
        for day_str, kcal in intake_log.items()
        if window_start <= date.fromisoformat(day_str) <= window_end
    ]
    if not values:
        return 0, None
    return len(values), sum(values) / len(values)


def suggest_target(
    *,
    formula_tdee: float,
    bmr: float,
    active_target_kcal: float | None,
    goal_rate_kg_week: float,
    actual_rate_kg_week: float | None,
    logged_days_in_window: int,
    avg_intake_kcal: float | None,
    slope_kg_per_day: float | None,
    min_logged_days: int,
) -> TargetSuggestion:
    """Two-tier suggested calorie target - see const.py for the tunables.

    Tier 2 (implied TDEE from logged intake) is used once enough days are
    logged in the trailing window; otherwise Tier 1 (formula TDEE, with an
    outcome-based proportional correction once a trend rate exists) is the
    always-available fallback. Neither branch requires unbroken daily
    logging or raises on missing data - both degrade to simpler math instead.
    """
    use_implied = (
        logged_days_in_window >= min_logged_days
        and avg_intake_kcal is not None
        and slope_kg_per_day is not None
    )

    if use_implied:
        tdee_estimate = compute_implied_tdee(avg_intake_kcal, slope_kg_per_day)
        tdee_source = "logged_intake"
        suggested = tdee_estimate + goal_rate_kg_week * KCAL_PER_KG / 7
    elif active_target_kcal is None or actual_rate_kg_week is None:
        # No active target yet, or not enough weight history for a rate -
        # this is the initial suggestion, not a weekly recalibration.
        tdee_estimate = formula_tdee
        tdee_source = "formula"
        suggested = formula_tdee + goal_rate_kg_week * KCAL_PER_KG / 7
    else:
        tdee_estimate = formula_tdee
        tdee_source = "formula"
        error_kg_week = goal_rate_kg_week - actual_rate_kg_week
        suggested = active_target_kcal + error_kg_week * KCAL_PER_KG / 7 * KP

    floor = max(MIN_CALORIE_FLOOR, bmr)
    ceiling = formula_tdee + 1000
    suggested = max(floor, min(ceiling, suggested))

    if active_target_kcal is not None:
        step = suggested - active_target_kcal
        if step > MAX_ADJUSTMENT_KCAL:
            suggested = active_target_kcal + MAX_ADJUSTMENT_KCAL
        elif step < -MAX_ADJUSTMENT_KCAL:
            suggested = active_target_kcal - MAX_ADJUSTMENT_KCAL

    return TargetSuggestion(
        suggested_kcal=round(suggested),
        tdee_estimate=round(tdee_estimate),
        tdee_source=tdee_source,
    )
