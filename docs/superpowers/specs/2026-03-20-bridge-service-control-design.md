# Bridge Service Control Design

**Date:** 2026-03-20  
**Status:** Approved  
**Author:** Claude

## Overview

Add UI controls to start/stop/restart the bt-bridge systemd service and view its logs directly from the pi-bt-hub dashboard. Currently, when the bridge daemon is offline, users see "Bridge Offline" with no way to start it from the web UI.

## Requirements

- Full control: start, stop, restart bt-bridge.service
- View service status (active/inactive/failed/not-found)
- View recent logs from journalctl
- Controls appear on the dashboard Bridge Status card
- Use sudoers for permission (no root required for pi-bt-hub)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     pi-bt-hub                               │
│  ┌─────────────────┐    ┌─────────────────────────────┐    │
│  │  Dashboard UI   │───▶│  /api/bridge/service/*      │    │
│  │  (HTMX buttons) │    │  API endpoints              │    │
│  └─────────────────┘    └──────────────┬──────────────┘    │
│                                        │                    │
│                         ┌──────────────▼──────────────┐    │
│                         │  SystemdService class       │    │
│                         │  (subprocess executor)      │    │
│                         └──────────────┬──────────────┘    │
└────────────────────────────────────────┼────────────────────┘
                                         │ sudo systemctl/journalctl
                                         ▼
                              ┌─────────────────────┐
                              │  bt-bridge.service  │
                              │  (systemd unit)     │
                              └─────────────────────┘
```

### 1. SystemdService Class

**File:** `backend/src/bt_hub/services/systemd_service.py`

```python
class ServiceStatus(BaseModel):
    state: Literal["active", "inactive", "failed", "not-found"]
    sub_state: str | None  # e.g., "running", "dead"
    enabled: bool | None
    description: str | None

class ServiceResult(BaseModel):
    success: bool
    message: str
    exit_code: int

class SystemdService:
    """Manage a systemd service via subprocess calls."""
    
    def __init__(self, service_name: str = "bt-bridge.service"):
        self.service_name = service_name
    
    async def status(self) -> ServiceStatus:
        """Get service status using systemctl is-active and show."""
        
    async def start(self) -> ServiceResult:
        """Start the service via sudo systemctl start."""
        
    async def stop(self) -> ServiceResult:
        """Stop the service via sudo systemctl stop."""
        
    async def restart(self) -> ServiceResult:
        """Restart the service via sudo systemctl restart."""
        
    async def logs(self, lines: int = 100) -> str:
        """Get recent journal logs via sudo journalctl."""
```

Implementation uses `asyncio.create_subprocess_exec()` for non-blocking execution.

### 2. API Endpoints

**File:** `backend/src/bt_hub/api/bridge.py` (additions)

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/api/bridge/service/status` | GET | Service state | `ServiceStatus` |
| `/api/bridge/service/start` | POST | Start service | `ServiceResult` |
| `/api/bridge/service/stop` | POST | Stop service | `ServiceResult` |
| `/api/bridge/service/restart` | POST | Restart service | `ServiceResult` |
| `/api/bridge/service/logs` | GET | Journal logs | `{"logs": "..."}` |

Query params for logs: `?lines=100` (default 100, max 500)

### 3. Dashboard UI

**File:** `backend/src/bt_hub/templates/index.html`

The BT Bridge card shows different states:

**Service not found:**
- Badge: "Not Found"
- Message: "bt-bridge.service not installed"
- Button: [View Logs]

**Service stopped (inactive):**
- Badge: "Stopped"
- Buttons: [Start] [View Logs]

**Service running, daemon not responding:**
- Badge: "Starting" or "Error"
- Info: "Service: Running, Daemon: Not responding"
- Buttons: [Stop] [Restart] [View Logs]

**Service running, daemon online:**
- Badge: "Online"
- Info: BLE/Classic status from daemon
- Buttons: [Stop] [Restart] [View Logs]

**Logs section:**
- Expandable/collapsible section below card
- Shows last 100 lines from journalctl
- Refresh button to reload
- Monospace font, auto-scroll to bottom

### 4. Sudoers Configuration

**File:** `/etc/sudoers.d/pi-bt-hub`

```sudoers
# Pi BT Hub - allow bt-bridge service control without password
# Created by pi-bt-hub installer

<user> ALL=(root) NOPASSWD: /bin/systemctl start bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/systemctl stop bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/systemctl restart bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/systemctl status bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/systemctl is-active bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/systemctl is-enabled bt-bridge.service
<user> ALL=(root) NOPASSWD: /bin/journalctl -u bt-bridge.service *
```

## Installation Updates

### install.sh Changes

Add `configure_bridge_sudoers()` function:

```bash
configure_bridge_sudoers() {
    info "Configuring sudoers for bridge service control..."
    
    SUDOERS_FILE="/etc/sudoers.d/pi-bt-hub"
    
    sudo tee "$SUDOERS_FILE" > /dev/null <<EOF
# Pi BT Hub - allow bt-bridge service control without password
$USER ALL=(root) NOPASSWD: /bin/systemctl start bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl stop bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl restart bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl status bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl is-active bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl is-enabled bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/journalctl -u bt-bridge.service *
EOF

    # Validate sudoers file
    if sudo visudo -c -f "$SUDOERS_FILE"; then
        sudo chmod 440 "$SUDOERS_FILE"
        success "Sudoers configured for bridge control"
    else
        error "Invalid sudoers file, removing"
        sudo rm -f "$SUDOERS_FILE"
        return 1
    fi
}
```

Called from `configure_bridge_integration()` when user enables bridge.

### README Updates

Add to "Bridge Integration" section:

```markdown
### Bridge Service Control

When bridge integration is enabled, the dashboard provides controls to 
start/stop/restart the bt-bridge systemd service. This requires sudoers 
configuration to allow the pi-bt-hub user to run systemctl commands.

**Automatic setup (recommended):**
The installer configures this automatically when you enable bridge integration.

**Manual setup:**
Create `/etc/sudoers.d/pi-bt-hub`:
\`\`\`
<your-user> ALL=(root) NOPASSWD: /bin/systemctl start bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/systemctl stop bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/systemctl restart bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/systemctl status bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/systemctl is-active bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/systemctl is-enabled bt-bridge.service
<your-user> ALL=(root) NOPASSWD: /bin/journalctl -u bt-bridge.service *
\`\`\`

Then set permissions: `sudo chmod 440 /etc/sudoers.d/pi-bt-hub`
```

## Error Handling

- If sudo command fails with permission denied, show "Permission denied - check sudoers configuration"
- If service not found, show "Service not installed" with link to bt-bridge docs
- Timeout subprocess calls after 10 seconds
- Log all service control actions for audit trail

## Security Considerations

- Sudoers rules are limited to specific commands only
- No wildcard permissions except for journalctl arguments
- Sudoers file validated with `visudo -c` before activation
- Service name is hardcoded, not user-controllable

## Testing

1. Unit tests for SystemdService class (mock subprocess)
2. Integration test: verify sudoers file syntax
3. Manual test: start/stop/restart from UI
4. Manual test: view logs updates in real-time

## Implementation Order

1. Create `SystemdService` class
2. Add API endpoints
3. Update dashboard template
4. Update installer with sudoers configuration
5. Update README documentation
6. Test on pi-sugar.hemna.com
