"""The Weight Coach integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WeightCoachCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Weight Coach from a config entry."""
    coordinator = WeightCoachCoordinator(hass, entry)
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: WeightCoachCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok
