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
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. metabolic-rate source).

    Safe to reload: the Store is keyed by entry.entry_id, which a reload
    does not change, so all accumulated history survives.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: WeightCoachCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok
