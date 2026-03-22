"""Tests for UI accessibility tree parser."""

from __future__ import annotations

from iostestagents.agent.ui_parser import (
    UIElement,
    build_element_list,
    check_goal_reached,
    detect_screen_title,
    parse_ui_elements,
    resolve_element,
)


SAMPLE_UI = """\
Application 'Settings' {{0, 0}, {393, 852}}
  Window  {{0, 0}, {393, 852}}
    NavigationBar 'Settings' {{0, 44}, {393, 52}}
      Button 'Back' {{0, 44}, {80, 44}}
      StaticText 'Settings' {{130, 55}, {133, 30}}
    Table  {{0, 96}, {393, 756}}
      Cell 'General' {{0, 500}, {393, 44}}
        StaticText 'General' {{20, 510}, {100, 24}}
      Cell 'About' {{0, 544}, {393, 44}}
        StaticText 'About' {{20, 554}, {60, 24}}
      SearchField id='search' {{16, 100}, {361, 36}}
    Other  {{0, 0}, {0, 0}}
"""


class TestParseUIElements:
    def test_parses_elements(self):
        elements = parse_ui_elements(SAMPLE_UI)
        assert len(elements) > 0
        types = {e.element_type for e in elements}
        assert "Button" in types
        assert "Cell" in types

    def test_calculates_centers(self):
        elements = parse_ui_elements(SAMPLE_UI)
        # Cell 'General' {{0, 500}, {393, 44}} → center = (196, 522)
        general = [e for e in elements if e.label == "General" and e.element_type == "Cell"]
        assert len(general) == 1
        assert general[0].center_x == 196
        assert general[0].center_y == 522

    def test_skips_zero_size_elements(self):
        elements = parse_ui_elements(SAMPLE_UI)
        for e in elements:
            assert e.width > 0 and e.height > 0

    def test_assigns_sequential_indices(self):
        elements = parse_ui_elements(SAMPLE_UI)
        indices = [e.index for e in elements]
        assert indices == list(range(1, len(elements) + 1))

    def test_parses_id_labels(self):
        elements = parse_ui_elements(SAMPLE_UI)
        search = [e for e in elements if e.label == "search"]
        assert len(search) == 1
        assert search[0].element_type == "SearchField"

    def test_empty_input(self):
        assert parse_ui_elements("") == []

    def test_non_matching_lines(self):
        assert parse_ui_elements("random text\nmore text") == []


class TestBuildElementList:
    def test_formats_numbered_list(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result, shown = build_element_list(elements)
        assert "[" in result
        assert "center=(" in result
        assert len(shown) > 0

    def test_tappable_only_filters(self):
        elements = parse_ui_elements(SAMPLE_UI)
        tappable, _ = build_element_list(elements, tappable_only=True)
        all_elements, _ = build_element_list(elements, tappable_only=False)
        # Tappable list should be shorter or equal
        assert len(tappable) <= len(all_elements)

    def test_includes_button_and_cell(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result, _ = build_element_list(elements)
        assert "Button" in result
        assert "Cell" in result


class TestResolveElement:
    def test_resolve_by_index(self):
        elements = parse_ui_elements(SAMPLE_UI)
        # Find the Cell 'General' element index
        general = [e for e in elements if e.label == "General" and e.element_type == "Cell"]
        assert general
        result = resolve_element(elements, index=general[0].index)
        assert result == (196, 522)

    def test_resolve_by_target_exact(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result = resolve_element(elements, target="General")
        assert result is not None
        assert result == (196, 522)

    def test_resolve_by_target_substring(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result = resolve_element(elements, target="About")
        assert result is not None

    def test_resolve_by_target_with_type(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result = resolve_element(elements, target="Button 'Back'")
        assert result is not None

    def test_resolve_missing_index(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result = resolve_element(elements, index=999)
        assert result is None

    def test_resolve_missing_target(self):
        elements = parse_ui_elements(SAMPLE_UI)
        result = resolve_element(elements, target="NonexistentElement")
        assert result is None

    def test_resolve_no_elements(self):
        result = resolve_element([], index=1)
        assert result is None


class TestDetectScreenTitle:
    def test_detects_navigation_bar(self):
        elements = parse_ui_elements(SAMPLE_UI)
        title = detect_screen_title(elements)
        assert title == "Settings"

    def test_empty_elements(self):
        assert detect_screen_title([]) == ""


class TestCheckGoalReached:
    def test_navigate_to_about(self):
        assert check_goal_reached("Navigate to General > About", "About", [])

    def test_navigate_to_general(self):
        assert check_goal_reached("Navigate to General", "General", [])

    def test_navigate_not_reached(self):
        assert not check_goal_reached("Navigate to General > About", "General", [])

    def test_open_settings(self):
        assert check_goal_reached("Open Settings", "Settings", [])

    def test_go_to(self):
        assert check_goal_reached("Go to About", "About", [])

    def test_no_screen_title(self):
        assert not check_goal_reached("Navigate to About", "", [])

    def test_case_insensitive(self):
        assert check_goal_reached("Navigate to general > about", "About", [])


class TestUIElementTappable:
    def test_button_is_tappable(self):
        el = UIElement(index=1, element_type="Button", label="OK", x=0, y=0, width=80, height=44, center_x=40, center_y=22)
        assert el.tappable

    def test_cell_is_tappable(self):
        el = UIElement(index=1, element_type="Cell", label="Item", x=0, y=0, width=393, height=44, center_x=196, center_y=22)
        assert el.tappable

    def test_window_not_tappable(self):
        el = UIElement(index=1, element_type="Window", label="", x=0, y=0, width=393, height=852, center_x=196, center_y=426)
        assert not el.tappable

    def test_navigationbar_not_tappable(self):
        el = UIElement(index=1, element_type="NavigationBar", label="Settings", x=0, y=44, width=393, height=52, center_x=196, center_y=70)
        assert not el.tappable
