"""Coordinator: interroga periodicamente la centrale VEDO (I/O bloccante in executor)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
)
from .protocol import ACT_ARM, ACT_DISARM, Vedo, VedoError

_LOGGER = logging.getLogger(__name__)


class VedoCoordinator(DataUpdateCoordinator):
    """Legge stato aree e zone dalla centrale e cachea i nomi."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.entry = entry
        self.host = entry.data["host"]
        self.port = entry.data.get("port", DEFAULT_PORT)
        self.unit_id = entry.data.get(CONF_UNIT_ID, "")
        self._names_ready = False
        self.area_names: dict[int, str] = {}
        self.zone_names: dict[int, str] = {}
        self.num_areas = 0
        super().__init__(
            hass,
            _LOGGER,
            name="Comelit VEDO",
            update_interval=timedelta(
                seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    def _client(self) -> Vedo:
        return Vedo(self.host, self.port, unit_id=self.unit_id)

    def _fetch(self) -> dict:
        """Eseguito in executor: una connessione, lettura nomi (una volta) e stato."""
        with self._client() as v:
            s = v.handshake()
            if not self._names_ready:
                anames = v.read_area_names(s)
                self.num_areas = len(anames)
                self.area_names = {i: n for i, n in enumerate(anames)}
                self.zone_names = {i: n for i, n in enumerate(v.read_zone_names(s))}
                self._names_ready = True
            return {"areas": v.read_areas(s), "zones": v.read_zones(s)}

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except (VedoError, OSError) as err:
            raise UpdateFailed(f"Errore leggendo la centrale VEDO: {err}") from err

    # --- azioni ---------------------------------------------------------
    def _do_action(self, idx: int, code: int) -> bool:
        with self._client() as v:
            s = v.handshake()
            num = self.num_areas or len(v.read_area_names(s))
            return v.area_action(s, idx, code, num)

    async def async_arm(self, idx: int) -> None:
        await self._run_action(idx, ACT_ARM, "arma")

    async def async_disarm(self, idx: int) -> None:
        await self._run_action(idx, ACT_DISARM, "disarma")

    async def _run_action(self, idx: int, code: int, verb: str) -> None:
        try:
            ok = await self.hass.async_add_executor_job(self._do_action, idx, code)
        except (VedoError, OSError) as err:
            raise UpdateFailed(f"Impossibile {verb} l'area {idx}: {err}") from err
        if not ok:
            raise UpdateFailed(f"La centrale ha rifiutato il comando {verb} sull'area {idx}")
        await self.async_request_refresh()
