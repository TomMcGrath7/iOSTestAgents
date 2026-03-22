"""Tests for device layer (SimulatorManager + IDBDevice + BridgeDevice)."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from iostestagents.device.simulator import SimulatorManager, SimulatorError, DeviceInfo
from iostestagents.device.idb import IDBDevice, IDBError
from iostestagents.device.bridge import BridgeDevice, BridgeError


class TestSimulatorManager:
    def test_list_devices(self, simctl_devices_json):
        sim = SimulatorManager()
        with patch.object(sim, "_run", return_value=simctl_devices_json):
            devices = sim.list_devices()
        assert len(devices) == 3
        assert devices[0].name == "iPhone 16"

    def test_find_device_prefers_latest_runtime(self, simctl_devices_json):
        sim = SimulatorManager()
        with patch.object(sim, "_run", return_value=simctl_devices_json):
            device = sim.find_device("iPhone 16")
        assert device.udid == "AAAA-BBBB-CCCC-DDDD"
        assert "18-2" in device.runtime

    def test_find_device_not_found(self, simctl_devices_json):
        sim = SimulatorManager()
        with patch.object(sim, "_run", return_value=simctl_devices_json):
            with pytest.raises(SimulatorError, match="No device named"):
                sim.find_device("iPhone 99")

    def test_boot_already_booted(self):
        sim = SimulatorManager()
        with patch.object(
            sim, "_run", side_effect=SimulatorError("current state: Booted")
        ):
            sim.boot("test-udid")  # Should not raise

    def test_boot_failure(self):
        sim = SimulatorManager()
        with patch.object(
            sim, "_run", side_effect=SimulatorError("some other error")
        ):
            with pytest.raises(SimulatorError):
                sim.boot("test-udid")

    def test_run_command_construction(self):
        sim = SimulatorManager()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
            sim._run(["list", "devices", "-j"])
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["xcrun", "simctl", "list", "devices", "-j"]

    def test_run_timeout(self):
        sim = SimulatorManager()
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            with pytest.raises(SimulatorError, match="timed out"):
                sim._run(["list"])

    def test_run_nonzero_exit(self):
        sim = SimulatorManager()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="bad")
            with pytest.raises(SimulatorError, match="simctl failed"):
                sim._run(["bad-command"])

    def test_reset_app_with_app_path(self):
        sim = SimulatorManager()
        with patch.object(sim, "terminate_app") as term, \
             patch.object(sim, "uninstall_app") as uninst, \
             patch.object(sim, "install_app") as inst, \
             patch.object(sim, "launch_app") as launch:
            sim.reset_app("udid", "com.test.app", "/path/to/app")
            term.assert_called_once_with("udid", "com.test.app")
            uninst.assert_called_once_with("udid", "com.test.app")
            inst.assert_called_once_with("udid", "/path/to/app")
            launch.assert_called_once_with("udid", "com.test.app")

    def test_reset_app_without_app_path(self):
        sim = SimulatorManager()
        with patch.object(sim, "terminate_app"), \
             patch.object(sim, "uninstall_app"), \
             patch.object(sim, "install_app") as inst, \
             patch.object(sim, "launch_app"):
            sim.reset_app("udid", "com.test.app")
            inst.assert_not_called()

    def test_screenshot(self, tmp_path):
        sim = SimulatorManager()
        with patch.object(sim, "_run"):
            path = sim.screenshot("udid", tmp_path / "shot.png")
            assert path == tmp_path / "shot.png"

    def test_get_screen_size_iphone16(self):
        sim = SimulatorManager()
        enumerate_output = (
            "Display 0:\n"
            "  Size 1170 x 2532\n"
            "  Scale 3.00\n"
        )
        with patch.object(sim, "_run", return_value=enumerate_output):
            w, h = sim.get_screen_size("udid")
        assert w == 390
        assert h == 844

    def test_get_screen_size_ipad(self):
        sim = SimulatorManager()
        enumerate_output = (
            "Display 0:\n"
            "  Size 1640 x 2360\n"
            "  Scale 2.00\n"
        )
        with patch.object(sim, "_run", return_value=enumerate_output):
            w, h = sim.get_screen_size("udid")
        assert w == 820
        assert h == 1180

    def test_get_screen_size_no_scale(self):
        """When scale factor is missing, treat as 1x."""
        sim = SimulatorManager()
        enumerate_output = "Display 0:\n  Size 393 x 852\n"
        with patch.object(sim, "_run", return_value=enumerate_output):
            w, h = sim.get_screen_size("udid")
        assert w == 393
        assert h == 852

    def test_get_screen_size_parse_failure(self):
        """Unparseable output should fall back to defaults."""
        sim = SimulatorManager()
        with patch.object(sim, "_run", return_value="no display info here"):
            w, h = sim.get_screen_size("udid")
        assert w == 393
        assert h == 852

    def test_get_screen_size_simctl_error(self):
        """SimulatorError should fall back to defaults."""
        sim = SimulatorManager()
        with patch.object(sim, "_run", side_effect=SimulatorError("failed")):
            w, h = sim.get_screen_size("udid")
        assert w == 393
        assert h == 852


class TestIDBDevice:
    def test_tap_command(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run") as mock_run:
            idb.tap(100, 200)
            mock_run.assert_called_once_with(["ui", "tap", "100", "200"])

    def test_swipe_command(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run") as mock_run:
            idb.swipe(0, 0, 100, 100, 0.3)
            mock_run.assert_called_once_with(
                ["ui", "swipe", "0", "0", "100", "100", "0.3"]
            )

    def test_type_text_command(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run") as mock_run:
            idb.type_text("hello world")
            mock_run.assert_called_once_with(["ui", "text", "hello world"])

    def test_press_button_command(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run") as mock_run:
            idb.press_button("HOME")
            mock_run.assert_called_once_with(["ui", "button", "HOME"])

    def test_describe_ui_with_idb(self):
        idb = IDBDevice("test-udid")
        tree = "AXApplication 'Settings' ..."
        with patch.object(idb, "_run", return_value=tree):
            result = idb.describe_ui()
            assert result == tree

    def test_describe_ui_fallback_on_empty(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run", return_value=""), \
             patch.object(idb, "_run_simctl_fallback", return_value="fallback tree"):
            result = idb.describe_ui()
            assert result == "fallback tree"

    def test_describe_ui_fallback_on_error(self):
        idb = IDBDevice("test-udid")
        with patch.object(idb, "_run", side_effect=IDBError("fail")), \
             patch.object(idb, "_run_simctl_fallback", return_value="fallback"):
            result = idb.describe_ui()
            assert result == "fallback"

    def test_run_command_includes_udid(self):
        idb = IDBDevice("my-udid")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            idb._run(["ui", "tap", "10", "20"])
            args = mock_run.call_args[0][0]
            assert args == ["idb", "ui", "tap", "10", "20", "--udid", "my-udid"]

    def test_run_idb_not_found(self):
        idb = IDBDevice("udid")
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(IDBError, match="idb not found"):
                idb._run(["ui", "tap", "0", "0"])

    def test_is_installed_true(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert IDBDevice.is_installed() is True

    def test_is_installed_false(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert IDBDevice.is_installed() is False


class TestBridgeDevice:
    def test_tap_sends_http_post(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request") as mock_req:
            bridge.tap(100, 200)
            mock_req.assert_called_once_with("POST", "/tap", {"x": 100, "y": 200})

    def test_swipe_sends_http_post(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request") as mock_req:
            bridge.swipe(0, 100, 200, 300, 0.5)
            mock_req.assert_called_once_with("POST", "/swipe", {
                "fromX": 0, "fromY": 100,
                "toX": 200, "toY": 300,
                "duration": 0.5,
            })

    def test_type_text_sends_http_post(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request") as mock_req:
            bridge.type_text("hello")
            mock_req.assert_called_once_with("POST", "/type", {"text": "hello"})

    def test_press_button_sends_http_post(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request") as mock_req:
            bridge.press_button("HOME")
            mock_req.assert_called_once_with("POST", "/pressButton", {"button": "HOME"})

    def test_describe_ui_sends_http_get(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request", return_value={"ui": "AXButton 'Test'"}) as mock_req:
            result = bridge.describe_ui()
            mock_req.assert_called_once_with("GET", "/ui", query=None)
            assert result == "AXButton 'Test'"

    def test_describe_ui_with_bundle_id(self):
        bridge = BridgeDevice("test-udid")
        with patch.object(bridge, "_request", return_value={"ui": "tree"}) as mock_req:
            result = bridge.describe_ui(bundle_id="com.test.app")
            mock_req.assert_called_once_with("GET", "/ui", query="bundleId=com.test.app")
            assert result == "tree"

    def test_request_raises_bridge_error_on_http_error(self):
        bridge = BridgeDevice("test-udid")
        error = urllib.error.HTTPError(
            "http://localhost:8615/tap", 400, "Bad Request", {},
            MagicMock(read=lambda: b'{"error": "Missing x/y"}')
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(BridgeError, match="Missing x/y"):
                bridge._request("POST", "/tap", {"x": 100})

    def test_request_raises_bridge_error_on_connection_failure(self):
        bridge = BridgeDevice("test-udid")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            with pytest.raises(BridgeError, match="not reachable"):
                bridge._request("GET", "/health")

    @patch("iostestagents.device.bridge.time.sleep")
    def test_start_polls_health(self, mock_sleep, tmp_path):
        bridge = BridgeDevice("test-udid")
        with patch("iostestagents.device.bridge.TESTBRIDGE_PROJECT", tmp_path / "TestBridge.xcodeproj"), \
             patch("subprocess.Popen") as mock_popen, \
             patch.object(bridge, "is_running", return_value=False), \
             patch.object(bridge, "_request") as mock_req:
            # Create the fake project path
            (tmp_path / "TestBridge.xcodeproj").mkdir()
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            mock_req.side_effect = [
                BridgeError("not ready"),
                {"status": "ok"},
            ]
            bridge.start(output_dir=tmp_path)
            assert mock_req.call_count == 2
            mock_popen.assert_called_once()

    def test_stop_terminates_process(self):
        bridge = BridgeDevice("test-udid")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        bridge._process = mock_proc
        bridge.stop()
        mock_proc.terminate.assert_called_once()

    def test_is_available_true(self, tmp_path):
        with patch("iostestagents.device.bridge.TESTBRIDGE_PROJECT", tmp_path / "TestBridge.xcodeproj"):
            (tmp_path / "TestBridge.xcodeproj").mkdir()
            assert BridgeDevice.is_available() is True

    def test_is_available_false(self, tmp_path):
        with patch("iostestagents.device.bridge.TESTBRIDGE_PROJECT", tmp_path / "nonexistent.xcodeproj"):
            assert BridgeDevice.is_available() is False

    def test_is_running_true(self):
        bridge = BridgeDevice("test-udid")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"status": "ok"}'
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            assert bridge.is_running() is True

    def test_is_running_false(self):
        bridge = BridgeDevice("test-udid")
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            assert bridge.is_running() is False

    def test_default_port(self):
        bridge = BridgeDevice("test-udid")
        assert bridge.port == 8615
        assert bridge.base_url == "http://localhost:8615"

    def test_custom_port(self):
        bridge = BridgeDevice("test-udid", port=8616)
        assert bridge.port == 8616
        assert bridge.base_url == "http://localhost:8616"

    def test_two_instances_different_ports(self):
        bridge1 = BridgeDevice("udid-1", port=8615)
        bridge2 = BridgeDevice("udid-2", port=8616)
        assert bridge1.base_url != bridge2.base_url
        assert bridge1.base_url == "http://localhost:8615"
        assert bridge2.base_url == "http://localhost:8616"

    @patch("iostestagents.device.bridge.time.sleep")
    def test_start_writes_port_file(self, mock_sleep, tmp_path):
        bridge = BridgeDevice("test-udid-1234", port=9000)
        port_file = Path("/tmp/testbridge_test-udid-1234.port")
        try:
            with patch("iostestagents.device.bridge.TESTBRIDGE_PROJECT", tmp_path / "TestBridge.xcodeproj"), \
                 patch("subprocess.Popen") as mock_popen, \
                 patch.object(bridge, "is_running", return_value=False), \
                 patch.object(bridge, "_request", return_value={"status": "ok"}):
                (tmp_path / "TestBridge.xcodeproj").mkdir()
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc
                bridge.start(output_dir=tmp_path)
                assert port_file.exists()
                assert port_file.read_text() == "9000"
        finally:
            port_file.unlink(missing_ok=True)
