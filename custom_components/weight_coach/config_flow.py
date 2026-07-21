"""Config flow for the Weight Coach integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import UnitOfMass
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util.unit_conversion import MassConverter

from .const import (
    ACTIVITY_MULTIPLIERS,
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
    GOAL_TYPE_GAIN,
    GOAL_TYPE_LOSE,
    GOAL_TYPE_MAINTAIN,
    GOAL_TYPES,
    MAX_MILESTONE_COUNT,
    MIN_MILESTONE_COUNT,
)

ACTIVITY_LEVEL_GUESS = {"normal": "light", "high": "active"}


def _to_kg(value: float, unit: str | None) -> float:
    if unit in (None, UnitOfMass.KILOGRAMS):
        return value
    return MassConverter.convert(value, unit, UnitOfMass.KILOGRAMS)


class WeightCoachConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weight Coach: one entry per coached person."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._prefill: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick the source weight sensor to coach against."""
        errors: dict[str, str] = {}

        if user_input is not None:
            source_entity_id = user_input[CONF_SOURCE_ENTITY]
            state = self.hass.states.get(source_entity_id)
            if state is None:
                errors["base"] = "source_unavailable"
            else:
                try:
                    start_weight_kg = _to_kg(
                        float(state.state), state.attributes.get("unit_of_measurement")
                    )
                except ValueError:
                    errors["base"] = "source_unavailable"
                else:
                    self._data[CONF_SOURCE_ENTITY] = source_entity_id
                    self._data[CONF_START_WEIGHT] = start_weight_kg
                    self._prefill = dict(state.attributes)
                    return await self.async_step_profile()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="weight")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm sex/age/height, prefilled from the source sensor if it has them."""
        if user_input is not None:
            self._data[CONF_GENDER] = user_input[CONF_GENDER]
            self._data[CONF_AGE] = user_input[CONF_AGE]
            self._data[CONF_HEIGHT_CM] = user_input[CONF_HEIGHT_CM]
            return await self.async_step_goal_type()

        prefill = self._prefill
        return self.async_show_form(
            step_id="profile",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GENDER, default=prefill.get(CONF_GENDER, "male")
                    ): vol.In(["male", "female"]),
                    vol.Required(CONF_AGE, default=prefill.get(CONF_AGE, 30)): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=120)
                    ),
                    vol.Required(
                        CONF_HEIGHT_CM, default=prefill.get(CONF_HEIGHT_CM, 170)
                    ): vol.All(vol.Coerce(float), vol.Range(min=100, max=250)),
                }
            ),
        )

    async def async_step_goal_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Lose / maintain / gain."""
        if user_input is not None:
            self._data[CONF_GOAL_TYPE] = user_input[CONF_GOAL_TYPE]
            if user_input[CONF_GOAL_TYPE] == GOAL_TYPE_MAINTAIN:
                self._data[CONF_GOAL_WEIGHT] = self._data[CONF_START_WEIGHT]
                self._data[CONF_GOAL_RATE] = 0.0
                self._data[CONF_MILESTONE_COUNT] = DEFAULT_MILESTONE_COUNT
                return await self.async_step_activity()
            return await self.async_step_goal_details()

        return self.async_show_form(
            step_id="goal_type",
            data_schema=vol.Schema({vol.Required(CONF_GOAL_TYPE): vol.In(GOAL_TYPES)}),
        )

    async def async_step_goal_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Goal weight, weekly rate, and how many milestones to split it into."""
        errors: dict[str, str] = {}
        goal_type = self._data[CONF_GOAL_TYPE]

        if user_input is not None:
            rate = abs(user_input[CONF_GOAL_RATE])
            start = self._data[CONF_START_WEIGHT]
            goal = user_input[CONF_GOAL_WEIGHT]
            if goal_type == GOAL_TYPE_LOSE and goal >= start:
                errors[CONF_GOAL_WEIGHT] = "goal_must_be_below_start"
            elif goal_type == GOAL_TYPE_GAIN and goal <= start:
                errors[CONF_GOAL_WEIGHT] = "goal_must_be_above_start"
            else:
                self._data[CONF_GOAL_WEIGHT] = goal
                # Store rate signed so downstream math doesn't need goal_type
                # branching: negative for a loss goal, positive for a gain.
                self._data[CONF_GOAL_RATE] = -rate if goal_type == GOAL_TYPE_LOSE else rate
                self._data[CONF_MILESTONE_COUNT] = user_input[CONF_MILESTONE_COUNT]
                return await self.async_step_activity()

        start_weight = self._data[CONF_START_WEIGHT]
        default_goal = start_weight - 5 if goal_type == GOAL_TYPE_LOSE else start_weight + 5

        return self.async_show_form(
            step_id="goal_details",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GOAL_WEIGHT, default=round(default_goal, 1)): vol.All(
                        vol.Coerce(float), vol.Range(min=20, max=400)
                    ),
                    vol.Required(CONF_GOAL_RATE, default=0.5): vol.All(
                        vol.Coerce(float), vol.Range(min=0.05, max=1.5)
                    ),
                    vol.Required(
                        CONF_MILESTONE_COUNT, default=DEFAULT_MILESTONE_COUNT
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_MILESTONE_COUNT, max=MAX_MILESTONE_COUNT)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"start_weight": f"{start_weight:.1f}"},
        )

    async def async_step_activity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Activity level, guessed from the source sensor's attribute if present."""
        if user_input is not None:
            self._data[CONF_ACTIVITY_LEVEL] = user_input[CONF_ACTIVITY_LEVEL]
            title = f"Weight Coach ({self._data[CONF_GOAL_TYPE]})"
            return self.async_create_entry(title=title, data=self._data)

        prefill_raw = self._prefill.get("activity_level")
        default_level = ACTIVITY_LEVEL_GUESS.get(prefill_raw, DEFAULT_ACTIVITY_LEVEL)

        return self.async_show_form(
            step_id="activity",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACTIVITY_LEVEL, default=default_level): vol.In(
                        list(ACTIVITY_MULTIPLIERS)
                    ),
                }
            ),
        )
