"""Sensor platform for the Medisana BLE Scale integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_MEDISANA_DATA
from .coordinator import MedisanaBLECoordinator


@dataclass(frozen=True, kw_only=True)
class MedisanaSensorDescription(SensorEntityDescription):
    """Describes one per-person sensor derived from coordinator.data."""

    value_key: str = ""
    has_profile_attributes: bool = False


SENSOR_DESCRIPTIONS: tuple[MedisanaSensorDescription, ...] = (
    MedisanaSensorDescription(
        key="weight",
        value_key="weight_kg",
        name="Weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        has_profile_attributes=True,
    ),
    MedisanaSensorDescription(
        key="body_fat",
        value_key="fat_percent",
        name="Body Fat",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:water-percent",
    ),
    MedisanaSensorDescription(
        key="body_water",
        value_key="water_percent",
        name="Body Water",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:water",
    ),
    MedisanaSensorDescription(
        key="muscle_mass",
        value_key="muscle_percent",
        name="Muscle Mass",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:arm-flex",
    ),
    MedisanaSensorDescription(
        key="bone_mass",
        value_key="bone_mass_kg",
        name="Bone Mass",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        icon="mdi:bone",
    ),
    MedisanaSensorDescription(
        key="metabolic_rate",
        value_key="kcal",
        name="Metabolic Rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kcal",
        icon="mdi:fire",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Medisana BLE sensors for each configured person slot."""
    coordinator: MedisanaBLECoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MedisanaBLESensor] = []
    for person_id, person_name in coordinator.persons.items():
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                MedisanaBLESensor(coordinator, entry, person_id, person_name, description)
            )
    async_add_entities(entities)


class MedisanaBLESensor(SensorEntity):
    """A single per-person measurement from a Medisana BLE scale."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: MedisanaBLECoordinator,
        entry: ConfigEntry,
        person_id: int,
        person_name: str,
        description: MedisanaSensorDescription,
    ) -> None:
        self.entity_description = description
        self._coordinator = coordinator
        self._entry = entry
        self._person_id = person_id

        self._attr_unique_id = f"{entry.entry_id}_{person_id}_{description.key}"
        self._attr_name = f"{person_name} {description.name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Medisana",
            model="BS4xx family BLE scale",
        )

    @property
    def native_value(self) -> float | None:
        person_data = self._coordinator.data.get(self._person_id)
        if not person_data:
            return None
        return person_data.get(self.entity_description.value_key)

    @property
    def available(self) -> bool:
        return self._person_id in self._coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None] | None:
        if not self.entity_description.has_profile_attributes:
            return None
        person_data = self._coordinator.data.get(self._person_id)
        if not person_data:
            return None
        return {
            "gender": person_data.get("gender"),
            "age": person_data.get("age"),
            "height_cm": person_data.get("height_cm"),
            "activity_level": person_data.get("activity_level"),
            "measured_at": person_data.get("measured_at_iso"),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_MEDISANA_DATA.format(entry_id=self._entry.entry_id),
                self._handle_coordinator_update,
            )
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
