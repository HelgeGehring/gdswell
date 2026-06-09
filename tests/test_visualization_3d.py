# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # before any pyplot import anywhere downstream

import pyvista as pv

pv.OFF_SCREEN = True  # no windows in CI / headless dev


def test_palette_color_for_name_allocates_first_seen_order():
    """The shared palette helper assigns colors by first appearance.

    Same allocator must be used by plot_cross_section and plot_stackup_3d
    so the two viewers agree on colors when no color_map is provided.
    """
    from gdswell.visualization import _palette_color_for_name

    name_to_color: dict[str, tuple[float, ...]] = {}
    color_map: dict[str, object] = {}

    c_a1 = _palette_color_for_name("A", color_map, name_to_color)
    c_b = _palette_color_for_name("B", color_map, name_to_color)
    c_a2 = _palette_color_for_name("A", color_map, name_to_color)
    c_c = _palette_color_for_name("C", color_map, name_to_color)

    assert c_a1 == c_a2  # stable across calls
    assert c_a1 != c_b
    assert c_b != c_c
    assert name_to_color == {"A": c_a1, "B": c_b, "C": c_c}


def test_palette_color_for_name_color_map_wins():
    """When the name is in color_map, the helper returns that without touching cache."""
    from gdswell.visualization import _palette_color_for_name

    name_to_color: dict[str, tuple[float, ...]] = {}
    color_map = {"A": "red"}

    c = _palette_color_for_name("A", color_map, name_to_color)
    assert c == "red"
    assert name_to_color == {}  # cache untouched
