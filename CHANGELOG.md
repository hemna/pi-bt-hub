# Changelog

## [Unreleased]

## [1.2.0] - 2026-08-30

### Fixed

- **Issue #1** — Replace `assert` guards with `RuntimeError` in `deps.py` and `bridge_proxy.py`. Guards that used bare `assert` statements now raise `RuntimeError` with a descriptive message, so they work correctly even when Python optimisation (`-O`) is enabled.
- **Issue #2 / #13** — Add `asyncio.Lock` to scan lifecycle in `BlueZManager`. `start_discovery` and `stop_discovery` are now mutually exclusive via a lock, preventing concurrent scan races. The `_handle_properties_changed` signal handler no longer mutates `_is_scanning` directly — ownership stays with the public methods.
- **Issue #3 / #4** — SQL column allowlist and `aiosqlite.Error` wrapping in `DeviceStore`. `update_settings` now builds the `SET` clause only from an explicit `_SETTINGS_COLUMNS` allowlist, closing a column-name injection path. Both `get_settings` and `update_settings` now catch `aiosqlite.Error` and re-raise as `RuntimeError` with a descriptive message.
- **Issue #6** — `Settings` is now a frozen dataclass (`@dataclass(frozen=True)`), preventing accidental mutation of configuration after startup and making it hashable.
- **Issue #7** — `EventBus.publish` now iterates a snapshot (`list(self._subscribers.items())`) instead of the live dict, preventing `RuntimeError: dictionary changed size during iteration` when a subscriber calls `unsubscribe()` from within its queue handler.
- **Issue #8** — `PATCH /api/settings` returns HTTP 400 `{"error": "invalid_json"}` for malformed request bodies instead of silently ignoring them.
- **Issue #9** — `POST /api/scan/start` validates the `duration` query parameter: non-integer values return 400; integer values are clamped to the range `[5, 300]` seconds.
- **Issue #12** — `startup_services` now guards `logging.basicConfig` behind `if not logging.root.handlers`, so bt-hub no longer clobbers a host application's logging setup when used as an embedded library.

### Tests

- **Issue #11** — Added API-level tests verifying all seven device action endpoints (`GET /api/devices/{mac}`, `/pair`, `/connect`, `/disconnect`, `/trust`, `/untrust`, `/remove`) return HTTP 422 with `{"error": "validation_error"}` for malformed MAC addresses. Parametrized over six invalid MAC formats.

## [1.1.0] - 2026-05-06

### Changed

- **Live-only device discovery**: Removed device history and SQLite persistence for devices. The devices page now shows only what BlueZ currently reports — no stored history, no favorites, no ignored lists. SQLite is retained solely for app settings.
- **Combined single-page UI**: Merged the Dashboard and Devices pages into a single page at `/`. Adapter status, scan controls, and the device list are all in one place — no switching between pages during scan and pairing workflows.
- **Non-blocking scan start**: Clicking "Start Scan" returns immediately. The BlueZ discovery (including bridge stop) runs in the background so the UI is never blocked.
- **Accurate scan countdown**: The countdown timer now starts when BlueZ actually begins scanning (via WebSocket `scan_started` event), not when the button is clicked. Shows "Starting scan..." during the bridge-stop delay.
- **Progressive device discovery**: Devices appear in real-time during scan via WebSocket events and periodic polling every 3 seconds, rather than all appearing at the end.

### Removed

- Device persistence (favorites, ignored lists, aliases, notes, first_seen/last_seen history)
- Filter buttons (In Range, Paired, Connected, Favorites, Ignored)
- Sort dropdown (Last Seen, Name, Last Connected)
- Separate `/devices` page (now redirects to `/`)
- Template partials: `device_filter_buttons.html`, `device_row.html`, `favorite_button_detail.html`, `ignored_button_detail.html`, `devices.html`

### Fixed

- WebSocket event handlers were checking `.type` instead of `.event` field, causing real-time updates to silently fail
- Scan progress device count was inconsistent with displayed cards
- `scan_progress.html` referenced removed API endpoints (`/api/devices?filter=ignored`, favorite/ignore buttons)

## [1.0.0] - 2026-04-15

- Initial release
