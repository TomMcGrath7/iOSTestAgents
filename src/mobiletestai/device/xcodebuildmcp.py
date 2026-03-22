"""XcodeBuildMCP device backend — wraps the xcodebuildmcp CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from mobiletestai.device.base import DeviceError
from mobiletestai.util.logging import get_logger

logger = get_logger(__name__)


class XcodeBuildMCPError(DeviceError):
    """Raised when an XcodeBuildMCP command fails."""


class XcodeBuildMCPDevice:
    """UI interaction layer using the xcodebuildmcp CLI."""

    def __init__(self, udid: str, bundle_id: str | None = None) -> None:
        self.udid = udid
        self.bundle_id = bundle_id

    def _run(self, args: list[str], timeout: int = 30) -> str:
        """Run an xcodebuildmcp CLI command and return stdout."""
        cmd = ["xcodebuildmcp"] + args
        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise XcodeBuildMCPError(
                "xcodebuildmcp not found. Install with: npm install -g xcodebuildmcp@latest"
            )
        except subprocess.TimeoutExpired:
            raise XcodeBuildMCPError(f"xcodebuildmcp command timed out after {timeout}s: {' '.join(args)}")

        if result.returncode != 0:
            raise XcodeBuildMCPError(
                f"xcodebuildmcp failed (rc={result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout

    def describe_ui(self) -> str:
        """Get the view hierarchy with element coordinates."""
        return self._run(["ui-automation", "snapshot-ui", "--simulator-id", self.udid])

    def tap(self, x: int, y: int) -> None:
        logger.debug(f"Tap ({x}, {y})")
        self._run(["ui-automation", "tap", "-x", str(x), "-y", str(y), "--post-delay", "0.5", "--simulator-id", self.udid])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> None:
        logger.debug(f"Swipe ({x1},{y1}) -> ({x2},{y2})")
        self._run([
            "ui-automation", "swipe",
            "--x1", str(x1), "--y1", str(y1),
            "--x2", str(x2), "--y2", str(y2),
            "--duration", str(duration),
            "--simulator-id", self.udid,
        ])

    def type_text(self, text: str) -> None:
        logger.debug(f"Type text: {text!r}")
        # Small delay to ensure keyboard is visible after a prior tap
        import time
        time.sleep(0.5)
        self._run(["ui-automation", "type-text", "--text", text, "--simulator-id", self.udid])

    def press_button(self, button: str) -> None:
        logger.debug(f"Press button: {button}")
        self._run(["ui-automation", "button", "--button-type", button.lower(), "--simulator-id", self.udid])

    def start(self, timeout: int = 30, output_dir: str | Path = "output") -> None:
        """Verify xcodebuildmcp is available. CLI is stateless, no server to start."""
        if not self.is_available():
            raise XcodeBuildMCPError(
                "xcodebuildmcp not found. Install with: npm install -g xcodebuildmcp@latest"
            )
        logger.info("XcodeBuildMCP backend ready (stateless CLI)")

    def stop(self) -> None:
        """No-op — CLI is stateless."""
        pass

    @staticmethod
    def is_available() -> bool:
        """Check if xcodebuildmcp CLI is on PATH."""
        return shutil.which("xcodebuildmcp") is not None

    @staticmethod
    def is_running() -> bool:
        """CLI is stateless; return True if available."""
        return XcodeBuildMCPDevice.is_available()
