"""Tests for DeviceBackend protocol conformance."""

from __future__ import annotations

from mobiletestai.device.base import DeviceBackend, DeviceError
from mobiletestai.device.bridge import BridgeDevice, BridgeError
from mobiletestai.device.xcodebuildmcp import XcodeBuildMCPDevice, XcodeBuildMCPError


class TestProtocolConformance:
    def test_bridge_device_is_device_backend(self):
        assert isinstance(BridgeDevice("test-udid"), DeviceBackend)

    def test_xcodebuildmcp_device_is_device_backend(self):
        assert isinstance(XcodeBuildMCPDevice("test-udid"), DeviceBackend)


class TestErrorHierarchy:
    def test_bridge_error_is_device_error(self):
        assert issubclass(BridgeError, DeviceError)

    def test_xcodebuildmcp_error_is_device_error(self):
        assert issubclass(XcodeBuildMCPError, DeviceError)

    def test_device_error_catch_catches_bridge_error(self):
        try:
            raise BridgeError("test")
        except DeviceError:
            pass  # Should be caught

    def test_device_error_catch_catches_xcodebuildmcp_error(self):
        try:
            raise XcodeBuildMCPError("test")
        except DeviceError:
            pass  # Should be caught
