"""Coordinator: interroga periodicamente la centrale VEDO (I/O bloccante in executor).

Mantiene una connessione persistente e la riusa tra un polling e l'altro: riaprire
una connessione TLS a ogni ciclo (specie con intervalli brevi) sovraccarica la
centrale e causa timeout. In caso di errore la connessione viene chiusa e riaperta,
con un tentativo di riconnessione prima di segnalare l'aggiornamento come fallito.
"""
from __future__ import annotations

import logging
import time
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

CONNECT_TIMEOUT = 5.0

# Subito dopo un comando di inserimento la centrale espone gia' il bit "inserita"
# ma non ancora il tempo di uscita, che compare un paio di secondi dopo (oppure,
# senza tempo di uscita, arriva solo l'impulso "arming_completed"). Senza
# correzione lo stato passa armed_away -> arming -> armed_away. Per questo tempo
# dopo il comando, finche' la centrale non segnala tempo di uscita o fine
# inserimento, l'area resta in `arming`.
ARM_SETTLE = 10.0  # secondi
_ARMED_STATES = {"armed_away", "armed_home", "armed_night"}


class VedoCoordinator(DataUpdateCoordinator):
    """Legge stato aree e zone dalla centrale (connessione persistente) e cachea i nomi."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.entry = entry
        cfg = {**entry.data, **entry.options}   # le opzioni hanno la precedenza
        self.host = cfg["host"]
        self.port = cfg.get("port", DEFAULT_PORT)
        self.unit_id = cfg.get(CONF_UNIT_ID, "")
        self._names_ready = False
        self.area_names: dict[int, str] = {}
        self.zone_names: dict[int, str] = {}
        self.num_areas = 0
        self._client: Vedo | None = None
        self._session: bytes | None = None
        self._arm_sent: dict[int, float] = {}   # area -> istante del comando di inserimento
        super().__init__(
            hass,
            _LOGGER,
            name="Comelit VEDO",
            update_interval=timedelta(
                seconds=cfg.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    def _new_client(self) -> Vedo:
        return Vedo(self.host, self.port, unit_id=self.unit_id, timeout=CONNECT_TIMEOUT)

    def _reset(self) -> None:
        """Chiude la connessione persistente (verra' riaperta al prossimo ciclo)."""
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
        self._client = None
        self._session = None

    def _ensure(self) -> None:
        """Garantisce una connessione aperta; legge i nomi la prima volta."""
        if self._client is not None and self._session is not None:
            return
        client = self._new_client()
        client.connect()
        session = client.handshake()
        if not self._names_ready:
            anames = client.read_area_names(session)
            self.num_areas = len(anames)
            self.area_names = dict(enumerate(anames))
            self.zone_names = dict(enumerate(client.read_zone_names(session)))
            self._names_ready = True
        self._client = client
        self._session = session

    def _read_once(self) -> dict:
        self._ensure()
        assert self._client is not None and self._session is not None
        return {
            "areas": self._client.read_areas(self._session),
            "zones": self._client.read_zones(self._session),
        }

    def _fetch(self) -> dict:
        """Eseguito in executor: legge lo stato, riconnettendo una volta se serve."""
        try:
            return self._read_once()
        except (VedoError, OSError) as first:
            _LOGGER.debug("Lettura fallita (%s), riconnetto e riprovo", first)
            self._reset()
            return self._read_once()

    async def _async_update_data(self) -> dict:
        try:
            data = await self.hass.async_add_executor_job(self._fetch)
        except (VedoError, OSError) as err:
            await self.hass.async_add_executor_job(self._reset)
            raise UpdateFailed(f"Errore leggendo la centrale VEDO: {err}") from err
        return self._settle_arming(data)

    def _settle_arming(self, data: dict) -> dict:
        """Mostra `arming` nel transitorio tra comando di inserimento e tempo di uscita."""
        now = time.monotonic()
        for idx, since in list(self._arm_sent.items()):
            area = data["areas"].get(idx)
            if area is None or now - since > ARM_SETTLE:
                del self._arm_sent[idx]
                continue
            flags = area["flags"]
            if area["state"] in _ARMED_STATES and not (
                {"arming_completed", "arming_failed"} & set(flags)
            ):
                data["areas"][idx] = {**area, "state": "arming", "arming": True}
            elif area["state"] != "disarmed":
                # tempo di uscita, fine inserimento, allarme o pre-allarme: da qui
                # in poi lo stato della centrale e' affidabile. Se e' ancora
                # disinserita il comando non e' stato ancora applicato: si attende.
                del self._arm_sent[idx]
        return data

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._reset)
        await super().async_shutdown()

    # --- azioni (connessione dedicata, separata da quella di polling) ---
    def _do_action(self, idx: int, code: int) -> bool:
        with self._new_client() as v:
            s = v.handshake()
            num = self.num_areas or len(v.read_area_names(s))
            return v.area_action(s, idx, code, num)

    async def async_arm(self, idx: int, code: int = ACT_ARM) -> None:
        area = (self.data or {}).get("areas", {}).get(idx)
        if area is None or area["state"] not in _ARMED_STATES:
            # gia' inserita: nessun transitorio da nascondere
            self._arm_sent[idx] = time.monotonic()
        try:
            await self._run_action(idx, code, "arma")
        except UpdateFailed:
            self._arm_sent.pop(idx, None)
            raise

    async def async_disarm(self, idx: int) -> None:
        self._arm_sent.pop(idx, None)
        await self._run_action(idx, ACT_DISARM, "disarma")

    async def _run_action(self, idx: int, code: int, verb: str) -> None:
        try:
            ok = await self.hass.async_add_executor_job(self._do_action, idx, code)
        except (VedoError, OSError) as err:
            raise UpdateFailed(f"Impossibile {verb} l'area {idx}: {err}") from err
        if not ok:
            raise UpdateFailed(f"La centrale ha rifiutato il comando {verb} sull'area {idx}")
        await self.async_request_refresh()
