"""BLE connection handling for the Medisana BLE Scale integration.

Connections are made through Home Assistant's own `bluetooth` integration
(`bluetooth.async_ble_device_from_address`), so whatever adapter or remote
ESPHome Bluetooth proxy you've already configured in Home Assistant is what
gets used here - there is no separate/second Bluetooth stack involved.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import struct
import time
from typing import Any

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTIVITY_LABELS,
    CHAR_BODY_UUID,
    CHAR_COMMAND_UUID,
    CHAR_PERSON_UUID,
    CHAR_WEIGHT_UUID,
    COMMAND_SET_TIMESTAMP,
    CONF_PERSON_NAME_PREFIX,
    CONF_TIME_OFFSET,
    EPOCH_2010_OFFSET,
    GENDER_LABELS,
    MAX_PERSON_SLOTS,
    MEASUREMENT_TIMEOUT,
    MIN_RECONNECT_INTERVAL,
    QUIET_PERIOD,
    SIGNAL_MEDISANA_DATA,
)
from .parser import BodyRecord, PersonRecord, WeightRecord, parse_body, parse_person, parse_weight, sanitize_timestamp

_LOGGER = logging.getLogger(__name__)


class MedisanaBLECoordinator:
    """Owns the Bluetooth callback + GATT connection lifecycle for one scale."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data["address"]
        self.data: dict[int, dict[str, Any]] = {}

        self.persons: dict[int, str] = {}
        for slot in range(1, MAX_PERSON_SLOTS + 1):
            name = entry.options.get(f"{CONF_PERSON_NAME_PREFIX}{slot}")
            if name:
                self.persons[slot] = name

        self.use_2010_epoch: bool = entry.options.get(CONF_TIME_OFFSET, True)

        self._unregister_callback: callback | None = None
        self._connect_lock = asyncio.Lock()
        self._last_connect_attempt = 0.0

    async def async_start(self) -> None:
        """Start listening for advertisements from the configured scale."""
        self._unregister_callback = bluetooth.async_register_callback(
            self.hass,
            self._async_advertisement_seen,
            bluetooth.BluetoothCallbackMatcher(address=self.address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

    async def async_stop(self) -> None:
        """Stop listening for advertisements."""
        if self._unregister_callback is not None:
            self._unregister_callback()
            self._unregister_callback = None

    @callback
    def _async_advertisement_seen(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        now = time.monotonic()
        if now - self._last_connect_attempt < MIN_RECONNECT_INTERVAL:
            return
        self._last_connect_attempt = now
        self.hass.async_create_task(
            self._async_connect_and_read(), f"medisana_ble read {self.address}"
        )

    async def _async_connect_and_read(self) -> None:
        if self._connect_lock.locked():
            _LOGGER.debug("Already connecting to %s, skipping", self.address)
            return

        async with self._connect_lock:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                _LOGGER.debug(
                    "Scale %s seen but not currently connectable", self.address
                )
                return

            try:
                client = await establish_connection(
                    BleakClient, ble_device, ble_device.name or self.address
                )
            except Exception as err:  # noqa: BLE001 - log and retry on next advert
                _LOGGER.warning(
                    "Failed to connect to Medisana scale %s: %s", self.address, err
                )
                return

            persons: dict[int, PersonRecord] = {}
            weights: dict[int, WeightRecord] = {}
            bodies: dict[int, BodyRecord] = {}
            received = asyncio.Event()

            def _on_person(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Person payload from %s: %s", self.address, data.hex())
                record = parse_person(bytes(data))
                if record is not None:
                    persons[record.person_id] = record
                    received.set()

            def _on_weight(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Weight payload from %s: %s", self.address, data.hex())
                record = parse_weight(bytes(data))
                if record is not None:
                    existing = weights.get(record.person_id)
                    if existing is None or record.timestamp > existing.timestamp:
                        weights[record.person_id] = record
                    received.set()

            def _on_body(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Body payload from %s: %s", self.address, data.hex())
                record = parse_body(bytes(data))
                if record is not None:
                    existing = bodies.get(record.person_id)
                    if existing is None or record.timestamp > existing.timestamp:
                        bodies[record.person_id] = record
                    received.set()

            try:
                await client.start_notify(CHAR_PERSON_UUID, _on_person)
                await client.start_notify(CHAR_WEIGHT_UUID, _on_weight)
                await client.start_notify(CHAR_BODY_UUID, _on_body)

                now_ts = int(time.time())
                if self.use_2010_epoch:
                    now_ts -= EPOCH_2010_OFFSET
                command = bytes([COMMAND_SET_TIMESTAMP]) + struct.pack("<I", now_ts)
                await client.write_gatt_char(CHAR_COMMAND_UUID, command, response=True)

                try:
                    await asyncio.wait_for(
                        self._async_wait_for_complete(weights, bodies, received),
                        timeout=MEASUREMENT_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "Timed out waiting for a full measurement from %s",
                        self.address,
                    )
            finally:
                await client.disconnect()

            if weights:
                self._async_process_results(persons, weights, bodies)

    @staticmethod
    async def _async_wait_for_complete(
        weights: dict[int, WeightRecord],
        bodies: dict[int, BodyRecord],
        received: asyncio.Event,
    ) -> None:
        """Wait out the scale's replay burst, then confirm we have a pair.

        The scale sends its stored history as a burst of notifications, not
        just the latest reading, so stopping at the first weight+body match
        can return a stale record instead of the current weigh-in. Instead,
        wait for QUIET_PERIOD seconds of silence (no new notification) so
        the whole burst has arrived, keeping only the highest-timestamped
        record per person (see _on_weight/_on_body), then finish once at
        least one person has both a weight and a body-composition record.
        """
        while True:
            try:
                await asyncio.wait_for(received.wait(), timeout=QUIET_PERIOD)
            except asyncio.TimeoutError:
                if weights and bodies and weights.keys() & bodies.keys():
                    return
                # No data of any kind yet - keep waiting for the burst to
                # start; the outer MEASUREMENT_TIMEOUT bounds the total wait.
                continue
            else:
                received.clear()

    def _async_process_results(
        self,
        persons: dict[int, PersonRecord],
        weights: dict[int, WeightRecord],
        bodies: dict[int, BodyRecord],
    ) -> None:
        for person_id, weight in weights.items():
            body = bodies.get(person_id)
            if body is None:
                _LOGGER.debug(
                    "Got a weight for person %s from %s but no body-composition "
                    "reading, skipping this update",
                    person_id,
                    self.address,
                )
                continue

            person = persons.get(person_id)
            timestamp = sanitize_timestamp(weight.timestamp, self.use_2010_epoch)
            measured_at_iso = datetime.fromtimestamp(
                timestamp, tz=timezone.utc
            ).isoformat()

            if person_id not in self.persons:
                _LOGGER.warning(
                    "Received a measurement for scale person slot %s on %s, but "
                    "no name is configured for that slot. Add it in the "
                    "integration's options to get sensors for this person.",
                    person_id,
                    self.address,
                )

            self.data[person_id] = {
                "weight_kg": weight.weight_kg,
                "kcal": body.kcal,
                "fat_percent": body.fat_percent,
                "water_percent": body.water_percent,
                "muscle_percent": body.muscle_percent,
                "bone_mass_kg": body.bone_mass_kg,
                "measured_at_iso": measured_at_iso,
                "gender": GENDER_LABELS.get(person.gender) if person else None,
                "age": person.age if person else None,
                "height_cm": person.height_cm if person else None,
                "activity_level": (
                    ACTIVITY_LABELS.get(person.activity_level, person.activity_level)
                    if person
                    else None
                ),
            }

        async_dispatcher_send(
            self.hass, SIGNAL_MEDISANA_DATA.format(entry_id=self.entry.entry_id)
        )
