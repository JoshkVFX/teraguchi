"""
USB device passthrough / bridge mode.

Allows USB devices (keyboards, Wacom tablets, mice) connected to the client
machine to be forwarded to the Linux server, appearing as real USB devices.

Two modes:
1. **USB/IP mode** (recommended): Uses the Linux kernel's USB/IP subsystem
   (usbip) to attach remote USB devices over the network. This is the most
   compatible approach — the device appears as a real USB device to the server.

2. **USB-VHCI mode** (legacy): Uses the Virtual Host Controller Interface
   to create virtual USB devices. Similar to what HP Anywhere used.

Both approaches work by:
- Client captures raw USB device data (via libusb/WinUSB/IOKit)
- Data is tunneled over the Teragucci WebSocket connection
- Server presents the device via usbip or vhci

For the client side, USB device enumeration and forwarding is handled
by a helper process (teragucci-usb-helper) that uses platform-native
USB APIs.
"""

import logging
import subprocess
import os
import json
import asyncio
from typing import Optional, List, Callable
from dataclasses import dataclass, asdict

from common.messages import MsgType

logger = logging.getLogger(__name__)


@dataclass
class USBDeviceInfo:
    """Describes a USB device available for passthrough."""
    bus_id: str = ""
    vendor_id: str = ""
    product_id: str = ""
    manufacturer: str = ""
    product: str = ""
    device_class: str = ""
    forwarding: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "USBDeviceInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class USBIPServer:
    """
    Server-side USB/IP manager.

    Uses the Linux kernel's USB/IP subsystem to attach remote USB devices.
    The client runs usbip in export mode, and the server attaches them.

    Prerequisites:
    - Kernel modules: vhci-hcd, usbip-core
    - Package: linux-tools-common (usbip userspace tools)
    """

    def __init__(self):
        self._attached: dict = {}  # bus_id -> port
        self._available = self._check_available()

    def _check_available(self) -> bool:
        """Check if USB/IP kernel modules and tools are available."""
        # Check kernel modules
        try:
            subprocess.run(
                ["modprobe", "vhci-hcd"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("vhci-hcd kernel module not available")
            return False

        # Check usbip tool
        try:
            result = subprocess.run(
                ["usbip", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info("USB/IP available: %s", result.stdout.strip())
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.warning("usbip tools not found (install linux-tools-common)")
        return False

    @property
    def available(self) -> bool:
        return self._available

    def list_remote_devices(self, client_host: str) -> List[USBDeviceInfo]:
        """List USB devices exported by a client."""
        if not self._available:
            return []

        try:
            result = subprocess.run(
                ["usbip", "list", "-r", client_host],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("Failed to list remote devices: %s", result.stderr)
                return []

            return self._parse_device_list(result.stdout)
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.error("Error listing remote devices: %s", e)
            return []

    def _parse_device_list(self, output: str) -> List[USBDeviceInfo]:
        """Parse usbip list output into USBDeviceInfo objects."""
        devices = []
        current = None

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Lines like: "1-1: Wacom Co., Ltd : Intuos Pro (056a:0357)"
            if ":" in line and "(" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    bus_id = parts[0].strip()
                    # Extract vendor:product from parentheses
                    rest = ":".join(parts[1:])
                    vid_pid = ""
                    if "(" in rest and ")" in rest:
                        vid_pid = rest[rest.rindex("(") + 1:rest.rindex(")")]
                        product_name = rest[:rest.rindex("(")].strip()
                    else:
                        product_name = rest.strip()
                        vid_pid = "0000:0000"

                    vid, pid = vid_pid.split(":") if ":" in vid_pid else ("0000", "0000")

                    devices.append(USBDeviceInfo(
                        bus_id=bus_id,
                        vendor_id=vid,
                        product_id=pid,
                        product=product_name,
                    ))

        return devices

    def attach_device(self, client_host: str, bus_id: str) -> bool:
        """
        Attach a remote USB device from the client.

        This makes the device appear as a local USB device on the server.
        """
        if not self._available:
            return False

        if bus_id in self._attached:
            logger.warning("Device %s already attached", bus_id)
            return True

        try:
            result = subprocess.run(
                ["usbip", "attach", "-r", client_host, "-b", bus_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("Attached USB device %s from %s", bus_id, client_host)
                self._attached[bus_id] = client_host
                return True
            else:
                logger.error("Failed to attach %s: %s", bus_id, result.stderr)
                return False
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.error("Error attaching device: %s", e)
            return False

    def detach_device(self, bus_id: str) -> bool:
        """Detach a previously attached USB device."""
        if bus_id not in self._attached:
            return True

        try:
            # Find the port number
            result = subprocess.run(
                ["usbip", "port"],
                capture_output=True, text=True, timeout=5,
            )
            # Parse port list to find our device
            port = self._find_port_for_device(result.stdout, bus_id)
            if port is not None:
                detach_result = subprocess.run(
                    ["usbip", "detach", "-p", str(port)],
                    capture_output=True, text=True, timeout=5,
                )
                if detach_result.returncode == 0:
                    self._attached.pop(bus_id, None)
                    logger.info("Detached USB device %s", bus_id)
                    return True

            self._attached.pop(bus_id, None)
            return True
        except Exception as e:
            logger.error("Error detaching device: %s", e)
            return False

    def _find_port_for_device(self, port_output: str, bus_id: str) -> Optional[int]:
        """Parse 'usbip port' output to find port number for a bus_id."""
        for line in port_output.split("\n"):
            if bus_id in line:
                # Line format: "Port 00: <...>"
                if line.strip().startswith("Port"):
                    try:
                        port_str = line.split(":")[0].replace("Port", "").strip()
                        return int(port_str)
                    except ValueError:
                        pass
        return None

    def detach_all(self):
        """Detach all attached devices."""
        for bus_id in list(self._attached.keys()):
            self.detach_device(bus_id)

    def list_attached(self) -> List[str]:
        """List currently attached device bus IDs."""
        return list(self._attached.keys())


class USBForwardingManager:
    """
    High-level USB forwarding manager that coordinates between
    client device exports and server attachments.

    Integrates with the Teragucci protocol to handle USB device
    list/attach/detach messages over the WebSocket connection.
    """

    def __init__(self):
        self._usbip = USBIPServer()
        self._client_devices: dict = {}  # client_addr -> [USBDeviceInfo]

    @property
    def available(self) -> bool:
        return self._usbip.available

    def handle_message(self, msg: dict, client_host: str) -> Optional[dict]:
        """
        Handle a USB-related protocol message.

        Returns a response message dict, or None.
        """
        msg_type = msg.get("type")

        if msg_type == MsgType.USB_DEVICE_LIST:
            # Client is advertising available USB devices
            devices = [USBDeviceInfo.from_dict(d) for d in msg.get("devices", [])]
            self._client_devices[client_host] = devices
            logger.info("Client %s has %d USB devices available", client_host, len(devices))
            return {
                "type": MsgType.USB_DEVICE_LIST,
                "devices": [d.to_dict() for d in devices],
                "attached": self._usbip.list_attached(),
            }

        elif msg_type == MsgType.USB_ATTACH:
            bus_id = msg.get("bus_id", "")
            success = self._usbip.attach_device(client_host, bus_id)
            return {
                "type": MsgType.USB_ATTACHED if success else MsgType.USB_ERROR,
                "bus_id": bus_id,
                "success": success,
                "message": "Attached" if success else "Failed to attach",
            }

        elif msg_type == MsgType.USB_DETACH:
            bus_id = msg.get("bus_id", "")
            success = self._usbip.detach_device(bus_id)
            return {
                "type": MsgType.USB_DETACHED if success else MsgType.USB_ERROR,
                "bus_id": bus_id,
                "success": success,
            }

        return None

    def cleanup(self):
        """Detach all devices on shutdown."""
        self._usbip.detach_all()


def check_usbip_available() -> bool:
    """Quick check if USB/IP is available on this system."""
    try:
        result = subprocess.run(
            ["usbip", "version"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def setup_usbip_modules():
    """Load required kernel modules for USB/IP."""
    modules = ["usbip-core", "vhci-hcd"]
    for mod in modules:
        try:
            subprocess.run(["modprobe", mod], capture_output=True, timeout=5)
            logger.info("Loaded kernel module: %s", mod)
        except Exception as e:
            logger.warning("Failed to load %s: %s", mod, e)
