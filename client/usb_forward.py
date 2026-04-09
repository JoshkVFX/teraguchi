"""
Client-side USB device forwarding.

Enumerates local USB devices and manages forwarding them to the
Teragucci server using USB/IP protocol.

Platform-specific implementation:
- Windows: Uses usbipd-win (https://github.com/dorssel/usbipd-win)
- macOS: Uses virtualhere or usbip (via homebrew)

The client advertises available USB devices to the server, and the
server can request to attach specific devices. The actual USB/IP
tunnel runs alongside the main WebSocket connection.
"""

import logging
import platform
import subprocess
import json
from typing import List, Optional, Callable
from dataclasses import dataclass, asdict

from common.messages import MsgType

logger = logging.getLogger(__name__)


@dataclass
class LocalUSBDevice:
    """A USB device connected to the client machine."""
    bus_id: str = ""
    vendor_id: str = ""
    product_id: str = ""
    manufacturer: str = ""
    product: str = ""
    serial: str = ""
    device_class: str = ""
    is_forwarding: bool = False

    def display_name(self) -> str:
        name = self.product or f"USB {self.vendor_id}:{self.product_id}"
        if self.manufacturer:
            name = f"{self.manufacturer} {name}"
        return name

    def to_dict(self) -> dict:
        return asdict(self)


class USBDeviceEnumerator:
    """
    Enumerate USB devices on the client machine.

    Uses platform-specific tools:
    - Windows: usbipd-win (usbipd.exe)
    - macOS: system_profiler SPUSBDataType + ioreg
    """

    def __init__(self):
        self._system = platform.system()

    def list_devices(self) -> List[LocalUSBDevice]:
        """List all USB devices available for forwarding."""
        if self._system == "Windows":
            return self._list_windows()
        elif self._system == "Darwin":
            return self._list_macos()
        else:
            return self._list_linux()

    def _list_windows(self) -> List[LocalUSBDevice]:
        """List USB devices on Windows using usbipd."""
        devices = []
        try:
            result = subprocess.run(
                ["usbipd", "list"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("usbipd not available: %s", result.stderr)
                return devices

            # Parse usbipd list output
            # Format: BUSID  VID:PID  DEVICE                         STATE
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("BUSID") or line.startswith("-"):
                    continue
                parts = line.split(None, 3)
                if len(parts) >= 3:
                    bus_id = parts[0]
                    vid_pid = parts[1]
                    vid, pid = vid_pid.split(":") if ":" in vid_pid else ("", "")
                    product = parts[2] if len(parts) > 2 else ""
                    state = parts[3].strip() if len(parts) > 3 else ""
                    devices.append(LocalUSBDevice(
                        bus_id=bus_id,
                        vendor_id=vid,
                        product_id=pid,
                        product=product,
                        is_forwarding="Shared" in state or "Attached" in state,
                    ))
        except FileNotFoundError:
            logger.info("usbipd-win not installed. Install from: https://github.com/dorssel/usbipd-win")
        except Exception as e:
            logger.error("Error listing USB devices: %s", e)

        return devices

    def _list_macos(self) -> List[LocalUSBDevice]:
        """List USB devices on macOS using system_profiler."""
        devices = []
        try:
            result = subprocess.run(
                ["system_profiler", "SPUSBDataType", "-json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                self._parse_macos_usb(data.get("SPUSBDataType", []), devices)
        except Exception as e:
            logger.error("Error listing macOS USB devices: %s", e)

        return devices

    def _parse_macos_usb(self, items: list, devices: list, depth: int = 0):
        """Recursively parse macOS USB device tree."""
        for item in items:
            if isinstance(item, dict):
                vid = item.get("vendor_id", "")
                pid = item.get("product_id", "")
                if vid and pid:
                    # Clean up hex format
                    vid = vid.replace("0x", "").strip()
                    pid = pid.replace("0x", "").strip()
                    devices.append(LocalUSBDevice(
                        bus_id=item.get("location_id", ""),
                        vendor_id=vid,
                        product_id=pid,
                        manufacturer=item.get("manufacturer", ""),
                        product=item.get("_name", ""),
                        serial=item.get("serial_num", ""),
                    ))
                # Recurse into child hubs
                if "_items" in item:
                    self._parse_macos_usb(item["_items"], devices, depth + 1)

    def _list_linux(self) -> List[LocalUSBDevice]:
        """List USB devices on Linux using lsusb."""
        devices = []
        try:
            result = subprocess.run(
                ["lsusb"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                # Format: Bus 001 Device 002: ID 056a:0357 Wacom Co., Ltd Intuos Pro
                parts = line.split()
                if len(parts) >= 6 and parts[5] != "":
                    bus = parts[1]
                    dev = parts[3].rstrip(":")
                    vid_pid = parts[5]
                    vid, pid = vid_pid.split(":") if ":" in vid_pid else ("", "")
                    product = " ".join(parts[6:]) if len(parts) > 6 else ""
                    devices.append(LocalUSBDevice(
                        bus_id=f"{bus}-{dev}",
                        vendor_id=vid,
                        product_id=pid,
                        product=product,
                    ))
        except Exception as e:
            logger.error("Error listing Linux USB devices: %s", e)

        return devices


class USBForwardClient:
    """
    Manages USB device forwarding from the client to the server.

    Handles:
    - Enumerating local devices
    - Starting USB/IP export on selected devices
    - Sending device list to server
    - Processing attach/detach requests
    """

    def __init__(self):
        self._enumerator = USBDeviceEnumerator()
        self._system = platform.system()
        self._forwarding: set = set()  # bus_ids currently forwarding
        self._on_device_list_changed: Optional[Callable] = None

    def list_devices(self) -> List[LocalUSBDevice]:
        """Get current list of USB devices."""
        devices = self._enumerator.list_devices()
        for dev in devices:
            dev.is_forwarding = dev.bus_id in self._forwarding
        return devices

    def start_forwarding(self, bus_id: str) -> bool:
        """
        Start forwarding a USB device to the server.

        Windows: usbipd bind --busid <id> && usbipd attach --wsl
        macOS: Uses VirtualHere or manual usbip export
        """
        if self._system == "Windows":
            return self._forward_windows(bus_id)
        elif self._system == "Darwin":
            logger.warning("macOS USB forwarding requires VirtualHere or manual usbip setup")
            return False
        else:
            return self._forward_linux(bus_id)

    def stop_forwarding(self, bus_id: str) -> bool:
        """Stop forwarding a USB device."""
        if self._system == "Windows":
            return self._unforward_windows(bus_id)
        self._forwarding.discard(bus_id)
        return True

    def _forward_windows(self, bus_id: str) -> bool:
        """Forward USB device on Windows using usbipd-win."""
        try:
            # Bind the device for sharing
            result = subprocess.run(
                ["usbipd", "bind", "--busid", bus_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # May already be bound
                logger.debug("Bind result: %s", result.stderr)

            self._forwarding.add(bus_id)
            logger.info("USB device %s ready for forwarding (Windows)", bus_id)
            return True
        except FileNotFoundError:
            logger.error("usbipd-win not installed")
            return False
        except Exception as e:
            logger.error("Error forwarding USB device: %s", e)
            return False

    def _unforward_windows(self, bus_id: str) -> bool:
        """Stop forwarding on Windows."""
        try:
            subprocess.run(
                ["usbipd", "unbind", "--busid", bus_id],
                capture_output=True, timeout=10,
            )
            self._forwarding.discard(bus_id)
            return True
        except Exception:
            return False

    def _forward_linux(self, bus_id: str) -> bool:
        """Forward USB device on Linux using usbip."""
        try:
            # Bind to usbip-host driver
            result = subprocess.run(
                ["usbip", "bind", "-b", bus_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                self._forwarding.add(bus_id)
                logger.info("USB device %s bound for forwarding (Linux)", bus_id)
                return True
            logger.error("Failed to bind: %s", result.stderr)
            return False
        except Exception as e:
            logger.error("Error: %s", e)
            return False

    def get_device_list_message(self) -> dict:
        """Build a protocol message with the current device list."""
        devices = self.list_devices()
        return {
            "type": MsgType.USB_DEVICE_LIST,
            "devices": [d.to_dict() for d in devices],
        }

    def cleanup(self):
        """Stop all forwarding."""
        for bus_id in list(self._forwarding):
            self.stop_forwarding(bus_id)


def check_usbip_client_available() -> bool:
    """Check if USB/IP client tools are available."""
    system = platform.system()
    if system == "Windows":
        try:
            result = subprocess.run(["usbipd", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    else:
        try:
            result = subprocess.run(["usbip", "version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
