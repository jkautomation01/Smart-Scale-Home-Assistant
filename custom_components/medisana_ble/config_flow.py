"""Config flow for the Medisana BLE Scale integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_PERSON_NAME_PREFIX, CONF_TIME_OFFSET, DEFAULT_NAME, DOMAIN, MAX_PERSON_SLOTS


class MedisanaBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Medisana BLE Scale."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: bluetooth.BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a discovery triggered by Home Assistant's Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a Bluetooth discovery."""
        assert self._discovery_info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or self._discovery_info.address,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: self._discovery_info.name or DEFAULT_NAME,
                },
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a manually-initiated setup: pick a seen device or type a MAC."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input.get(CONF_NAME)
                or self._discovered_devices.get(address)
                or DEFAULT_NAME,
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                },
            )

        current_addresses = self._async_current_ids()
        for discovery in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if discovery.address in current_addresses:
                continue
            self._discovered_devices[discovery.address] = (
                discovery.name or discovery.address
            )

        if self._discovered_devices:
            address_schema = vol.In(self._discovered_devices)
        else:
            # Nothing seen yet (e.g. the scale only advertises briefly right
            # after a weigh-in) - fall back to typing the MAC address in
            # directly, as printed on/near the scale's battery compartment
            # or found via any BLE scanner app.
            address_schema = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): address_schema,
                    vol.Optional(CONF_NAME): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MedisanaBLEOptionsFlow:
        """Get the options flow for this handler."""
        return MedisanaBLEOptionsFlow()


class MedisanaBLEOptionsFlow(config_entries.OptionsFlow):
    """Configure person slots (1-8) and clock-offset behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            options: dict[str, Any] = {CONF_TIME_OFFSET: user_input[CONF_TIME_OFFSET]}
            for slot in range(1, MAX_PERSON_SLOTS + 1):
                key = f"{CONF_PERSON_NAME_PREFIX}{slot}"
                name = user_input.get(key, "").strip()
                if name:
                    options[key] = name
            return self.async_create_entry(title="", data=options)

        current = self.config_entry.options
        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_TIME_OFFSET, default=current.get(CONF_TIME_OFFSET, True)
            ): bool,
        }
        for slot in range(1, MAX_PERSON_SLOTS + 1):
            key = f"{CONF_PERSON_NAME_PREFIX}{slot}"
            schema_dict[vol.Optional(key, default=current.get(key, ""))] = str

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict)
        )
