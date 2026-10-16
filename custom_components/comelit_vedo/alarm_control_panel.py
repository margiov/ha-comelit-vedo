"""Pannelli d'allarme: una entità per area presente."""
from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VedoCoordinator
from .entity import VedoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VedoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VedoAreaPanel(coordinator, idx) for idx in coordinator.data["areas"]
    )


class VedoAreaPanel(VedoEntity, AlarmControlPanelEntity):
    """Un'area della centrale come pannello d'allarme (arma totale / disarma)."""

    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
    _attr_code_arm_required = False

    def __init__(self, coordinator: VedoCoordinator, idx: int) -> None:
        super().__init__(coordinator)
        self._idx = idx
        self._attr_unique_id = f"{coordinator.entry.entry_id}_area_{idx}"

    @property
    def name(self) -> str:
        return self.coordinator.area_names.get(self._idx, f"Area {self._idx + 1}")

    @property
    def _area(self) -> dict | None:
        return self.coordinator.data["areas"].get(self._idx)

    @property
    def available(self) -> bool:
        return super().available and self._area is not None

    _STATE_MAP = {
        "triggered": AlarmControlPanelState.TRIGGERED,
        "arming": AlarmControlPanelState.ARMING,
        "pending": AlarmControlPanelState.PENDING,
        "armed_away": AlarmControlPanelState.ARMED_AWAY,
        "armed_home": AlarmControlPanelState.ARMED_HOME,
        "armed_night": AlarmControlPanelState.ARMED_NIGHT,
        "disarmed": AlarmControlPanelState.DISARMED,
    }

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        area = self._area
        if area is None:
            return None
        return self._STATE_MAP.get(area["state"])

    @property
    def extra_state_attributes(self) -> dict:
        area = self._area or {}
        return {
            "not_ready": area.get("not_ready", False),
            "alarm_memory": area.get("alarm_memory", False),
            "sabotage": area.get("sabotage", False),
            "anomaly": area.get("anomaly", False),
            "exclusion": area.get("exclusion", False),
            "open_zone": area.get("open_zone", False),
            "output_on": area.get("output_on", False),
            "flags": area.get("flags", []),
            "raw": area.get("raw"),
        }

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self.coordinator.async_arm(self._idx)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self.coordinator.async_disarm(self._idx)
