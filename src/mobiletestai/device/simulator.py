"""SimulatorManager — wraps xcrun simctl for iOS simulator lifecycle management."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mobiletestai.util.logging import get_logger

logger = get_logger(__name__)

COMMAND_TIMEOUT = 30


class SimulatorError(Exception):
    """Raised when a simctl command fails."""


@dataclass
class DeviceInfo:
    name: str
    udid: str
    state: str
    runtime: str


class SimulatorManager:
    """Manages iOS simulators via xcrun simctl."""

    def _run(self, args: list[str], timeout: int = COMMAND_TIMEOUT) -> str:
        cmd = ["xcrun", "simctl", *args]
        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise SimulatorError(f"Command timed out: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            raise SimulatorError(
                f"simctl failed (rc={result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def list_devices(self) -> list[DeviceInfo]:
        raw = self._run(["list", "devices", "available", "-j"])
        data = json.loads(raw)
        devices: list[DeviceInfo] = []
        for runtime, device_list in data.get("devices", {}).items():
            for d in device_list:
                if d.get("isAvailable", False):
                    devices.append(
                        DeviceInfo(
                            name=d["name"],
                            udid=d["udid"],
                            state=d["state"],
                            runtime=runtime,
                        )
                    )
        return devices

    def find_device(self, name: str) -> DeviceInfo:
        devices = self.list_devices()
        matches = [d for d in devices if d.name == name]
        if not matches:
            available = sorted({d.name for d in devices})
            raise SimulatorError(
                f"No device named '{name}'. Available: {', '.join(available)}"
            )
        # Prefer latest runtime (runtime strings sort lexicographically)
        matches.sort(key=lambda d: d.runtime, reverse=True)
        return matches[0]

    def boot(self, udid: str) -> None:
        logger.info(f"Booting simulator {udid}")
        try:
            self._run(["boot", udid])
        except SimulatorError as exc:
            if "current state: Booted" in str(exc):
                logger.debug("Simulator already booted")
            else:
                raise

    def shutdown(self, udid: str) -> None:
        logger.info(f"Shutting down simulator {udid}")
        try:
            self._run(["shutdown", udid])
        except SimulatorError as exc:
            if "current state: Shutdown" in str(exc):
                logger.debug("Simulator already shut down")
            else:
                raise

    def install_app(self, udid: str, app_path: str) -> None:
        logger.info(f"Installing {app_path} on {udid}")
        self._run(["install", udid, app_path])

    def launch_app(self, udid: str, bundle_id: str) -> None:
        logger.info(f"Launching {bundle_id} on {udid}")
        self._run(["launch", udid, bundle_id])

    def terminate_app(self, udid: str, bundle_id: str) -> None:
        logger.info(f"Terminating {bundle_id} on {udid}")
        try:
            self._run(["terminate", udid, bundle_id])
        except SimulatorError:
            logger.debug("App may not be running, ignoring terminate error")

    def uninstall_app(self, udid: str, bundle_id: str) -> None:
        logger.info(f"Uninstalling {bundle_id} from {udid}")
        try:
            self._run(["uninstall", udid, bundle_id])
        except SimulatorError:
            logger.debug("App may not be installed, ignoring uninstall error")

    def reset_app(
        self, udid: str, bundle_id: str, app_path: str | None = None
    ) -> None:
        """Terminate → uninstall → (optionally reinstall) → launch. Ensures clean state."""
        logger.info(f"Resetting app {bundle_id} on {udid}")
        self.terminate_app(udid, bundle_id)
        self.uninstall_app(udid, bundle_id)
        if app_path:
            self.install_app(udid, app_path)
        self.launch_app(udid, bundle_id)

    def screenshot(self, udid: str, path: str | Path) -> Path:
        path = Path(path)
        self._run(["io", udid, "screenshot", str(path)])
        logger.debug(f"Screenshot saved to {path}")
        return path

    def start_recording(self, udid: str, path: str | Path) -> subprocess.Popen:
        path = Path(path)
        logger.info(f"Starting recording to {path}")
        cmd = ["xcrun", "simctl", "io", udid, "recordVideo", str(path)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc

    def stop_recording(self, proc: subprocess.Popen) -> None:
        logger.info("Stopping recording")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
