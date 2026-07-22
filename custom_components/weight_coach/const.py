"""Constants for the Weight Coach integration."""
from __future__ import annotations

DOMAIN = "weight_coach"
DEFAULT_NAME = "Weight Coach"

STORAGE_VERSION = 1

CONF_SOURCE_ENTITY = "source_entity_id"
CONF_GENDER = "gender"
CONF_AGE = "age"
CONF_HEIGHT_CM = "height_cm"
CONF_GOAL_TYPE = "goal_type"
CONF_GOAL_WEIGHT = "goal_weight_kg"
CONF_GOAL_RATE = "goal_rate_kg_week"
CONF_MILESTONE_COUNT = "milestone_count"
CONF_ACTIVITY_LEVEL = "activity_level"
CONF_START_WEIGHT = "goal_start_weight_kg"
CONF_METABOLIC_SOURCE_ENTITY = "metabolic_source_entity_id"

GOAL_TYPE_LOSE = "lose"
GOAL_TYPE_MAINTAIN = "maintain"
GOAL_TYPE_GAIN = "gain"
GOAL_TYPES = (GOAL_TYPE_LOSE, GOAL_TYPE_MAINTAIN, GOAL_TYPE_GAIN)

# Mifflin-St Jeor activity multipliers.
ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}
DEFAULT_ACTIVITY_LEVEL = "moderate"

# kcal per kg of body fat/mass, the standard estimate used throughout the
# energy-balance math (deficit/surplus sizing, implied-TDEE back-calculation).
KCAL_PER_KG = 7700

# Trend smoothing: continuous-time EMA time constant. Larger = smoother but
# slower to reflect a real change; smaller = tracks day-to-day noise more.
TAU_DAYS = 7
# A gap longer than this makes the old trend too stale to blend algebraically
# with a new reading - reset instead of smoothing across the gap.
MAX_GAP_DAYS = 30

# Trailing window for the rate-of-change regression and for counting logged
# intake days towards Tier 2 TDEE.
REGRESSION_WINDOW_DAYS = 21
MIN_REGRESSION_READINGS = 5
MIN_REGRESSION_SPAN_DAYS = 7

# Tier 2 (implied TDEE from logged intake) only activates once at least this
# many distinct days have a logged intake entry within REGRESSION_WINDOW_DAYS.
# This is a threshold, not a requirement to log every day - occasional missed
# days never disable it, and having none at all just keeps Tier 1 active.
MIN_LOGGED_DAYS = 10

# Weekly recalibration proportional-controller gain (Tier 1 only). 0.5 means
# "close half the gap between actual and goal rate per cycle" - weight
# response to a calorie change lags 1-2 weeks, so fully correcting a single
# week's error tends to overshoot and oscillate.
KP = 0.5

# Safety caps applied to the suggested calorie target regardless of tier.
MAX_ADJUSTMENT_KCAL = 250  # max change from the active target per cycle
MIN_CALORIE_FLOOR = 1200  # absolute floor regardless of BMR

DEFAULT_MILESTONE_COUNT = 4
MIN_MILESTONE_COUNT = 2
MAX_MILESTONE_COUNT = 10

# Bounded local history: collapse to at most one entry per calendar day, and
# hard-cap total entries so years of daily use stay a trivial amount of data.
MAX_STORED_DAYS = 1095  # ~3 years

# The *attribute* exposed for graphing is windowed separately/more tightly
# than the full internal history above - a year is already generous for
# "the whole journey" and keeps entity attribute payloads reasonable.
HISTORY_ATTRIBUTE_MAX_DAYS = 365

SIGNAL_WEIGHT_COACH_UPDATE = "weight_coach_update_{entry_id}"
