"""Client per il protocollo nativo delle centrali Comelit VEDO (TCP 10012 / TLS 10022).

Adattato dal progetto comelit-vedo-client per l'uso come libreria dentro Home
Assistant. Codice bloccante: va eseguito in un executor (vedi coordinator).
"""
from __future__ import annotations

import logging
import socket
import ssl
import struct

_LOGGER = logging.getLogger(__name__)

MAGIC = b"\x36\x0c"

# codici azione per area (ordinali enum AreaActivation dell'app):
# 0=non toccare, 1=TOT, 2=P1+P2, 3=P1, 4=P2, 5=disarma
ACT_NONE, ACT_ARM, ACT_P12, ACT_P1, ACT_P2, ACT_DISARM = 0, 1, 2, 3, 4, 5

# bitmask stato zona (enum RtSpecZoneStatus)
ZONE_FLAGS = [
    (1, "open"), (2, "alarm"), (4, "faulty"), (8, "sabotaged"),
    (16, "ready"), (32, "active"), (64, "chime"), (128, "excluded"),
    (256, "isolated"), (512, "not_present"), (2048, "masked"),
    (4096, "low_batt"), (8192, "superv"),
]

# stato aree (frame 6029): record 4 byte = 28 bit, uno per flag, nell'ordine
# dell'enum AreaStatus dell'app (com.comelitgroup.nimbus.dpcp.realtime.AreaStatus).
# (byte_index, bitmask, nome)
AREA_BITS = [
    # byte 0
    (0, 0x01, "disarmed"), (0, 0x02, "armed_total"), (0, 0x04, "armed_p1"),
    (0, 0x08, "armed_p2"), (0, 0x10, "not_ready_arming"), (0, 0x20, "in_alarm"),
    (0, 0x40, "sabotage"), (0, 0x80, "anomaly"),
    # byte 1
    (1, 0x01, "alarm_memory"), (1, 0x02, "not_ready_total"), (1, 0x04, "not_ready_p1"),
    (1, 0x08, "not_ready_p2"), (1, 0x10, "alarm_in_progress"), (1, 0x20, "exclusion"),
    (1, 0x40, "entry_delay"), (1, 0x80, "exit_delay"),
    # byte 2
    (2, 0x01, "arming_failed"), (2, 0x02, "arming_completed"), (2, 0x04, "disarming_completed"),
    (2, 0x08, "no_burglar_p1"), (2, 0x10, "no_burglar_p2"), (2, 0x20, "no_burglar_area"),
    (2, 0x40, "open_zone"), (2, 0x80, "output_on"),
    # byte 3
    (3, 0x01, "alarm_p1"), (3, 0x02, "alarm_p2"), (3, 0x04, "memory_p1"), (3, 0x08, "memory_p2"),
]
# flag "sempre attivi" quando l'area non ha zone P1/P2: solo rumore di fondo
_AREA_NOISE = {"no_burglar_p1", "no_burglar_p2", "no_burglar_area"}


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, xorout 0)."""
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def escape(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        if b >= 0xF0:
            out += bytes([0xF0, b ^ 0xF0])
        else:
            out.append(b)
    return bytes(out)


def unescape(data: bytes) -> bytes:
    out = bytearray()
    esc = False
    for b in data:
        if esc:
            out.append(b ^ 0xF0)
            esc = False
        elif b == 0xF0:
            esc = True
        else:
            out.append(b)
    return bytes(out)


def build_frame(session: bytes, seq: int, msgtype: int, payload: bytes) -> bytes:
    body = MAGIC + session + bytes([seq & 0xFF]) + struct.pack(">H", msgtype) + payload
    body += struct.pack(">H", crc16(body))
    return b"\xF1" + escape(body) + b"\xF2"


def parse_frame(raw_inner: bytes) -> dict:
    u = unescape(raw_inner)
    if len(u) < 9:
        return {"session": b"", "seq": -1, "msgtype": -1, "payload": b"", "crc_ok": False}
    body, trailer = u[:-2], u[-2:]
    return {
        "session": body[2:4],
        "seq": body[4],
        "msgtype": struct.unpack(">H", body[5:7])[0],
        "payload": body[7:],
        "crc_ok": crc16(body) == struct.unpack(">H", trailer)[0],
    }


class VedoError(Exception):
    """Errore di protocollo o di comunicazione con la centrale."""


class Vedo:
    """Connessione a una centrale VEDO via protocollo nativo (10012/10022)."""

    CFG_AREAS = 0x0001
    CFG_ZONES = 0x0010
    CFG_PARAM_NAME = 0x0000
    CFG_CHUNK = 8
    STATUS_ZONES = 30

    AREAS_STATUS_PFX = bytes.fromhex("000100000000")
    ZONE_FRAME_PFX = bytes.fromhex("00000000000260fd")
    SUBS = [
        "00010000000060040008000000",
        "0002000000006004008b000000",
        "0000000000026004003d000000",
        "0000003d00026004003d000000",
        "0000007a00026004003d000000",
        "000000b700026004003d000000",
        "000000f400026004003d000000",
    ]

    def __init__(self, host, port=10022, unit_id="", timeout=6.0,
                 tls=None, tls_cafile=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls = (port == 10022) if tls is None else tls
        self.tls_cafile = tls_cafile
        self.unit_id = bytes.fromhex(unit_id) if unit_id else b""
        self.sock = None
        self.seq = 0xA0
        self.buf = bytearray()

    # --- contesto / I/O -------------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self.tls:
            if self.tls_cafile:
                ctx = ssl.create_default_context(cafile=self.tls_cafile)
                ctx.check_hostname = False
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=self.host)
        sock.settimeout(self.timeout)
        self.sock = sock

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _next_seq(self):
        self.seq = (self.seq + 1) & 0xFF
        return self.seq

    def send(self, session, msgtype, payload=b""):
        self.sock.sendall(build_frame(session, self._next_seq(), msgtype, payload))

    def recv_frame(self):
        while True:
            start = self.buf.find(0xF1)
            if start >= 0:
                end = self.buf.find(0xF2, start + 1)
                if end >= 0:
                    inner = bytes(self.buf[start + 1:end])
                    del self.buf[:end + 1]
                    return parse_frame(inner)
            chunk = self.sock.recv(4096)
            if not chunk:
                raise VedoError("connessione chiusa dalla centrale")
            self.buf += chunk

    def recv_matching(self, msgtype, pfx, tries=400):
        for _ in range(tries):
            fr = self.recv_frame()
            if fr["msgtype"] == msgtype and fr["payload"].startswith(pfx):
                return fr
        raise VedoError("risposta attesa non ricevuta")

    # --- sessione -------------------------------------------------------
    def handshake(self):
        self.send(b"\x00\x00", 0x4002, bytes.fromhex("000000000000"))
        r = self.recv_frame()
        if not r["crc_ok"] or len(r["payload"]) < 4:
            raise VedoError("handshake fallito")
        session = r["payload"][2:4]
        self.send(session, 0x4005, b"\x00\x00")
        self.recv_frame()
        return session

    def open_device_session(self, ctrl_session):
        if not self.unit_id:
            raise VedoError("unit_id non configurato: richiesto per arma/disarma")
        self.send(ctrl_session, 0x4002, b"\x00" + self.unit_id + b"\x00\x01")
        r = self.recv_frame()
        dev = r["payload"][2:4]
        if not r["crc_ok"] or r["payload"][0] != 0 or dev == b"\x00\x00":
            raise VedoError(
                f"device session rifiutata (esito {r['payload'][:2].hex()}): unit_id errato?"
            )
        return dev

    # --- letture config -------------------------------------------------
    def read_config(self, session, group, start, count, param=CFG_PARAM_NAME):
        req = struct.pack(">HHHHH", group, start, param, 0x6004, count) + b"\x00\x00\x00"
        self.send(session, 0x400a, req)
        pl = self.recv_matching(0x400a, req[:6])["payload"]
        n, recsz = struct.unpack(">HH", pl[8:12])
        off = 12 + recsz
        dlen = struct.unpack(">H", pl[off:off + 2])[0]
        data = pl[off + 2:off + 2 + dlen]
        return [data[i * recsz:(i + 1) * recsz] for i in range(min(n, dlen // max(recsz, 1)))]

    def read_names(self, session, group, start, count):
        out = []
        for s in range(start, start + count, self.CFG_CHUNK):
            n = min(self.CFG_CHUNK, start + count - s)
            out += [r.split(b"\x00")[0].decode("latin-1").strip()
                    for r in self.read_config(session, group, s, n)]
        return out

    def read_num_areas(self, session):
        self.send(session, 0x4012, self.AREAS_STATUS_PFX + bytes.fromhex("60040020000000"))
        pl = self.recv_matching(0x4012, self.AREAS_STATUS_PFX)["payload"]
        return struct.unpack(">H", pl[8:10])[0]

    def read_area_names(self, session, num_areas=None):
        if num_areas is None:
            num_areas = self.read_num_areas(session)
        return self.read_names(session, self.CFG_AREAS, 0, num_areas)

    def read_zone_names(self, session, num_zones=STATUS_ZONES):
        # nel gruppo config l'indice 0 e' il tamper di sistema: la zona z e' il record z+1
        return self.read_names(session, self.CFG_ZONES, 1, num_zones)

    # --- letture stato --------------------------------------------------
    @staticmethod
    def _area_records(payload):
        n, recsz = struct.unpack(">H", payload[8:10])[0], struct.unpack(">H", payload[10:12])[0]
        off = 12 + recsz
        dlen = struct.unpack(">H", payload[off:off + 2])[0]
        data = payload[off + 2:off + 2 + dlen]
        return [data[i * recsz:(i + 1) * recsz] for i in range(n)]

    @staticmethod
    def _decode_area(rec):
        if not rec or rec[0] == 0x00:
            return None
        active = {name for bi, bit, name in AREA_BITS if rec[bi] & bit}
        armed = bool(active & {"armed_total", "armed_p1", "armed_p2"})
        in_alarm = "in_alarm" in active
        exit_delay = "exit_delay" in active      # tempo di uscita = inserimento in corso
        entry_delay = "entry_delay" in active     # tempo di ingresso = pre-allarme
        if in_alarm:
            state = "triggered"
        elif exit_delay:
            state = "arming"
        elif entry_delay:
            state = "pending"
        elif "armed_total" in active:
            state = "armed_away"
        elif "armed_p1" in active:
            state = "armed_home"
        elif "armed_p2" in active:
            state = "armed_night"
        elif "disarmed" in active:
            state = "disarmed"
        else:
            state = "unknown"
        return {
            "state": state,
            "armed": armed,
            "alarm": in_alarm,
            "arming": exit_delay,
            "pending": entry_delay,
            "alarm_memory": "alarm_memory" in active,
            "not_ready": bool(active & {"not_ready_arming", "not_ready_total"}),
            "sabotage": "sabotage" in active,
            "anomaly": "anomaly" in active,
            "exclusion": "exclusion" in active,
            "open_zone": "open_zone" in active,
            "output_on": "output_on" in active,
            "flags": sorted(active - _AREA_NOISE),
            "raw": rec.hex(),
        }

    def read_areas(self, session):
        """{idx: {state, armed, not_ready, raw}} per le aree presenti."""
        self.send(session, 0x4012, self.AREAS_STATUS_PFX + bytes.fromhex("60040020000000"))
        pl = self.recv_matching(0x4012, self.AREAS_STATUS_PFX)["payload"]
        out = {}
        for i, rec in enumerate(self._area_records(pl)):
            info = self._decode_area(rec)
            if info is not None:
                out[i] = info
        return out

    def read_zones(self, session):
        """{idx: {open, flags, raw}} per le zone presenti."""
        for s in self.SUBS:
            self.send(session, 0x4012, bytes.fromhex(s))
        fr = self.recv_matching(0x4012, self.ZONE_FRAME_PFX)
        body = fr["payload"][20:]
        out = {}
        for z in range(len(body) // 8):
            spec = int.from_bytes(body[8 * z + 6:8 * z + 8], "little")
            if spec & 512:  # not_present
                continue
            out[z] = {
                "open": bool(spec & 1),
                "flags": [name for bit, name in ZONE_FLAGS if spec & bit],
                "raw": f"{spec:#06x}",
            }
        return out

    # --- azioni (scrittura) --------------------------------------------
    def _area_vector(self, idx, code, num_areas):
        if not 0 <= idx < num_areas:
            raise VedoError(f"indice area {idx} fuori range (0..{num_areas - 1})")
        v = bytearray(num_areas)
        v[idx] = code
        return bytes(v)

    def area_action(self, ctrl_session, idx, code, num_areas):
        """Invia arma/disarma per la sola area `idx`. Ritorna True se accettato."""
        vector = self._area_vector(idx, code, num_areas)
        dev = self.open_device_session(ctrl_session)
        payload = bytes.fromhex("00020201") + struct.pack(">H", len(vector)) + vector
        self.send(dev, 0x4013, payload)
        r = self.recv_frame()
        return r["payload"][:2] == b"\x00\x00"
