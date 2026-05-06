# Direwolf Integration Design

**Date:** 2026-04-29
**Status:** Draft
**Repos:** pi-bt-bridge (services), pi-bt-hub (UI)

## Summary

Enable pi-bt-bridge to connect as a TCP client to a running direwolf instance, allowing phones connected via BLE to send/receive packets over RF through direwolf (software TNC). Supports both TCP KISS and AGW protocols, configurable one-at-a-time.

## Problem

The current architecture requires a hardware TNC (connected via Bluetooth Classic SPP) for RF transmission. Users who run direwolf as a software modem (soundcard → radio) have no way to bridge phone BLE traffic to direwolf. Direwolf only acts as a TCP server — it cannot connect out as a client. The bridge must initiate the connection.

## Data Flow

```
Phone (APRSDroid/etc)
    │
    │  BLE (KISS frames via Nordic UART)
    ▼
pi-bt-bridge
    │
    ├── Classic BT (SPP/RFCOMM) ──→ Hardware TNC ──→ RF   (existing, still works)
    │
    ├── TCP KISS server (port 8002) ←── desktop apps       (existing, still works)
    │
    └── Direwolf client ──→ direwolf TCP KISS (port 8001)  (NEW)
                        OR ──→ direwolf AGW (port 8000)    (NEW)
                                    │
                                    ▼
                              soundcard ──→ radio ──→ RF
```

All endpoints coexist. Frames from any source are forwarded to all other connected endpoints via the bridge's central frame router.

## Architecture

### New Components (in pi-bt-bridge)

| File | Purpose |
|------|---------|
| `src/services/direwolf_kiss_client_service.py` | TCP KISS client connecting to direwolf |
| `src/services/direwolf_agw_client_service.py` | AGW protocol client connecting to direwolf |
| `src/models/agw.py` | AGW frame header parsing/building |

### Existing Changes (in pi-bt-bridge)

| File | Change |
|------|--------|
| `src/services/bridge.py` | Register direwolf endpoint in frame router |
| `src/config.py` | Add direwolf config options |
| `src/main.py` | Start direwolf service based on config |
| `src/models/state.py` | Add direwolf connection state |
| Web templates + API | Expose direwolf status |

### Changes (in pi-bt-hub)

| File | Change |
|------|--------|
| `templates/settings.html` | Direwolf config section (enable, mode, host, port, callsign) |
| `templates/bridge/status.html` | Direwolf connection state display |
| `services/bridge_proxy.py` | Handle new direwolf status fields in API responses |

## Configuration

New entries in `/etc/bt-bridge/config.json`:

```json
{
  "direwolf_enabled": false,
  "direwolf_mode": "kiss",
  "direwolf_host": "localhost",
  "direwolf_kiss_port": 8001,
  "direwolf_agw_port": 8000,
  "direwolf_reconnect": true,
  "direwolf_reconnect_interval": 5,
  "direwolf_agw_callsign": "",
  "direwolf_agw_monitor": true
}
```

| Option | Default | Description |
|--------|---------|-------------|
| `direwolf_enabled` | `false` | Enable direwolf client connection |
| `direwolf_mode` | `"kiss"` | `"kiss"` or `"agw"` — which protocol to use |
| `direwolf_host` | `"localhost"` | Direwolf host (usually same Pi) |
| `direwolf_kiss_port` | `8001` | Direwolf's TCP KISS server port |
| `direwolf_agw_port` | `8000` | Direwolf's AGW server port |
| `direwolf_reconnect` | `true` | Auto-reconnect on disconnect |
| `direwolf_reconnect_interval` | `5` | Seconds between reconnect attempts (exponential backoff) |
| `direwolf_agw_callsign` | `""` | Callsign to register with AGW (required for AGW mode) |
| `direwolf_agw_monitor` | `true` | Enable AGW monitoring frames |

**Port conflict validation:** If `direwolf_mode` is `"kiss"` and `direwolf_kiss_port` equals `tcp_kiss_port`, the bridge must warn/error — both would try to use the same port (one as server, one as client to direwolf).

## Service Design

### DirewolfKissClientService

```python
class DirewolfKissClientService:
    """TCP KISS client that connects to direwolf's KISS server."""

    state: Literal["idle", "connecting", "connected", "error"]

    async def start(host: str, port: int) -> None
    async def stop() -> None
    async def send_frame(kiss_frame: bytes) -> None  # called by bridge router
    # Internal:
    async def _connect() -> None
    async def _read_loop() -> None  # reads from direwolf, delivers to bridge
    async def _reconnect_loop() -> None  # exponential backoff
```

Reuses existing `models/kiss.py` for KISS framing. Same wire format as the existing TCP KISS server — just opposite direction (client vs server).

### DirewolfAgwClientService

```python
class DirewolfAgwClientService:
    """AGW protocol client that connects to direwolf's AGW server."""

    state: Literal["idle", "connecting", "connected", "registered", "error"]

    async def start(host: str, port: int, callsign: str) -> None
    async def stop() -> None
    async def send_frame(ax25_frame: bytes) -> None  # wraps in AGW 'K' frame
    async def connect_ax25(call_from: str, call_to: str) -> None  # 'C' frame
    async def send_data(call_from: str, call_to: str, data: bytes) -> None  # 'D' frame
    async def disconnect_ax25(call_from: str, call_to: str) -> None  # 'd' frame
    # Internal:
    async def _connect() -> None
    async def _register_callsign() -> None  # 'X' frame
    async def _enable_monitoring() -> None  # 'm' frame
    async def _read_loop() -> None  # parses 36-byte AGW headers
    async def _reconnect_loop() -> None
```

### AGW Frame Model

```python
@dataclass
class AgwFrame:
    port: int          # Radio port (0-based)
    data_kind: str     # Single char: 'R', 'X', 'G', 'K', 'C', 'D', 'd', 'm', etc.
    call_from: str     # 10 chars max
    call_to: str       # 10 chars max
    data: bytes        # Variable length

    def to_bytes() -> bytes  # Serialize to 36-byte header + data
    @classmethod
    def from_bytes(raw: bytes) -> AgwFrame  # Parse from wire
```

AGW header structure (36 bytes):
```
Offset  Size  Field
0       4     Port (little-endian uint32)
4       4     DataKind (4 bytes, first byte is the command char)
8       4     Reserved (unused)
12      10    CallFrom (null-padded string)
22      10    CallTo (null-padded string)
32      4     DataLen (little-endian uint32)
--- data follows (DataLen bytes) ---
```

### Frame Translation (AGW mode)

When using AGW mode, frames need protocol translation:

- **BLE → direwolf (TX):** Strip KISS framing → extract raw AX.25 → wrap in AGW 'K' frame (raw send)
- **direwolf → BLE (RX):** Parse AGW frame → extract raw AX.25 → wrap in KISS framing → send to BLE

For connected-mode sessions, the AGW service manages connection state ('C'/'D'/'d' frames) and the bridge may need to expose this to phone apps via a higher-level protocol (future work).

### Bridge Router Registration

```python
# In bridge.py startup
if config.direwolf_enabled:
    if config.direwolf_mode == "kiss":
        self.direwolf = DirewolfKissClientService(...)
    else:
        self.direwolf = DirewolfAgwClientService(...)
    self.register_endpoint("direwolf", self.direwolf)
```

## Status API

New `direwolf` section in `/api/status` response:

```json
{
  "direwolf": {
    "enabled": true,
    "mode": "kiss",
    "state": "connected",
    "host": "localhost",
    "port": 8001,
    "connected_at": "2026-04-29T10:30:00Z",
    "frames_tx": 42,
    "frames_rx": 108,
    "bytes_tx": 2100,
    "bytes_rx": 5400,
    "last_error": null,
    "reconnect_attempts": 0
  }
}
```

AGW mode adds:

```json
{
  "direwolf": {
    "mode": "agw",
    "state": "registered",
    "callsign": "WB2OSZ-5",
    "monitoring": true,
    "active_connections": [
      {"call_from": "WB2OSZ-5", "call_to": "N0CALL-2", "state": "connected"}
    ]
  }
}
```

## Implementation Phases

| Phase | Scope | Repo | Deliverable |
|-------|-------|------|-------------|
| **1** | TCP KISS client | pi-bt-bridge | `direwolf_kiss_client_service.py` + config + bridge registration |
| **2** | AGW protocol model | pi-bt-bridge | `models/agw.py` — header parsing/building |
| **3** | AGW client service | pi-bt-bridge | `direwolf_agw_client_service.py` + KISS↔AGW translation |
| **4** | Hub UI | pi-bt-hub | Settings + status UI for direwolf |
| **5** | Testing | both | Integration tests with mock direwolf TCP server |

## Testing Strategy

- **Unit tests:** AGW frame parsing/building, KISS client connection state machine
- **Integration tests:** Mock TCP server simulating direwolf, verify frame forwarding end-to-end
- **Manual testing:** Phone → BLE → bridge → direwolf → RF with real hardware

## Open Questions

1. **Duplex control:** If both hardware TNC and direwolf are connected, should the bridge avoid forwarding BLE frames to both simultaneously (double-TX)? Or is that the user's responsibility via config?
2. **AGW connected-mode UX:** How does the phone app initiate/manage AX.25 connected-mode sessions through AGW? This may require a new BLE characteristic or KISS extension.
3. **Direwolf PTT timing:** Does the bridge need to coordinate with direwolf's TXDELAY/TXtail, or does direwolf handle all timing via KISS commands?
