# Pi BT Hub - Installation Guide

Complete installation instructions for Raspberry Pi Zero W, Pi Zero 2 W, and other Pi models.

## Platform Comparison

| Feature | Pi Zero W | Pi Zero 2 W | Pi 3/4/5 |
|---------|-----------|-------------|----------|
| CPU architecture | armv6l | armv7l (32-bit OS) / aarch64 (64-bit OS) | armv7l / aarch64 |
| RAM | 512 MB | 512 MB | 1-8 GB |
| piwheels support | No (armv6l not supported) | Yes | Yes |
| Install time | 30-60 min (compiles from source) | ~5 min | ~2 min |
| Swap increase needed | Yes (1 GB recommended) | Optional | No |
| Bluetooth | Built-in BLE | Built-in BLE | Built-in BLE |

## Prerequisites (All Platforms)

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# Install system dependencies
sudo apt-get install -y \
    python3 python3-venv python3-pip python3-dev \
    libglib2.0-dev \
    bluetooth bluez

# Ensure Bluetooth is enabled
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Verify Bluetooth adapter
bluetoothctl show
```

## Check Your Architecture

Before installing, confirm which CPU architecture you're running:

```bash
uname -m
```

| Output | Board | Install Section |
|--------|-------|-----------------|
| `armv6l` | Pi Zero W (original) | [Pi Zero W](#raspberry-pi-zero-w-armv6l) |
| `armv7l` | Pi Zero 2 W (32-bit OS), Pi 3/4 | [Pi Zero 2 W / Standard](#raspberry-pi-zero-2-w-and-standard-boards) |
| `aarch64` | Pi Zero 2 W (64-bit OS), Pi 3/4/5 | [Pi Zero 2 W / Standard](#raspberry-pi-zero-2-w-and-standard-boards) |

---

## Raspberry Pi Zero 2 W and Standard Boards

Applies to: **Pi Zero 2 W**, Pi 2, Pi 3, Pi 4, Pi 5 (armv7l or aarch64).

These boards benefit from [piwheels.org](https://www.piwheels.org/) which provides pre-built ARM wheels. Raspberry Pi OS ships with piwheels pre-configured, so pip will automatically download pre-compiled binaries instead of compiling from source.

### Step 1: Verify piwheels is Configured

Raspberry Pi OS includes piwheels by default. Verify:

```bash
pip config list
```

You should see a line like:

```
global.extra-index-url='https://www.piwheels.org/simple'
```

If it's missing (custom OS image, Ubuntu, etc.), add it:

```bash
sudo tee /etc/pip.conf > /dev/null <<EOF
[global]
extra-index-url=https://www.piwheels.org/simple
EOF
```

### Step 2: Clone and Install

```bash
# Clone the repository
git clone https://github.com/hemna/pi-bt-hub.git
cd pi-bt-hub

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (piwheels provides pre-built wheels)
pip install -r backend/requirements.txt
pip install -e backend/

# Install websockets for real-time updates
pip install websockets
```

This should complete in under 5 minutes with piwheels providing pre-built wheels for most packages.

### Step 3: Verify Installation

```bash
source .venv/bin/activate
python -c "import bt_hub; print('bt_hub OK')"
python -c "import fastapi; print('fastapi OK')"
python -c "import dbus_fast; print('dbus_fast OK')"
```

---

## Raspberry Pi Zero W (armv6l)

Applies to: **Pi Zero W** (original, BCM2835 single-core).

The Pi Zero W uses the armv6l architecture. piwheels.org does **not** build wheels for armv6l, which means all Python packages with C extensions must be compiled from source on the device. This is slow due to the single-core CPU and limited RAM.

### Step 1: Increase Swap Space

The default 100 MB swap is insufficient for compiling packages like `dbus-fast` and `pydantic`. Increase to 1 GB:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Verify
free -h
# Should show ~1.0G swap
```

### Step 2: Install Build Dependencies

```bash
sudo apt-get install -y \
    python3-dev \
    libglib2.0-dev \
    libffi-dev \
    build-essential
```

### Step 3: Clone the Repository

```bash
git clone https://github.com/hemna/pi-bt-hub.git
cd pi-bt-hub
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and setuptools (armv6l ships older versions)
pip install --upgrade pip setuptools wheel
```

### Step 4: Install Dependencies (One at a Time)

Installing packages individually avoids pip's memory-intensive dependency resolver choking on the limited RAM:

```bash
# These pure-Python packages install quickly
pip install jinja2 python-multipart aiosqlite httpx websockets

# These have Rust/C extensions and take longer
pip install pydantic pydantic-settings    # ~5-10 min
pip install fastapi                        # ~2 min
pip install uvicorn                        # ~2 min (no [standard] extra on armv6l)
pip install dbus-fast                      # ~10-20 min (Cython compilation)
```

> **Tip**: If a package fails to compile with a memory error, try installing it alone with no other processes running, or temporarily increase swap further:
> ```bash
> sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
> sudo dphys-swapfile setup && sudo dphys-swapfile swapon
> ```

### Step 5: Install the Application

```bash
# Use --no-deps since we already installed dependencies individually
pip install --no-deps -e backend/
```

### Step 6: Verify Installation

```bash
python -c "import bt_hub; print('bt_hub OK')"
python -c "import fastapi; print('fastapi OK')"
python -c "import dbus_fast; print('dbus_fast OK')"
```

### Step 7: Restore Swap (Optional)

After installation, you can reduce swap back to preserve SD card life:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=256/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

---

## About piwheels

[piwheels.org](https://www.piwheels.org/) is a Python package repository providing pre-built ARM wheels for Raspberry Pi. It is maintained by the Raspberry Pi community and dramatically reduces install times by eliminating the need to compile C/Rust extensions on the device.

### How It Works

- pip checks piwheels alongside PyPI when resolving packages
- If a pre-built wheel exists for your architecture, it downloads the binary
- If no wheel exists, pip falls back to source compilation from PyPI

### Architecture Coverage

| Architecture | piwheels Support | Boards |
|-------------|------------------|--------|
| armv6l | **Not supported** | Pi Zero W (original), Pi 1 |
| armv7l | Supported | Pi Zero 2 W (32-bit OS), Pi 2/3/4 |
| aarch64 | Supported | Pi Zero 2 W (64-bit OS), Pi 3/4/5 |

### Configuring piwheels

Raspberry Pi OS configures piwheels automatically in `/etc/pip.conf`. If you're using another distribution or the configuration is missing:

```bash
# System-wide configuration
sudo tee /etc/pip.conf > /dev/null <<EOF
[global]
extra-index-url=https://www.piwheels.org/simple
EOF
```

Or per-user:

```bash
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf <<EOF
[global]
extra-index-url=https://www.piwheels.org/simple
EOF
```

Or per-install:

```bash
pip install --extra-index-url https://www.piwheels.org/simple <package>
```

### Checking Available Wheels

You can check if a specific package has a piwheels build for your architecture:

```bash
# Visit the package page
# https://www.piwheels.org/project/<package-name>/
# e.g., https://www.piwheels.org/project/dbus-fast/
```

---

## Setting Up the systemd Service

After installation on any platform:

```bash
# Copy the service file
sudo cp systemd/bt-hub.service /etc/systemd/system/

# Edit paths and user to match your setup
sudo nano /etc/systemd/system/bt-hub.service

# Reload, enable, and start
sudo systemctl daemon-reload
sudo systemctl enable bt-hub
sudo systemctl start bt-hub

# Verify it's running
sudo systemctl status bt-hub
sudo journalctl -u bt-hub -f
```

### Service File Customization

Edit the service file to match your username and install path:

```ini
[Service]
User=<your-username>
Group=<your-username>
WorkingDirectory=/home/<your-username>/pi-bt-hub
ExecStart=/home/<your-username>/pi-bt-hub/.venv/bin/uvicorn bt_hub.main:app --host 0.0.0.0 --port 8080
```

---

## Troubleshooting Installation

### `error: externally-managed-environment`

Raspberry Pi OS Bookworm and later use PEP 668 to prevent pip from modifying system packages. Always use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Compilation fails with "Killed" or memory errors

This typically happens on Pi Zero W. Increase swap space and install packages one at a time. See [Step 1](#step-1-increase-swap-space) in the Pi Zero W section.

### `dbus-fast` won't compile

Ensure build dependencies are installed:

```bash
sudo apt-get install -y python3-dev libglib2.0-dev libffi-dev build-essential
```

If it still fails, try with increased swap (2 GB):

```bash
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
pip install dbus-fast
```

### pip is very slow on Pi Zero W

This is expected. The single-core armv6l CPU must compile packages from source. Use `screen` or `tmux` so you can disconnect and reconnect:

```bash
sudo apt-get install -y screen
screen -S install
# Run your pip install commands...
# Detach with Ctrl-A, D
# Reattach with: screen -r install
```

### Bluetooth permission denied

```bash
# Add your user to the bluetooth group
sudo usermod -a -G bluetooth $USER
# Log out and back in, or:
newgrp bluetooth
```
