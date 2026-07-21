"""Select platform for Weight Coach: activity level."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVITY_MULTIPLIERS, DOMAIN, SIGNAL_WEIGHT_COACH_UPDATE
from .coordinator import WeightCoachCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Weight Coach activity-level select."""
    coordinator: WeightCoachCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ActivityLevelSelect(coordinator, entry)])


class ActivityLevelSelect(SelectEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:run"
    _attr_options = list(ACTIVITY_MULTIPLIERS)

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_activity_level"
        self._attr_name = "Activity Level"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Weight Coach",
            model="Coaching profile",
        )

    @property
    def current_option(self) -> str:
        return self._coordinator.activity_level

    async def async_select_option(self, option: str) -> None:
        await self._coordinator.async_set_activity_level(option)

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
