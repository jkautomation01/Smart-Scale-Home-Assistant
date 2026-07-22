"""Sensor platform for Weight Coach: read-only trend/projection/target values."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_WEIGHT_COACH_UPDATE
from .coordinator import WeightCoachCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weight Coach sensors."""
    coordinator: WeightCoachCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TrendWeightSensor(coordinator, entry),
            ActualRateSensor(coordinator, entry),
            ProjectedEndDateSensor(coordinator, entry),
            NextMilestoneSensor(coordinator, entry),
            TdeeSensor(coordinator, entry),
            ActiveTargetSensor(coordinator, entry),
            SuggestedTargetSensor(coordinator, entry),
            DaysUntilCheckinSensor(coordinator, entry),
        ]
    )


class WeightCoachSensorBase(SensorEntity):
    """Shared device info + push-update wiring for all Weight Coach sensors."""

    _attr_should_poll = False

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


class TrendWeightSensor(WeightCoachSensorBase):
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "trend_weight", "Trend Weight")

    @property
    def native_value(self) -> float | None:
        value = self._coordinator.trend_kg
        return round(value, 2) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"last_reading_source": self._coordinator.last_reading_source}


class ActualRateSensor(WeightCoachSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kg/wk"
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "actual_weekly_rate", "Actual Weekly Rate")

    @property
    def native_value(self) -> float | None:
        value = self._coordinator.actual_rate_kg_week
        return round(value, 3) if value is not None else None


class ProjectedEndDateSensor(WeightCoachSensorBase):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "projected_end_date", "Projected End Date")

    @property
    def native_value(self):
        return self._coordinator.projected_end_date


class NextMilestoneSensor(WeightCoachSensorBase):
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_icon = "mdi:flag-checkered"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_milestone", "Next Milestone")

    @property
    def native_value(self) -> float | None:
        milestone = self._coordinator.next_milestone
        return milestone.weight_kg if milestone else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        milestone = self._coordinator.next_milestone
        return {
            "milestone_number": milestone.number if milestone else None,
            "projected_date": (
                milestone.projected_date.isoformat()
                if milestone and milestone.projected_date
                else None
            ),
            "reached": milestone.reached if milestone else None,
            "all_milestones": [
                {
                    "number": item.number,
                    "weight_kg": item.weight_kg,
                    "projected_date": item.projected_date.isoformat()
                    if item.projected_date
                    else None,
                    "reached": item.reached,
                }
                for item in self._coordinator.milestones
            ],
        }


class TdeeSensor(WeightCoachSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kcal/d"
    _attr_icon = "mdi:fire"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tdee_estimate", "TDEE Estimate")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.tdee_estimate

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"tdee_source": self._coordinator.tdee_source}


class ActiveTargetSensor(WeightCoachSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kcal/d"
    _attr_icon = "mdi:target"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "active_calorie_target", "Active Calorie Target")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.active_target_kcal


class SuggestedTargetSensor(WeightCoachSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kcal/d"
    _attr_icon = "mdi:target-variant"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "suggested_calorie_target", "Suggested Calorie Target"
        )

    @property
    def native_value(self) -> float | None:
        return self._coordinator.suggested_target_kcal

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        next_checkin = self._coordinator.next_checkin_date
        return {
            "tdee_source": self._coordinator.tdee_source,
            "next_checkin_date": next_checkin.isoformat() if next_checkin else None,
        }


class DaysUntilCheckinSensor(WeightCoachSensorBase):
    """Countdown to the weekly (Sunday) recalibration of the suggested target."""

    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: WeightCoachCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "days_until_checkin", "Days Until Check-in")

    @property
    def native_value(self) -> int | None:
        return self._coordinator.days_until_checkin

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        next_checkin = self._coordinator.next_checkin_date
        return {"next_checkin_date": next_checkin.isoformat() if next_checkin else None}
