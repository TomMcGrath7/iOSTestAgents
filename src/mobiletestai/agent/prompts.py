"""System and user prompt templates for the agent."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You test iOS apps. You see the current screen and a list of UI elements. Pick the next action.
Reply with ONLY a JSON object.

Actions:
- Tap element by number: {"action": "tap", "element": 3, "reasoning": "why"}
- Swipe: {"action": "swipe_up", "reasoning": "why"} (also swipe_down, swipe_left, swipe_right)
- Tap a text field AND type into it: {"action": "tap_and_type", "element": 5, "text": "hello", "reasoning": "why"}
- Type into already-focused field: {"action": "type", "text": "hello", "reasoning": "why"}
- Done: {"action": "done", "message": "what was achieved", "reasoning": "why"}
- Fail: {"action": "fail", "message": "what went wrong", "reasoning": "why"}

Rules:
1. ONLY output JSON. No other text.
2. Read the Goal carefully. Tap the element that gets you closer to the Goal.
3. If the element you need is not in the list, use swipe_up to scroll down and reveal more.
4. If you are on the wrong screen, tap the Back button to go back.
5. IMPORTANT: To type into a text field, ALWAYS use "tap_and_type" with the element number of the TextField. This taps the field first to focus it, then types. Do NOT use "tap" then "type" as separate actions — the field will lose focus.
6. When the Goal specifies exact text to type (email, password, name), use that EXACT text — do not make up your own. For "Confirm Password" fields, type the SAME password again — it must match exactly.
7. IMPORTANT: Only use "done" when ALL parts of the Goal are complete, not just the first part.
   For multi-step goals like "do X, create Y, and send Z" — you must finish every step before using "done".
   For simple navigation goals like "Navigate to About", use "done" when you reach that screen.
"""


def build_user_prompt(
    goal: str,
    step: int,
    max_steps: int,
    action_history: list[dict],
    ui_state: str,
    ui_stuck: bool = False,
    element_list: str = "",
    screen_title: str = "",
) -> str:
    parts = [f"**Goal**: {goal}", f"**Step**: {step}/{max_steps}"]

    if screen_title:
        parts.append(f"**Current screen**: {screen_title}")

    if action_history:
        history_lines = []
        for i, entry in enumerate(action_history[-5:], 1):  # last 5 actions
            action = entry.get("action", "unknown")
            reasoning = entry.get("reasoning", "")
            error = entry.get("error")
            line = f"  {i}. {action}"
            if reasoning:
                line += f" — {reasoning}"
            if error:
                line += f" [ERROR: {error}]"
            history_lines.append(line)
        parts.append("**Recent actions**:\n" + "\n".join(history_lines))

    if ui_stuck:
        parts.append(
            "**WARNING**: The UI has NOT changed after your last actions. "
            "Try: (1) a different element, (2) swipe to scroll, "
            "(3) tap Back to go to previous screen, or (4) use 'fail' if unreachable."
        )

    if element_list:
        parts.append(f"**Tappable elements** (use element number to tap):\n{element_list}")

    parts.append("Decide the next action. Respond with JSON only.")

    return "\n\n".join(parts)
