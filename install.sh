#!/bin/bash
#
# Pi BT Hub Installer
# 
# This script installs pi-bt-hub and configures the necessary permissions
# for Bluetooth access via D-Bus.
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default installation directory
INSTALL_DIR="${INSTALL_DIR:-$HOME/pi-bt-hub}"
PYTHON="${PYTHON:-python3}"
USE_UV="${USE_UV:-auto}"

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root (we need sudo for some operations)
check_sudo() {
    if ! command -v sudo &> /dev/null; then
        error "sudo is required but not installed"
        exit 1
    fi
    
    # Test sudo access
    if ! sudo -n true 2>/dev/null; then
        info "This installer needs sudo access for system configuration"
        sudo -v
    fi
}

# Check and fix Bluetooth group membership
check_bluetooth_group() {
    info "Checking Bluetooth group membership..."
    
    # Check if bluetooth group exists
    if ! getent group bluetooth > /dev/null 2>&1; then
        warn "bluetooth group does not exist, creating..."
        sudo groupadd bluetooth
    fi
    
    # Check if current user is in bluetooth group
    if groups | grep -q '\bbluetooth\b'; then
        success "User '$USER' is already in bluetooth group"
    else
        info "Adding user '$USER' to bluetooth group..."
        sudo usermod -aG bluetooth "$USER"
        success "Added '$USER' to bluetooth group"
        NEED_RELOGIN=1
    fi
}

# Check and fix rfkill status
check_rfkill() {
    info "Checking rfkill status..."
    
    # Find rfkill binary
    RFKILL=""
    if command -v rfkill &> /dev/null; then
        RFKILL="rfkill"
    elif [ -x /usr/sbin/rfkill ]; then
        RFKILL="/usr/sbin/rfkill"
    fi
    
    if [ -z "$RFKILL" ]; then
        warn "rfkill not found, skipping check"
        return
    fi
    
    # Check if Bluetooth is blocked
    if sudo $RFKILL list bluetooth 2>/dev/null | grep -q "Soft blocked: yes"; then
        warn "Bluetooth is soft-blocked by rfkill"
        info "Unblocking Bluetooth..."
        sudo $RFKILL unblock bluetooth
        success "Bluetooth unblocked"
        
        # Offer to make it persistent
        echo ""
        read -p "Make Bluetooth unblock persistent across reboots? [Y/n] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            create_rfkill_service
        fi
    else
        success "Bluetooth is not blocked"
    fi
    
    # Check for hard block
    if sudo $RFKILL list bluetooth 2>/dev/null | grep -q "Hard blocked: yes"; then
        error "Bluetooth is hardware-blocked (physical switch?)"
        error "Please enable Bluetooth hardware switch and re-run installer"
        exit 1
    fi
}

# Create systemd service to unblock Bluetooth on boot
create_rfkill_service() {
    info "Creating rfkill-unblock-bluetooth service..."
    
    sudo tee /etc/systemd/system/rfkill-unblock-bluetooth.service > /dev/null <<EOF
[Unit]
Description=Unblock Bluetooth adapter
Before=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/rfkill unblock bluetooth
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable rfkill-unblock-bluetooth
    success "Created and enabled rfkill-unblock-bluetooth service"
}

# Check D-Bus policy
check_dbus_policy() {
    info "Checking D-Bus policy for BlueZ..."
    
    # Check if default policy allows bluetooth group
    POLICY_FILE="/etc/dbus-1/system.d/pi-bt-hub.conf"
    
    if [ -f "$POLICY_FILE" ]; then
        success "D-Bus policy file already exists"
    else
        info "Creating D-Bus policy for bluetooth group..."
        sudo tee "$POLICY_FILE" > /dev/null <<'EOF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <!-- Allow bluetooth group to control BlueZ -->
  <policy group="bluetooth">
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.Adapter1"/>
    <allow send_interface="org.bluez.Device1"/>
    <allow send_interface="org.bluez.Agent1"/>
    <allow send_interface="org.bluez.AgentManager1"/>
    <allow send_interface="org.freedesktop.DBus.ObjectManager"/>
    <allow send_interface="org.freedesktop.DBus.Properties"/>
  </policy>
</busconfig>
EOF
        success "Created D-Bus policy file"
        
        # Reload D-Bus
        if sudo systemctl reload dbus 2>/dev/null; then
            success "Reloaded D-Bus configuration"
        else
            warn "Could not reload D-Bus, a reboot may be required"
        fi
    fi
}

# Check Python version
check_python() {
    info "Checking Python version..."
    
    if ! command -v "$PYTHON" &> /dev/null; then
        error "Python not found. Please install Python 3.11+"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
        error "Python 3.11+ required, found $PYTHON_VERSION"
        exit 1
    fi
    
    success "Python $PYTHON_VERSION found"
}

# Check/install uv
check_uv() {
    if [ "$USE_UV" = "no" ]; then
        return 1
    fi
    
    info "Checking for uv package manager..."
    
    # Check if uv is available
    if command -v uv &> /dev/null; then
        success "uv is already installed"
        return 0
    fi
    
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
        success "uv found at ~/.local/bin/uv"
        return 0
    fi
    
    if [ "$USE_UV" = "auto" ]; then
        echo ""
        read -p "Install uv for faster package installation? [Y/n] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            return 1
        fi
    fi
    
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    success "uv installed"
    return 0
}

# Install with uv
install_with_uv() {
    info "Installing with uv..."
    
    cd "$INSTALL_DIR"
    
    # Create venv
    info "Creating virtual environment..."
    uv venv --python 3.11 || uv venv
    
    # Check architecture for piwheels
    ARCH=$(uname -m)
    EXTRA_INDEX=""
    if [[ "$ARCH" == "armv7l" ]] || [[ "$ARCH" == "aarch64" ]]; then
        info "Detected ARM architecture, using piwheels.org"
        EXTRA_INDEX="--extra-index-url https://www.piwheels.org/simple"
    fi
    
    # Install
    info "Installing dependencies (this may take a few minutes)..."
    uv pip install $EXTRA_INDEX -e ".[dev]" 2>/dev/null || \
    uv pip install $EXTRA_INDEX -e .
    
    success "Installation complete"
}

# Install with pip
install_with_pip() {
    info "Installing with pip..."
    
    cd "$INSTALL_DIR"
    
    # Create venv
    info "Creating virtual environment..."
    $PYTHON -m venv .venv
    source .venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Check architecture for piwheels
    ARCH=$(uname -m)
    EXTRA_INDEX=""
    if [[ "$ARCH" == "armv7l" ]] || [[ "$ARCH" == "aarch64" ]]; then
        info "Detected ARM architecture, using piwheels.org"
        EXTRA_INDEX="--extra-index-url https://www.piwheels.org/simple"
    fi
    
    # Install
    info "Installing dependencies (this may take several minutes on Pi)..."
    pip install $EXTRA_INDEX -e ".[dev]" 2>/dev/null || \
    pip install $EXTRA_INDEX -e .
    
    success "Installation complete"
}

# Create systemd service
create_service() {
    echo ""
    read -p "Create systemd service for pi-bt-hub? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        return
    fi
    
    info "Creating systemd service..."
    
    # Determine the venv python path
    if [ -x "$INSTALL_DIR/.venv/bin/uvicorn" ]; then
        UVICORN_PATH="$INSTALL_DIR/.venv/bin/uvicorn"
    else
        error "uvicorn not found in venv"
        return
    fi
    
    sudo tee /etc/systemd/system/pi-bt-hub.service > /dev/null <<EOF
[Unit]
Description=Pi BT Hub - Bluetooth Management Web UI
After=network.target bluetooth.target
Wants=bluetooth.service

[Service]
Type=simple
User=$USER
Group=$USER
SupplementaryGroups=bluetooth
WorkingDirectory=$INSTALL_DIR
Environment=BT_HUB_HOST=0.0.0.0
Environment=BT_HUB_PORT=8080
ExecStart=$UVICORN_PATH bt_hub.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    success "Created pi-bt-hub.service"
    
    # Ask about bridge integration
    configure_bridge_integration
    
    echo ""
    read -p "Enable and start pi-bt-hub service now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        sudo systemctl enable pi-bt-hub
        sudo systemctl start pi-bt-hub
        success "Service enabled and started"
        info "Access the web UI at http://$(hostname -I | awk '{print $1}'):8080"
    fi
}

# Install system dependencies required for bt-bridge
install_bridge_dependencies() {
    info "Installing system dependencies for bt-bridge..."
    
    # List of required packages for bt-bridge installation
    # - python3-pip: Required for pip install (bt-bridge uses pip)
    # - libgirepository1.0-dev: Required for PyGObject (D-Bus/GLib bindings)
    # - python3-gi: GObject introspection bindings for Python
    # - gir1.2-glib-2.0: GLib introspection data
    BRIDGE_DEPS="python3-pip libgirepository1.0-dev python3-gi gir1.2-glib-2.0"
    
    # Check which packages are missing
    MISSING_PKGS=""
    for pkg in $BRIDGE_DEPS; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            MISSING_PKGS="$MISSING_PKGS $pkg"
        fi
    done
    
    if [ -n "$MISSING_PKGS" ]; then
        info "Installing:$MISSING_PKGS"
        sudo apt-get update -qq
        sudo apt-get install -y $MISSING_PKGS
        success "Bridge dependencies installed"
    else
        success "All bridge dependencies already installed"
    fi
}

# Configure bridge integration
configure_bridge_integration() {
    echo ""
    read -p "Enable bt-bridge integration? (requires bt-bridge daemon) [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        return
    fi
    
    info "Configuring bridge integration..."
    
    # Install system dependencies needed for bt-bridge
    install_bridge_dependencies
    
    # Check if bt-bridge.service exists
    if ! systemctl list-unit-files bt-bridge.service &>/dev/null; then
        warn "bt-bridge.service not found"
        warn "Bridge integration configured, but bt-bridge daemon needs to be installed separately"
        warn "You can install it from the web UI or manually from: https://github.com/hemna/pi-bt-bridge"
    fi
    
    # Create drop-in directory
    sudo mkdir -p /etc/systemd/system/pi-bt-hub.service.d
    
    # Create bridge override
    sudo tee /etc/systemd/system/pi-bt-hub.service.d/bridge.conf > /dev/null <<EOF
# Bridge integration for pi-bt-hub
# Auto-generated by install.sh

[Unit]
# Start bt-bridge.service if available (soft dependency)
Wants=bt-bridge.service
# Wait for bt-bridge to start first
After=bt-bridge.service

[Service]
# Enable bridge integration
Environment=BT_HUB_BRIDGE_ENABLED=true
Environment=BT_HUB_BRIDGE_URL=http://localhost:8081
EOF
    
    sudo systemctl daemon-reload
    success "Bridge integration enabled"
    info "pi-bt-hub will automatically start bt-bridge.service (if installed)"
    
    # Configure sudoers for service control
    configure_bridge_sudoers
}

# Configure sudoers for bridge service control
configure_bridge_sudoers() {
    info "Configuring sudoers for bridge service control..."
    
    SUDOERS_FILE="/etc/sudoers.d/pi-bt-hub"
    SUDOERS_TMP="/tmp/pi-bt-hub-sudoers.tmp"
    
    # Create sudoers content
    cat > "$SUDOERS_TMP" <<EOF
# Pi BT Hub - allow bt-bridge service control without password
# Auto-generated by install.sh
# User: $USER

# Service control
$USER ALL=(root) NOPASSWD: /bin/systemctl start bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl stop bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl restart bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl status bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl is-active bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl is-enabled bt-bridge.service
$USER ALL=(root) NOPASSWD: /bin/systemctl show bt-bridge.service *
$USER ALL=(root) NOPASSWD: /bin/journalctl -u bt-bridge.service *

# bt-bridge installation (one-click install from web UI)
# The wrapper script is created by pi-bt-hub to cd into the repo before running install
$USER ALL=(root) NOPASSWD: /tmp/bt-bridge-install-wrapper.sh
EOF

    # Validate sudoers file syntax
    if sudo visudo -c -f "$SUDOERS_TMP" 2>/dev/null; then
        sudo cp "$SUDOERS_TMP" "$SUDOERS_FILE"
        sudo chmod 440 "$SUDOERS_FILE"
        rm -f "$SUDOERS_TMP"
        success "Sudoers configured for bridge service control"
        info "User '$USER' can now start/stop/restart bt-bridge.service from the web UI"
    else
        error "Invalid sudoers file syntax, skipping"
        rm -f "$SUDOERS_TMP"
        warn "You may need to manually configure sudoers for bridge service control"
        warn "See README.md for manual setup instructions"
    fi
}

# Main installation
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║         Pi BT Hub Installer            ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    
    NEED_RELOGIN=0
    
    # Pre-flight checks
    check_sudo
    check_python
    
    # Bluetooth permissions
    echo ""
    info "=== Bluetooth Permissions ==="
    check_bluetooth_group
    check_rfkill
    check_dbus_policy
    
    # Installation
    echo ""
    info "=== Installing Pi BT Hub ==="
    
    # Check if we're in the project directory or need to use INSTALL_DIR
    if [ -f "backend/pyproject.toml" ]; then
        INSTALL_DIR="$(pwd)/backend"
        info "Installing from current directory: $INSTALL_DIR"
    elif [ -f "pyproject.toml" ]; then
        INSTALL_DIR="$(pwd)"
        info "Installing from current directory: $INSTALL_DIR"
    else
        info "Install directory: $INSTALL_DIR"
        if [ ! -d "$INSTALL_DIR" ]; then
            error "Directory $INSTALL_DIR does not exist"
            error "Please clone the repository first or set INSTALL_DIR"
            exit 1
        fi
        cd "$INSTALL_DIR"
        if [ -f "backend/pyproject.toml" ]; then
            INSTALL_DIR="$INSTALL_DIR/backend"
        fi
    fi
    
    # Install using uv or pip
    if check_uv; then
        install_with_uv
    else
        install_with_pip
    fi
    
    # Create systemd service
    create_service
    
    # Summary
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║         Installation Complete          ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    
    if [ "$NEED_RELOGIN" -eq 1 ]; then
        warn "You were added to the bluetooth group."
        warn "Please log out and back in for changes to take effect."
        echo ""
    fi
    
    success "Pi BT Hub installed to: $INSTALL_DIR"
    echo ""
    info "To run manually:"
    echo "  cd $INSTALL_DIR"
    echo "  source .venv/bin/activate"
    echo "  uvicorn bt_hub.main:app --host 0.0.0.0 --port 8080"
    echo ""
    
    if systemctl is-active --quiet pi-bt-hub 2>/dev/null; then
        info "Service is running. Access at: http://$(hostname -I | awk '{print $1}'):8080"
    fi
}

# Run main
main "$@"
