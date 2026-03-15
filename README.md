# Pi BT Hub

A web-based Bluetooth management interface for Raspberry Pi, with optional integration for the BT Bridge daemon that bridges Bluetooth LE to Classic Bluetooth for TNC (Terminal Node Controller) devices.

## Features

- **Device Management**: Scan, discover, and manage Bluetooth devices
- **Favorites**: Mark devices as favorites for quick access
- **Bridge Integration**: Optional integration with bt-bridge daemon for BLE-to-Classic bridging
- **TCP KISS Server**: Configurable TCP KISS server port to avoid conflicts with direwolf
- **Real-time Updates**: WebSocket-based live updates during scanning
- **Responsive UI**: Works on desktop and mobile browsers

## Requirements

- Raspberry Pi (tested on Pi Zero W, Pi Zero 2 W, Pi 3, Pi 4)
- Raspberry Pi OS (Bookworm or Trixie recommended)
- Python 3.11+
- Bluetooth adapter (built-in or USB)

## Installation

> **Detailed guide**: See [docs/INSTALL.md](docs/INSTALL.md) for complete platform-specific instructions, including piwheels configuration and troubleshooting.

### Quick Install (Raspberry Pi 2/3/4/5 and Pi Zero 2 W)

These boards use armv7l or aarch64 and have pre-built wheels available from [piwheels.org](https://www.piwheels.org/). Installation is straightforward:

```bash
# Clone the repository
git clone https://github.com/hemna/pi-bt-hub.git
cd pi-bt-hub

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
pip install -e backend/

# Install websockets for real-time updates
pip install websockets
```

### Raspberry Pi Zero W (armv6l)

The original Pi Zero W uses an armv6l CPU. Most piwheels packages target armv7l and above, so many dependencies must be compiled from source. This is slow (~30-60 minutes) and requires extra swap space. See [docs/INSTALL.md](docs/INSTALL.md) for the full walkthrough.

**Quick summary:**

```bash
# 1. Increase swap to 1GB (required for compilation)
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# 2. Install build dependencies
sudo apt-get install -y python3-dev libglib2.0-dev

# 3. Clone and set up
git clone https://github.com/hemna/pi-bt-hub.git
cd pi-bt-hub
python3 -m venv .venv
source .venv/bin/activate

# 4. Install packages individually (avoids pip memory issues)
pip install fastapi uvicorn jinja2 aiosqlite httpx python-multipart websockets
pip install pydantic pydantic-settings
pip install dbus-fast  # This one takes longest to compile
pip install --no-deps -e backend/
```

### Using piwheels (Raspberry Pi OS default)

Raspberry Pi OS ships with [piwheels.org](https://www.piwheels.org/) pre-configured in `/etc/pip.conf`. This provides pre-built ARM wheels and dramatically speeds up installs on armv7l and aarch64 boards (Pi Zero 2 W, Pi 3/4/5).

If piwheels is not configured (e.g., you are using a custom OS image), you can add it manually:

```bash
# Check if piwheels is already configured
pip config list

# If not present, add it
sudo tee /etc/pip.conf > /dev/null <<EOF
[global]
extra-index-url=https://www.piwheels.org/simple
EOF
```

> **Note**: piwheels does not provide armv6l wheels. On the original Pi Zero W, packages with C extensions will always be compiled from source regardless of this setting.

## Running

### Development Mode

```bash
source .venv/bin/activate
uvicorn bt_hub.main:app --host 0.0.0.0 --port 8080 --reload
```

### Production (systemd)

Copy the service file and enable it:

```bash
sudo cp systemd/bt-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bt-hub
sudo systemctl start bt-hub
```

Check status:

```bash
sudo systemctl status bt-hub
sudo journalctl -u bt-hub -f
```

## Configuration

Configuration is done via environment variables. Set these in the systemd service file or export them before running.

| Variable | Default | Description |
|----------|---------|-------------|
| `BT_HUB_HOST` | `0.0.0.0` | Listen address |
| `BT_HUB_PORT` | `8080` | Listen port |
| `BT_HUB_DB_PATH` | `data/bt_hub.db` | SQLite database path |
| `BT_HUB_LOG_LEVEL` | `INFO` | Log level |
| `BT_HUB_BRIDGE_ENABLED` | `false` | Enable bridge integration |
| `BT_HUB_BRIDGE_URL` | `http://localhost:8081` | Bridge daemon URL |

### Systemd Service Configuration

Edit `/etc/systemd/system/bt-hub.service`:

```ini
[Unit]
Description=Pi BT Hub - Unified Bluetooth Management Web UI
After=network.target bluetooth.target
Wants=bt-bridge.service

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/pi-bt-hub
Environment=BT_HUB_BRIDGE_ENABLED=true
Environment=BT_HUB_BRIDGE_URL=http://localhost:8081
ExecStart=/home/pi/pi-bt-hub/.venv/bin/uvicorn bt_hub.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Bridge Integration

Pi BT Hub can integrate with the [bt-bridge](https://github.com/hemna/pi-bt-bridge) daemon to provide a web interface for managing the Bluetooth LE to Classic bridge.

### Enabling Bridge Integration

1. Install and configure bt-bridge daemon (see bt-bridge documentation)
2. Set `BT_HUB_BRIDGE_ENABLED=true` in your environment
3. Set `BT_HUB_BRIDGE_URL` to point to your bridge daemon (default: `http://localhost:8081`)
4. Restart bt-hub

### Bridge Features

When bridge integration is enabled, the UI provides:

- **Bridge Status**: Real-time status of BLE and Classic Bluetooth connections
- **TNC Management**: Add, edit, and remove TNC devices from history
- **Connection Control**: Connect/disconnect from TNC devices
- **TCP KISS Server**: Configure the TCP KISS server port

### TCP KISS Server Port

The bridge daemon runs a TCP KISS server that allows applications (like direwolf or APRS clients) to connect. By default, it listens on port 8001.

If you're running direwolf on the same host (which also defaults to port 8001), you'll need to change one of them. To change the bridge's TCP KISS port:

1. Go to **Settings** in the web UI
2. Find the **Bridge Settings** section
3. Change the **TCP KISS Server Port** to a different port (e.g., 8002)
4. Click **Save Bridge Settings**
5. Confirm the restart when prompted

The bridge will automatically restart with the new port.

## Web Interface

Access the web interface at `http://<pi-address>:8080`

### Pages

- **Dashboard** (`/`): Overview with quick actions and bridge status
- **Devices** (`/devices`): List all discovered Bluetooth devices
- **Bridge** (`/bridge`): Bridge status and TNC connection management (when enabled)
- **TNC Devices** (`/bridge/tnc`): Manage TNC device history (when enabled)
- **Settings** (`/settings`): Configure app and bridge settings
- **Logs** (`/logs`): View application logs

## Troubleshooting

### Scan not showing devices

1. Check Bluetooth adapter is powered on:
   ```bash
   bluetoothctl show
   ```

2. Check bt-hub logs:
   ```bash
   sudo journalctl -u bt-hub -f
   ```

3. Ensure websockets is installed for real-time updates:
   ```bash
   pip install websockets
   sudo systemctl restart bt-hub
   ```

### Bridge not connecting

1. Check bt-bridge daemon is running:
   ```bash
   sudo systemctl status bt-bridge
   ```

2. Verify bridge URL is correct in bt-hub config

3. Check bridge logs:
   ```bash
   sudo journalctl -u bt-bridge -f
   ```

### Permission errors

Ensure your user is in the `bluetooth` group:

```bash
sudo usermod -a -G bluetooth $USER
# Log out and back in for changes to take effect
```

## License

MIT License - see LICENSE file for details.
