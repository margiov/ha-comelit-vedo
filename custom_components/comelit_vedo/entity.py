"""Base comune per le entità Comelit VEDO."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VedoCoordinator


class VedoEntity(CoordinatorEntity[VedoCoordinator]):
    """Entità legata alla config entry, con device condiviso."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VedoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            manufacturer="Comelit",
            name="Centrale VEDO",
            configuration_url=None,
        )
