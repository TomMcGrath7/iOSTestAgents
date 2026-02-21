"""BridgeDevice — communicates with TestBridge XCUITest HTTP server for UI interaction."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

from mobiletestai.device.base import DeviceError
from mobiletestai.util.logging import get_logger

logger = get_logger(__name__)

# TODO: Multi-device support requires a configurable port per BridgeDevice instance.
# Currently hardcoded to 8615, so only one TestBridge can run per host.
# To support multi-device orchestration with TestBridge:
#   1. Add --port argument to HTTPServer.swift's NWListener setup
#   2. Accept port parameter in BridgeDevice.__init__
#   3. Pass unique ports from the Orchestrator (e.g. 8615, 8616, 8617, ...)
# Until then, use the XcodeBuildMCP backend (stateless per-UDID CLI) for multi-device scenarios.
BRIDGE_PORT = 8615
BRIDGE_URL = f"http://localhost:{BRIDGE_PORT}"
TESTBRIDGE_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "testbridge" / "TestBridge.xcodeproj"


class BridgeError(DeviceError):
    """Raised when a TestBridge command fails."""


class BridgeDevice:
    """UI interaction layer using TestBridge XCUITest HTTP server."""

    def __init__(self, udid: str, bundle_id: str | None = None) -> None:
        self.udid = udid
        self.bundle_id = bundle_id
        self._process: subprocess.Popen | None = None

    def _request(self, method: str, path: str, body: dict | None = None, query: str | None = None) -> dict | bytes:
        url = f"{BRIDGE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"} if body else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
                if "application/json" in content_type:
                    return json.loads(raw)
                return raw
        except urllib.error.HTTPError as exc:
            try:
                error_body = json.loads(exc.read())
                msg = error_body.get("error", str(exc))
            except Exception:
                msg = str(exc)
            raise BridgeError(f"TestBridge {method} {path} failed ({exc.code}): {msg}") from exc
        except urllib.error.URLError as exc:
            raise BridgeError(f"TestBridge not reachable: {exc.reason}") from exc

    def describe_ui(self, bundle_id: str | None = None) -> str:
        bid = bundle_id or self.bundle_id
        query = f"bundleId={bid}" if bid else None
        result = self._request("GET", "/ui", query=query)
        if isinstance(result, dict):
            return result.get("ui", "")
        return ""

    def tap(self, x: int, y: int) -> None:
        logger.debug(f"Tap ({x}, {y})")
        self._request("POST", "/tap", {"x": x, "y": y})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> None:
        logger.debug(f"Swipe ({x1},{y1}) -> ({x2},{y2})")
        self._request("POST", "/swipe", {
            "fromX": x1, "fromY": y1,
            "toX": x2, "toY": y2,
            "duration": duration,
        })

    def type_text(self, text: str) -> None:
        logger.debug(f"Type text: {text!r}")
        self._request("POST", "/type", {"text": text})

    def press_button(self, button: str) -> None:
        logger.debug(f"Press button: {button}")
        self._request("POST", "/pressButton", {"button": button})

    def start(self, timeout: int = 60, output_dir: str | Path = "output") -> None:
        """Start TestBridge by running xcodebuild test as a background process."""
        if self.is_running():
            logger.info("TestBridge already running")
            return

        project = str(TESTBRIDGE_PROJECT)
        if not Path(project).exists():
            raise BridgeError(f"TestBridge project not found at {project}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        log_file = output_path / "testbridge.log"

        cmd = [
            "xcodebuild", "test",
            "-project", project,
            "-scheme", "TestBridge",
            "-destination", f"platform=iOS Simulator,id={self.udid}",
            "-only-testing:TestBridgeUITests/TestBridgeUITests/testBridgeServer",
        ]
        logger.info(f"Starting TestBridge: {' '.join(cmd)}")

        with open(log_file, "w") as lf:
            self._process = subprocess.Popen(
                cmd, stdout=lf, stderr=subprocess.STDOUT
            )

        # Poll /health until ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._process.poll() is not None:
                raise BridgeError(
                    f"xcodebuild exited early (rc={self._process.returncode}). "
                    f"Check {log_file} for details."
                )
            try:
                result = self._request("GET", "/health")
                if isinstance(result, dict) and result.get("status") == "ok":
                    logger.info("TestBridge is ready")
                    return
            except BridgeError:
                pass
            time.sleep(1.0)

        raise BridgeError(f"TestBridge did not start within {timeout}s. Check {log_file}")

    def stop(self) -> None:
        """Stop the TestBridge xcodebuild process."""
        if self._process and self._process.poll() is None:
            logger.info("Stopping TestBridge")
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    @staticmethod
    def is_available() -> bool:
        """Check if TestBridge Xcode project exists."""
        return TESTBRIDGE_PROJECT.exists()

    @staticmethod
    def is_running() -> bool:
        """Check if TestBridge server is responding."""
        try:
            req = urllib.request.Request(f"{BRIDGE_URL}/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                return data.get("status") == "ok"
        except Exception:
            return False
