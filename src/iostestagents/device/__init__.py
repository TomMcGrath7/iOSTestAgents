"""Device backends for iOS simulator interaction."""

from iostestagents.device.base import DeviceBackend, DeviceError
from iostestagents.device.bridge import BridgeDevice, BridgeError
from iostestagents.device.xcodebuildmcp import XcodeBuildMCPDevice, XcodeBuildMCPError

__all__ = [
    "DeviceBackend",
    "DeviceError",
    "BridgeDevice",
    "BridgeError",
    "XcodeBuildMCPDevice",
    "XcodeBuildMCPError",
]
