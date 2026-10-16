"""Sensori binari: una entità per zona presente (aperta / a riposo)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
        VedoZoneSensor(coordinator, idx) for idx in coordinator.data["zones"]
    )


class VedoZoneSensor(VedoEntity, BinarySensorEntity):
    """Stato di una zona (attiva / a riposo), con i flag come attributi.

    Il protocollo non dice se una zona e' un rilevatore di movimento o un contatto:
    di default e' "motion" (il caso tipico delle zone VEDO); per i contatti porta o
    finestra si cambia da HA (impostazioni dell'entita' -> "Mostra come")."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: VedoCoordinator, idx: int) -> None:
        super().__init__(coordinator)
        self._idx = idx
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{idx}"

    @property
    def name(self) -> str:
        return self.coordinator.zone_names.get(self._idx, f"Zona {self._idx}")

    @property
    def _zone(self) -> dict | None:
        return self.coordinator.data["zones"].get(self._idx)

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def is_on(self) -> bool | None:
        zone = self._zone
        return None if zone is None else zone["open"]

    @property
    def extra_state_attributes(self) -> dict:
        zone = self._zone or {}
        return {"flags": zone.get("flags", []), "raw": zone.get("raw")}
