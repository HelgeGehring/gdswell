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


def test_kdb_polygon_hull_um_unit_square():
    """A 1 µm × 1 µm rectangle at the origin yields four corner points."""
    import klayout.db as kdb

    from gdswell.visualization import _kdb_polygon_hull_um

    dbu = 0.001
    # Build a 1 µm square polygon directly in dbu (1000 dbu = 1 µm).
    kpoly = kdb.Polygon(
        [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
    )

    hull = _kdb_polygon_hull_um(kpoly, dbu)

    assert len(hull) == 4
    # KLayout's each_point_hull walks the hull in its own internal order;
    # we assert the set of corners (order-independent) plus first==origin.
    assert hull[0] == (0.0, 0.0)
    assert set(hull) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}
