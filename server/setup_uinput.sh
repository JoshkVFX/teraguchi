#!/bin/bash
# Setup script for Teragucci server on Linux
# Configures uinput permissions so the server can create virtual input devices
# without running as root.
#
# Usage: sudo bash server/setup_uinput.sh

set -e

echo "=== Teragucci Server Setup ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)"
    exit 1
fi

# Create uinput group if it doesn't exist
if ! getent group uinput > /dev/null 2>&1; then
    echo "Creating 'uinput' group..."
    groupadd uinput
fi

# Add current user to uinput group
REAL_USER="${SUDO_USER:-$USER}"
echo "Adding user '$REAL_USER' to 'uinput' group..."
usermod -aG uinput "$REAL_USER"

# Create udev rule for uinput access
UDEV_RULE="/etc/udev/rules.d/99-teragucci-uinput.rules"
echo "Creating udev rule at $UDEV_RULE..."
cat > "$UDEV_RULE" << 'EOF'
# Teragucci: Allow uinput group to access /dev/uinput
KERNEL=="uinput", GROUP="uinput", MODE="0660"
EOF

# Load uinput module
echo "Loading uinput kernel module..."
modprobe uinput

# Load USB/IP modules for USB passthrough
echo "Loading USB/IP kernel modules..."
modprobe usbip-core 2>/dev/null || echo "  usbip-core not available (USB passthrough won't work)"
modprobe vhci-hcd 2>/dev/null || echo "  vhci-hcd not available (USB passthrough won't work)"

# Ensure modules load on boot
MODULES_FILE="/etc/modules-load.d/teragucci.conf"
echo "Configuring kernel modules to load on boot..."
cat > "$MODULES_FILE" << 'MODEOF'
# Teragucci: virtual input devices
uinput
# Teragucci: USB/IP passthrough (optional)
usbip-core
vhci-hcd
MODEOF

# Reload udev rules
echo "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo ""
echo "=== Setup complete ==="
echo ""
echo "IMPORTANT: You need to log out and log back in for the group"
echo "change to take effect, or run: newgrp uinput"
echo ""
echo "After that, start the server with:"
echo "  python -m server.main"
echo ""
echo "Or to test immediately (as root):"
echo "  sudo python -m server.main"
