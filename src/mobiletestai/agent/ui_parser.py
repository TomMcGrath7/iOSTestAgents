"""Parse accessibility tree text into structured elements with pre-calculated centers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class UIElement:
    """A parsed UI element with pre-calculated center coordinates."""

    index: int
    element_type: str
    label: str
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    traits: str = ""

    @property
    def tappable(self) -> bool:
        """Elements likely to respond to taps."""
        return self.element_type in {
            "Button", "Cell", "Link", "TextField", "SecureTextField",
            "Switch", "Toggle", "Slider", "SearchField", "StaticText",
            "Icon", "Image", "Tab", "SegmentedControl", "PopUpButton",
            "MenuButton", "Key",
        }


# Pattern: TypeName 'label' or id='label' {{x, y}, {w, h}} traits
_ELEMENT_RE = re.compile(
    r"^\s*(\w+)\s+"                         # element type
    r"(?:(?:id=)?'([^']*)')?\s*"            # optional label (with or without id= prefix)
    r"\{\{(\d+),\s*(\d+)\},\s*\{(\d+),\s*(\d+)\}\}"  # frame {{x,y},{w,h}}
    r"(.*)?$"                               # optional trailing traits
)


def parse_ui_elements(ui_state: str) -> list[UIElement]:
    """Parse raw accessibility tree into a list of UIElements.

    Supports two formats:
    - TestBridge text format: Button 'label' {{x, y}, {w, h}}
    - XcodeBuildMCP JSON format: nested objects with type, AXLabel, frame, children
    """
    # Detect XcodeBuildMCP JSON format
    if _is_json_ui(ui_state):
        return _parse_json_ui(ui_state)
    return _parse_text_ui(ui_state)


def _is_json_ui(ui_state: str) -> bool:
    """Check if the UI state is XcodeBuildMCP JSON format."""
    # XcodeBuildMCP wraps JSON in markdown code block with a preamble
    stripped = ui_state.strip()
    return "```json" in stripped or ('"type"' in stripped and '"frame"' in stripped)


def _parse_text_ui(ui_state: str) -> list[UIElement]:
    """Parse TestBridge text format accessibility tree."""
    elements = []
    idx = 1
    for line in ui_state.splitlines():
        m = _ELEMENT_RE.match(line.strip())
        if not m:
            continue
        el_type = m.group(1)
        label = m.group(2) or ""
        x, y, w, h = int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
        traits = (m.group(7) or "").strip()

        if w == 0 or h == 0:
            continue

        elem = UIElement(
            index=idx,
            element_type=el_type,
            label=label,
            x=x, y=y, width=w, height=h,
            center_x=x + w // 2,
            center_y=y + h // 2,
            traits=traits,
        )
        elements.append(elem)
        idx += 1
    return elements


def _parse_json_ui(ui_state: str) -> list[UIElement]:
    """Parse XcodeBuildMCP JSON format accessibility tree."""
    # Extract JSON from markdown code block if present
    text = ui_state.strip()
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:start + end - start].strip()
    elif "```" in text:
        start = text.index("```") + len("```")
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:start + end - start].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    elements: list[UIElement] = []
    idx_counter = [1]  # mutable counter for nested recursion

    def _walk(node: dict) -> None:
        el_type = node.get("type", "")
        label = node.get("AXLabel") or node.get("title") or ""
        frame = node.get("frame", {})
        x = frame.get("x", 0)
        y = frame.get("y", 0)
        w = frame.get("width", 0)
        h = frame.get("height", 0)

        # Convert to int (XcodeBuildMCP uses floats)
        x, y, w, h = int(x), int(y), int(w), int(h)

        if w > 0 and h > 0 and el_type:
            elem = UIElement(
                index=idx_counter[0],
                element_type=el_type,
                label=label,
                x=x, y=y, width=w, height=h,
                center_x=x + w // 2,
                center_y=y + h // 2,
            )
            elements.append(elem)
            idx_counter[0] += 1

        for child in node.get("children", []):
            _walk(child)

    nodes = data if isinstance(data, list) else [data]
    for node in nodes:
        _walk(node)

    return elements


def _is_child_element(el: UIElement, elements: list[UIElement]) -> bool:
    """Check if an element is visually contained within a Button/Cell parent.

    If a Button's frame fully contains this element, it's a child — tapping
    the parent Button is sufficient, so we skip the child to save list slots.
    """
    if el.element_type in ("Button", "Cell", "Switch", "Toggle"):
        return False  # Top-level interactive elements are never children
    for other in elements:
        if other is el:
            continue
        if other.element_type not in ("Button", "Cell"):
            continue
        # Check if el is fully contained within other's frame
        if (other.x <= el.x and other.y <= el.y
                and other.x + other.width >= el.x + el.width
                and other.y + other.height >= el.y + el.height):
            return True
    return False


def build_element_list(
    elements: list[UIElement],
    tappable_only: bool = True,
    max_elements: int = 30,
    screen_height: int = 874,
) -> tuple[str, set[int]]:
    """Format elements as a numbered list for the LLM prompt.

    Only includes labeled, tappable elements to keep the list focused.
    Filters out child elements (Images/StaticTexts inside Buttons) to avoid
    wasting slots. Prioritizes action buttons.
    Caps at max_elements to avoid overwhelming small models.

    Returns (formatted_text, set_of_shown_element_indices).
    """
    # Separate elements into priority tiers
    action_buttons: list[UIElement] = []  # Continue, Next, Submit, etc.
    regular: list[UIElement] = []

    action_keywords = {"continue", "next", "submit", "done", "save", "confirm",
                       "sign up", "sign in", "log in", "create", "send", "ok",
                       "accept", "agree", "skip", "get started", "proceed",
                       "report", "bug", "feedback", "feature", "request",
                       "help", "support", "contact"}

    for el in elements:
        if tappable_only and not el.tappable:
            continue
        if not el.label:
            continue
        # Skip child elements that are inside a parent Button/Cell
        if _is_child_element(el, elements):
            continue
        label_lower = el.label.lower()
        if any(kw in label_lower for kw in action_keywords):
            action_buttons.append(el)
        else:
            regular.append(el)

    def _format(el: UIElement) -> str:
        traits_part = f" {el.traits}" if el.traits else ""
        return f"[{el.index}] {el.element_type} '{el.label}' center=({el.center_x}, {el.center_y}){traits_part}"

    lines = []
    shown_indices: set[int] = set()

    # Always include action buttons first (they're most important)
    for el in action_buttons:
        lines.append(_format(el))
        shown_indices.add(el.index)

    # Fill remaining slots with regular elements
    remaining = max_elements - len(lines)
    for el in regular[:remaining]:
        lines.append(_format(el))
        shown_indices.add(el.index)

    total_tappable = len(action_buttons) + len(regular)
    if total_tappable > max_elements:
        lines.append(f"... ({total_tappable - len(lines)} more elements, use swipe_up to scroll)")

    return "\n".join(lines), shown_indices


def detect_screen_title(elements: list[UIElement]) -> str:
    """Extract the current screen title from NavigationBar, Heading, or StaticText near top."""
    # Look for NavigationBar with a label (TestBridge format)
    for el in elements:
        if el.element_type == "NavigationBar" and el.label:
            return el.label
    # Look for Heading near top (XcodeBuildMCP format)
    for el in elements:
        if el.element_type == "Heading" and el.label and el.y < 120:
            return el.label
    # Fallback: look for prominent StaticText near the top of the screen (y < 120)
    for el in elements:
        if el.element_type == "StaticText" and el.label and el.y < 120:
            return el.label
    return ""


def check_goal_reached(goal: str, screen_title: str, elements: list[UIElement]) -> bool:
    """Check if the current screen state indicates the goal has been reached.

    Uses simple heuristics — only for simple single-destination goals like
    "Navigate to X > Y > Z". Multi-step goals (containing "and", commas, or
    action verbs beyond navigation) are left to the LLM to judge completion.
    """
    if not screen_title:
        return False

    goal_lower = goal.lower()
    screen_lower = screen_title.lower()

    # Skip auto-detection for multi-step or complex goals — let the LLM decide
    multi_step_indicators = [" and ", ", ", "then ", "create", "send", "submit", "fill", "enter", "sign", "log in", "register"]
    if any(indicator in goal_lower for indicator in multi_step_indicators):
        return False

    # Extract destination from "Navigate to X > Y" or "Go to X > Y" patterns
    for prefix in ("navigate to ", "go to ", "open "):
        if goal_lower.startswith(prefix):
            destination = goal_lower[len(prefix):]
            # For "General > About", the final destination is "About"
            if ">" in destination:
                final = destination.split(">")[-1].strip()
            else:
                final = destination.strip()
            if final and final in screen_lower:
                return True

    return False


def resolve_element(
    elements: list[UIElement],
    *,
    index: int | None = None,
    target: str | None = None,
) -> tuple[int, int] | None:
    """Resolve an element reference to (center_x, center_y).

    Supports:
    - index: element number from the numbered list (e.g., 1, 2, 3)
    - target: label text to fuzzy-match against element labels
    """
    if index is not None:
        for el in elements:
            if el.index == index:
                return el.center_x, el.center_y
        return None

    if target is not None:
        target_lower = target.lower().strip("'\"")
        # Exact label match first
        for el in elements:
            if el.label and el.label.lower() == target_lower:
                return el.center_x, el.center_y
        # Target contained in label or label contained in target (min 3 chars)
        for el in elements:
            if el.label and len(el.label) >= 3:
                if target_lower in el.label.lower() or el.label.lower() in target_lower:
                    return el.center_x, el.center_y
        # Match element type + label pattern like "Button 'General'"
        for el in elements:
            if el.label:
                full = f"{el.element_type} '{el.label}'".lower()
                if target_lower == full or target_lower in full:
                    return el.center_x, el.center_y

    return None
