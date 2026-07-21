"""Button platform for Weight Coach: accept the suggested calorie target."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WeightCoachCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Weight Coach accept-target button."""
    coordinator: WeightCoachCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcceptSuggestedTargetButton(coordinator, entry)])


class AcceptSuggestedTargetButton(ButtonEntity):
    """Promotes the suggested calorie target to active. No-op if they already match."""

    _attr_should_poll = False
    _attr_icon = "mdi:check-circle"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_accept_suggested_target"
        self._attr_name = "Accept Suggested Target"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Weight Coach",
            model="Coaching profile",
        )

    async def async_press(self) -> None:
        await self._coordinator.async_accept_suggested_target()
