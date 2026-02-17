"""Device backends for iOS simulator interaction."""

from mobiletestai.device.base import DeviceBackend, DeviceError
from mobiletestai.device.bridge import BridgeDevice, BridgeError
from mobiletestai.device.xcodebuildmcp import XcodeBuildMCPDevice, XcodeBuildMCPError

__all__ = [
    "DeviceBackend",
    "DeviceError",
    "BridgeDevice",
    "BridgeError",
    "XcodeBuildMCPDevice",
    "XcodeBuildMCPError",
]
