"""Core observe → reason → act agent loop."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from pydantic import ValidationError

from mobiletestai.agent.models import (
    ActionType,
    AgentAction,
    RunResult,
    StepRecord,
    TokenUsage,
)
from mobiletestai.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from mobiletestai.agent.ui_parser import (
    build_element_list,
    check_goal_reached,
    detect_screen_title,
    parse_ui_elements,
    resolve_element,
)
from mobiletestai.device.base import DeviceBackend, DeviceError
from mobiletestai.device.bridge import BridgeDevice
from mobiletestai.device.simulator import SimulatorError, SimulatorManager
from mobiletestai.llm.registry import get_provider
from mobiletestai.util.logging import get_logger

logger = get_logger(__name__)

# Swipe offset as a fraction of screen dimension (±24% from center)
_SWIPE_VERTICAL_FRAC = 0.24
_SWIPE_HORIZONTAL_FRAC = 0.19


def _encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _parse_action(raw: str, ui_elements: list | None = None, shown_indices: set[int] | None = None) -> AgentAction:
    """Parse LLM response into AgentAction, normalizing common format variations.

    If ui_elements is provided, resolves "element" numbers and "target" names
    to x/y coordinates automatically.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json.loads(text)

    # Normalize common LLM format variations:
    # "coordinates": [x, y] or "coordinates": {"x": n, "y": n}
    coords = data.pop("coordinates", None)
    if coords is not None and data.get("x") is None:
        if isinstance(coords, list) and len(coords) == 2:
            data["x"], data["y"] = int(coords[0]), int(coords[1])
        elif isinstance(coords, dict):
            data["x"] = int(coords.get("x", 0))
            data["y"] = int(coords.get("y", 0))

    # "reason" instead of "reasoning"
    if "reason" in data and "reasoning" not in data:
        data["reasoning"] = data.pop("reason")

    # Resolve "element" number to x/y coordinates
    element_ref = data.pop("element", None)
    if element_ref is not None and data.get("x") is None and ui_elements:
        try:
            idx = int(element_ref)
            # Only resolve elements the LLM was actually shown
            if shown_indices and idx not in shown_indices:
                logger.warning(f"LLM referenced element [{idx}] which was not in the shown list — ignoring")
            else:
                result = resolve_element(ui_elements, index=idx)
                if result:
                    data["x"], data["y"] = result
                    logger.info(f"Resolved element [{idx}] to ({result[0]}, {result[1]})")
        except (ValueError, TypeError):
            pass

    # Resolve "target" name to x/y coordinates
    target = data.pop("target", None)
    if target is not None and data.get("x") is None and ui_elements:
        target_str = str(target) if not isinstance(target, str) else target
        result = resolve_element(ui_elements, target=target_str)
        if result:
            data["x"], data["y"] = result
            logger.info(f"Resolved target '{target_str}' to ({result[0]}, {result[1]})")

    # Normalize common action name variations
    action_aliases = {
        "click": "tap",
        "press": "tap",
        "scroll_down": "swipe_down",
        "scroll_up": "swipe_up",
        "scroll_left": "swipe_left",
        "scroll_right": "swipe_right",
        "swipe": "swipe_down",
        "scroll": "swipe_down",
        "back": "press_button",
    }
    action_val = data.get("action", "")
    if action_val in action_aliases:
        data["action"] = action_aliases[action_val]
        if action_val == "back":
            data["button"] = "HOME"

    # Drop unknown fields that would fail Pydantic validation
    known = {"action", "reasoning", "x", "y", "text", "button", "message"}
    data = {k: v for k, v in data.items() if k in known}

    return AgentAction(**data)


def _execute_action(
    action: AgentAction,
    backend: DeviceBackend,
    screen_width: int = 393,
    screen_height: int = 852,
) -> None:
    """Dispatch an action to the device backend."""
    cx, cy = screen_width // 2, screen_height // 2
    vert_offset = int(screen_height * _SWIPE_VERTICAL_FRAC)
    horiz_offset = int(screen_width * _SWIPE_HORIZONTAL_FRAC)

    match action.action:
        case ActionType.TAP:
            if action.x is None or action.y is None:
                raise DeviceError(f"tap action missing coordinates (x={action.x}, y={action.y})")
            backend.tap(action.x, action.y)
        case ActionType.SWIPE_UP:
            backend.swipe(cx, cy + vert_offset, cx, cy - vert_offset)
        case ActionType.SWIPE_DOWN:
            backend.swipe(cx, cy - vert_offset, cx, cy + vert_offset)
        case ActionType.SWIPE_LEFT:
            backend.swipe(cx + horiz_offset, cy, cx - horiz_offset, cy)
        case ActionType.SWIPE_RIGHT:
            backend.swipe(cx - horiz_offset, cy, cx + horiz_offset, cy)
        case ActionType.TYPE:
            backend.type_text(action.text or "")
        case ActionType.TAP_AND_TYPE:
            if action.x is None or action.y is None:
                raise DeviceError(f"tap_and_type action missing coordinates (x={action.x}, y={action.y})")
            backend.tap(action.x, action.y)
            time.sleep(1.0)  # wait for keyboard to appear
            backend.type_text(action.text or "")
        case ActionType.PRESS_BUTTON:
            backend.press_button(action.button or "HOME")
        case ActionType.WAIT:
            time.sleep(2.0)
        case ActionType.DONE | ActionType.FAIL:
            pass  # Terminal actions, no device interaction


def run_agent(
    goal: str,
    device_name: str,
    bundle_id: str,
    max_steps: int = 20,
    model: str | None = None,
    vision_model: str | None = None,
    output_dir: str | Path = "output",
    step_delay: float = 1.5,
    record: bool = False,
    reset: bool = True,
    app_path: str | None = None,
    provider: str | None = None,
    backend: DeviceBackend | None = None,
    vision: bool = True,
    device_udid: str | None = None,
) -> RunResult:
    """Run the agent loop: observe → reason → act until goal is met or max steps."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result = RunResult(goal=goal, device=device_name)
    sim = SimulatorManager()
    llm = get_provider(provider)
    if model is None:
        model = llm.default_model
    logger.info(f"Using LLM provider: {llm.name}, model: {model}")

    # Find and boot device
    if device_udid:
        from mobiletestai.device.simulator import DeviceInfo
        device = DeviceInfo(name=device_name, udid=device_udid, runtime="", state="")
    else:
        logger.info(f"Finding device: {device_name}")
        device = sim.find_device(device_name)
    result.device = f"{device.name} ({device.udid})"
    sim.boot(device.udid)

    # Detect actual screen dimensions for this device
    screen_width, screen_height = sim.get_screen_size(device.udid)
    logger.info(f"Screen dimensions: {screen_width}x{screen_height}")

    owns_backend = backend is None
    if owns_backend:
        backend = BridgeDevice(device.udid, bundle_id=bundle_id)
        backend.start(output_dir=output_path)

    # Reset app for clean state
    if reset:
        sim.reset_app(device.udid, bundle_id, app_path)
    else:
        try:
            sim.launch_app(device.udid, bundle_id)
        except SimulatorError:
            if app_path:
                logger.info("App not installed, installing from app_path before launch")
                sim.install_app(device.udid, app_path)
                sim.launch_app(device.udid, bundle_id)
            else:
                raise

    # Optional recording
    recording_proc = None
    if record:
        recording_path = output_path / f"{result.run_id}_recording.mp4"
        recording_proc = sim.start_recording(device.udid, recording_path)

    action_history: list[dict] = []
    prev_ui_state = ""
    identical_count = 0

    try:
        for step_num in range(1, max_steps + 1):
            step = StepRecord(step_number=step_num)
            logger.info(f"--- Step {step_num}/{max_steps} ---")

            # 1. Observe
            try:
                ui_state = backend.describe_ui()
            except (DeviceError, Exception) as exc:
                logger.warning(f"describe_ui failed: {exc} — app may have left foreground, relaunching")
                try:
                    sim.terminate_app(device.udid, bundle_id)
                except Exception:
                    pass
                time.sleep(1.0)
                sim.launch_app(device.udid, bundle_id)
                time.sleep(2.0)
                ui_state = backend.describe_ui()
            logger.info(f"UI state ({len(ui_state)} chars): {ui_state[:300]}..."
                        if len(ui_state) > 300 else f"UI state ({len(ui_state)} chars): {ui_state}")
            screenshot_path = output_path / f"{result.run_id}_step{step_num:03d}.png"
            try:
                sim.screenshot(device.udid, screenshot_path)
                step.screenshot_path = str(screenshot_path)
            except Exception as exc:
                logger.warning(f"Screenshot failed: {exc}")

            # 2. Stale UI detection
            if ui_state == prev_ui_state and ui_state:
                identical_count += 1
                if identical_count < 3:
                    logger.debug("UI unchanged, waiting 2s and re-observing")
                    time.sleep(2.0)
                    ui_state = backend.describe_ui()
                    try:
                        sim.screenshot(device.udid, screenshot_path)
                    except Exception:
                        pass
            else:
                identical_count = 0

            prev_ui_state = ui_state
            step.ui_state = ui_state
            ui_stuck = identical_count >= 3

            # 3. Parse UI elements and build numbered list
            ui_elements = parse_ui_elements(ui_state)
            element_list, shown_element_indices = build_element_list(ui_elements)
            screen_title = detect_screen_title(ui_elements)
            tappable_count = element_list.count(chr(10)) + 1 if element_list else 0
            logger.info(f"Parsed {len(ui_elements)} UI elements, {tappable_count} tappable, screen='{screen_title}'")

            # 3b. Auto-detect goal completion from screen state
            if check_goal_reached(goal, screen_title, ui_elements):
                logger.info(f"Goal auto-detected as reached: screen='{screen_title}' matches goal")
                step.action = AgentAction(
                    action=ActionType.DONE,
                    reasoning=f"Screen '{screen_title}' matches goal destination",
                    message=f"Navigated to {screen_title}",
                )
                result.steps.append(step)
                result.status = "success"
                result.message = step.action.message or "Goal achieved"
                break

            # 4. Detect repeated actions (agent looping)
            repeat_count = 0
            if len(action_history) >= 2:
                last = action_history[-1]
                for prev in reversed(action_history[:-1]):
                    if prev.get("action") == last.get("action") and prev.get("reasoning", "")[:30] == last.get("reasoning", "")[:30]:
                        repeat_count += 1
                    else:
                        break
            use_vision_fallback = repeat_count >= 2 and step.screenshot_path
            if use_vision_fallback:
                logger.info(f"Action repeated {repeat_count + 1}x — enabling vision fallback for this step")

            # 5. Reason — call LLM
            user_prompt = build_user_prompt(
                goal=goal,
                step=step_num,
                max_steps=max_steps,
                action_history=action_history,
                ui_state=ui_state,
                ui_stuck=ui_stuck or repeat_count >= 2,
                element_list=element_list,
                screen_title=screen_title,
            )

            messages_content: list[dict] = []
            # Send screenshot if: always-on vision, OR vision fallback when stuck
            if (vision or use_vision_fallback) and step.screenshot_path:
                image_data = _encode_image(screenshot_path)
                messages_content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    }
                )
                if use_vision_fallback:
                    messages_content.append(
                        {
                            "type": "text",
                            "text": "You are STUCK repeating the same action. "
                            "Look at the screenshot above carefully. "
                            "Find a DIFFERENT button or element to tap. "
                            "Look for Continue, Next, Skip, or Done buttons.\n\n",
                        }
                    )
            messages_content.append({"type": "text", "text": user_prompt})

            action = None
            # Use vision model when doing vision fallback, otherwise normal model
            step_model = vision_model if (use_vision_fallback and vision_model) else model
            for attempt in range(3):
                try:
                    llm_response = llm.chat(
                        model=step_model,
                        system=SYSTEM_PROMPT,
                        messages_content=messages_content,
                        max_tokens=1024,
                    )
                    step.token_usage = TokenUsage(
                        input_tokens=llm_response.input_tokens,
                        output_tokens=llm_response.output_tokens,
                    )
                    raw_text = llm_response.text
                    logger.info(f"LLM raw response: {raw_text[:500]}")
                    action = _parse_action(raw_text, ui_elements=ui_elements, shown_indices=shown_element_indices)
                    break
                except (json.JSONDecodeError, ValidationError, KeyError) as exc:
                    logger.warning(f"Parse attempt {attempt + 1} failed: {exc}")
                    if attempt < 2:
                        messages_content.append(
                            {
                                "type": "text",
                                "text": f"Your previous response was not valid JSON: {exc}. "
                                "Please respond with ONLY a valid JSON object.",
                            }
                        )
                    else:
                        step.success = False
                        step.error = f"Failed to parse LLM response after 3 attempts: {exc}"

            step.action = action
            result.steps.append(step)

            # Accumulate tokens
            result.total_tokens.input_tokens += step.token_usage.input_tokens
            result.total_tokens.output_tokens += step.token_usage.output_tokens

            if action is None:
                logger.error("Could not parse action, continuing to next step")
                action_history.append({"action": "parse_error", "error": step.error})
                time.sleep(step_delay)
                continue

            action_detail = f"Action: {action.action.value}"
            if action.x is not None and action.y is not None:
                action_detail += f" @ ({action.x}, {action.y})"
            if action.text:
                action_detail += f" text={action.text!r}"
            action_detail += f" — {action.reasoning}"
            logger.info(action_detail)
            action_history.append(
                {
                    "action": action.action.value,
                    "reasoning": action.reasoning,
                }
            )

            # 5. Check terminal actions
            if action.action == ActionType.DONE:
                result.status = "success"
                result.message = action.message or "Goal achieved"
                logger.info(f"DONE: {result.message}")
                break
            if action.action == ActionType.FAIL:
                result.status = "failure"
                result.message = action.message or "Goal failed"
                logger.info(f"FAIL: {result.message}")
                break

            # 6. Act
            try:
                _execute_action(action, backend, screen_width, screen_height)
            except DeviceError as exc:
                logger.warning(f"Action execution failed: {exc}")
                step.success = False
                step.error = str(exc)
                action_history[-1]["error"] = str(exc)

            time.sleep(step_delay)
        else:
            result.status = "max_steps_reached"
            result.message = f"Reached maximum of {max_steps} steps without completing goal"
            logger.warning(result.message)

    finally:
        if owns_backend:
            backend.stop()
        if recording_proc:
            sim.stop_recording(recording_proc)

    # Calculate estimated cost
    result.estimated_cost = (
        result.total_tokens.input_tokens * llm.cost_per_input_token
        + result.total_tokens.output_tokens * llm.cost_per_output_token
    )

    logger.info(
        f"Run complete: status={result.status}, steps={len(result.steps)}, "
        f"tokens={result.total_tokens.input_tokens}+{result.total_tokens.output_tokens}, "
        f"cost≈${result.estimated_cost:.4f}"
    )

    return result
