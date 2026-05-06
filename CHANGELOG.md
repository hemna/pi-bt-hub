# Changelog

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
