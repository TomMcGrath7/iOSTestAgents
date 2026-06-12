"""IDBDevice — wraps idb CLI for UI interaction on iOS simulators."""

from __future__ import annotations

import subprocess

from iostestagents.util.logging import get_logger

logger = get_logger(__name__)

COMMAND_TIMEOUT = 15


class IDBError(Exception):
    """Raised when an idb command fails."""


class IDBDevice:
    """UI interaction layer using idb CLI."""

    def __init__(self, udid: str) -> None:
        self.udid = udid

    def _run(self, args: list[str], timeout: int = COMMAND_TIMEOUT) -> str:
        cmd = ["idb", *args, "--udid", self.udid]
        logger.debug(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise IDBError("idb not found. Install with: pip install fb-idb") from exc
        except subprocess.TimeoutExpired as exc:
            raise IDBError(f"idb command timed out: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            raise IDBError(f"idb failed (rc={result.returncode}): {result.stderr.strip()}")
        return result.stdout

    def _run_simctl_fallback(self, args: list[str]) -> str:
        cmd = ["xcrun", "simctl", *args]
        logger.debug(f"Running fallback: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
        return result.stdout

    def describe_ui(self) -> str:
        """Get the current UI accessibility tree.

        Tries idb first, falls back to xcrun simctl if output is empty/garbage.
        """
        try:
            output = self._run(["ui", "describe-all"])
            if output and len(output.strip()) > 10:
                return output.strip()
            logger.warning("idb describe-all returned empty/short output, using simctl fallback")
        except IDBError as exc:
            logger.warning(f"idb describe-all failed: {exc}, using simctl fallback")

        fallback = self._run_simctl_fallback(["ui", self.udid, "describe"])
        return fallback.strip() if fallback else ""

    def tap(self, x: int, y: int) -> None:
        logger.debug(f"Tap ({x}, {y})")
        self._run(["ui", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> None:
        logger.debug(f"Swipe ({x1},{y1}) → ({x2},{y2})")
        self._run(["ui", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def type_text(self, text: str) -> None:
        logger.debug(f"Type text: {text!r}")
        self._run(["ui", "text", text])

    def press_button(self, button: str) -> None:
        """Press a hardware button (HOME, LOCK, SIDE_BUTTON, SIRI, APPLE_PAY)."""
        logger.debug(f"Press button: {button}")
        self._run(["ui", "button", button])

    @staticmethod
    def is_installed() -> bool:
        """Check if idb CLI is available."""
        try:
            result = subprocess.run(["idb", "--help"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
