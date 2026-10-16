"""Costanti dell'integrazione Comelit VEDO (nativo)."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "comelit_vedo"

CONF_UNIT_ID = "unit_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 10022
DEFAULT_SCAN_INTERVAL = 15  # secondi
MIN_SCAN_INTERVAL = 2

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR]
