"""Number platform for Weight Coach: goal weight/rate, calorie logging, manual weight fallback."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_WEIGHT_COACH_UPDATE
from .coordinator import WeightCoachCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weight Coach number entities."""
    coordinator: WeightCoachCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GoalWeightNumber(coordinator, entry),
            GoalRateNumber(coordinator, entry),
            CaloriesConsumedTodayNumber(coordinator, entry),
            ManualWeightEntryNumber(coordinator, entry),
        ]
    )


class WeightCoachNumberBase(NumberEntity):
    """Shared device info + push-update wiring for all Weight Coach numbers."""

    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: WeightCoachCoordinator, entry: ConfigEntry, key: str, name: str
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Weight Coach",
            model="Coaching profile",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_WEIGHT_COACH_UPDATE.format(entry_id=self._entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class GoalWeightNumber(WeightCoachNumberBase):
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_native_min_value = 20
    _attr_native_max_value = 400
    _attr_native_step = 0.1
    _attr_icon = "mdi:bullseye-arrow"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "goal_weight", "Goal Weight")

    @property
    def native_value(self) -> float:
        return self._coordinator.goal_weight_kg

    async def async_set_native_value(self, value: float) -> None:
        await self._coordinator.async_set_goal_weight(value)


class GoalRateNumber(WeightCoachNumberBase):
    """Signed weekly rate: negative = losing, positive = gaining, 0 = maintain."""

    _attr_native_unit_of_measurement = "kg/wk"
    _attr_native_min_value = -2.0
    _attr_native_max_value = 2.0
    _attr_native_step = 0.05
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "goal_weekly_rate", "Goal Weekly Rate")

    @property
    def native_value(self) -> float:
        return self._coordinator.goal_rate_kg_week

    async def async_set_native_value(self, value: float) -> None:
        await self._coordinator.async_set_goal_rate(value)


class CaloriesConsumedTodayNumber(WeightCoachNumberBase):
    """Enter once, at the end of the day. Displayed value naturally clears at
    local midnight since it reads straight from today's log entry, which
    starts out empty for the new day."""

    _attr_native_unit_of_measurement = "kcal"
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 10
    _attr_icon = "mdi:food-apple"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "calories_consumed_today", "Calories Consumed Today")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.get_intake_for_date(dt_util.now().date())

    async def async_set_native_value(self, value: float) -> None:
        await self._coordinator.async_log_intake(value, day=dt_util.now().date())


class ManualWeightEntryNumber(WeightCoachNumberBase):
    """Fallback for when the automatic source sensor doesn't update (BLE
    failure, out of range, etc). Feeds the same ingestion path as the
    automatic reading, tagged source="manual" for transparency."""

    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_native_min_value = 20
    _attr_native_max_value = 400
    _attr_native_step = 0.1
    _attr_icon = "mdi:scale-bathroom"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "manual_weight_entry", "Manual Weight Entry")
        self._last_value: float | None = None

    @property
    def native_value(self) -> float | None:
        return self._last_value

    async def async_set_native_value(self, value: float) -> None:
        self._last_value = value
        await self._coordinator.async_ingest_weight(value, source="manual")
