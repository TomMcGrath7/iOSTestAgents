"""Tests for XcodeBuildMCPDevice backend."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from iostestagents.device.xcodebuildmcp import XcodeBuildMCPDevice, XcodeBuildMCPError


class TestXcodeBuildMCPDevice:
    def test_tap_runs_correct_command(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(device, "_run") as mock_run:
            device.tap(100, 200)
            mock_run.assert_called_once_with(
                ["ui-automation", "tap", "-x", "100", "-y", "200", "--post-delay", "0.5", "--simulator-id", "test-udid"]
            )

    def test_swipe_runs_correct_command(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(device, "_run") as mock_run:
            device.swipe(0, 100, 200, 300, 0.5)
            mock_run.assert_called_once_with([
                "ui-automation", "swipe",
                "--x1", "0", "--y1", "100",
                "--x2", "200", "--y2", "300",
                "--duration", "0.5",
                "--simulator-id", "test-udid",
            ])

    def test_type_text_runs_correct_command(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(device, "_run") as mock_run:
            device.type_text("hello")
            mock_run.assert_called_once_with(
                ["ui-automation", "type-text", "--text", "hello", "--simulator-id", "test-udid"]
            )

    def test_press_button_runs_correct_command(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(device, "_run") as mock_run:
            device.press_button("HOME")
            mock_run.assert_called_once_with(
                ["ui-automation", "button", "--button-type", "home", "--simulator-id", "test-udid"]
            )

    def test_describe_ui_runs_correct_command(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(device, "_run", return_value="AXButton 'Test'") as mock_run:
            result = device.describe_ui()
            mock_run.assert_called_once_with(
                ["ui-automation", "snapshot-ui", "--simulator-id", "test-udid"]
            )
            assert result == "AXButton 'Test'"

    def test_run_raises_on_missing_binary(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(XcodeBuildMCPError, match="not found"):
                device._run(["ui-automation", "tap"])

    def test_run_raises_on_nonzero_exit(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
            with pytest.raises(XcodeBuildMCPError, match="error msg"):
                device._run(["ui-automation", "tap"])

    def test_run_raises_on_timeout(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            with pytest.raises(XcodeBuildMCPError, match="timed out"):
                device._run(["ui-automation", "tap"])

    def test_start_raises_if_not_available(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(XcodeBuildMCPDevice, "is_available", return_value=False):
            with pytest.raises(XcodeBuildMCPError, match="not found"):
                device.start()

    def test_start_succeeds_if_available(self):
        device = XcodeBuildMCPDevice("test-udid")
        with patch.object(XcodeBuildMCPDevice, "is_available", return_value=True):
            device.start()  # Should not raise

    def test_stop_is_noop(self):
        device = XcodeBuildMCPDevice("test-udid")
        device.stop()  # Should not raise

    def test_is_available_true(self):
        with patch("shutil.which", return_value="/usr/local/bin/xcodebuildmcp"):
            assert XcodeBuildMCPDevice.is_available() is True

    def test_is_available_false(self):
        with patch("shutil.which", return_value=None):
            assert XcodeBuildMCPDevice.is_available() is False

    def test_is_running_delegates_to_is_available(self):
        with patch.object(XcodeBuildMCPDevice, "is_available", return_value=True):
            assert XcodeBuildMCPDevice.is_running() is True
        with patch.object(XcodeBuildMCPDevice, "is_available", return_value=False):
            assert XcodeBuildMCPDevice.is_running() is False
