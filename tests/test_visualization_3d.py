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


def test_extrude_region_uniform_unit_square():
    """Extruding a unit square from z=0 to z=0.22 produces a PolyData with the
    expected bounding box (within dbu rounding tolerance)."""
    import klayout.db as kdb

    from gdswell.visualization import _extrude_region_uniform

    dbu = 0.001
    region = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )

    meshes = _extrude_region_uniform(region, z_lo=0.0, z_hi=0.22, dbu=dbu)
    assert len(meshes) == 1
    b = meshes[0].bounds
    assert abs(b.x_min - 0.0) < 1e-6
    assert abs(b.x_max - 1.0) < 1e-6
    assert abs(b.y_min - 0.0) < 1e-6
    assert abs(b.y_max - 1.0) < 1e-6
    assert abs(b.z_min - 0.0) < 1e-6
    assert abs(b.z_max - 0.22) < 1e-6
    # Capped extrusion has triangulated top + bottom + sidewall quads.
    assert meshes[0].n_cells > 0


def test_extrude_region_uniform_two_disjoint_polygons():
    """Two disjoint polygons in one region produce two meshes."""
    import klayout.db as kdb

    from gdswell.visualization import _extrude_region_uniform

    dbu = 0.001
    region = kdb.Region()
    region.insert(
        kdb.Polygon([kdb.Point(0, 0), kdb.Point(500, 0), kdb.Point(500, 500), kdb.Point(0, 500)])
    )
    region.insert(
        kdb.Polygon(
            [kdb.Point(2000, 0), kdb.Point(2500, 0), kdb.Point(2500, 500), kdb.Point(2000, 500)]
        )
    )

    meshes = _extrude_region_uniform(region, z_lo=0.0, z_hi=0.1, dbu=dbu)
    assert len(meshes) == 2


def test_loft_region_pair_shrinking_square_has_smaller_top():
    """Lofting a 1 µm square at z=0 to a 0.9 µm square at z=0.22 produces a
    closed mesh whose top cap area is smaller than the bottom."""
    import klayout.db as kdb

    from gdswell.visualization import _loft_region_pair

    dbu = 0.001
    bottom = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    # Top: same shape, shrunk by 50 nm per side → 0.9 µm square centered.
    top = kdb.Region(
        kdb.Polygon(
            [
                kdb.Point(50, 50),
                kdb.Point(950, 50),
                kdb.Point(950, 950),
                kdb.Point(50, 950),
            ]
        )
    )

    meshes = _loft_region_pair(bottom, top, z_lo=0.0, z_hi=0.22, dbu=dbu, entry_name="Si_rib")
    assert len(meshes) == 1
    b = meshes[0].bounds
    assert abs(b.z_min - 0.0) < 1e-6
    assert abs(b.z_max - 0.22) < 1e-6
    # The bottom cap (z=0) should span the full 1 µm; the top cap the
    # shrunken 0.9 µm. The mesh as a whole spans the union in xy.
    assert abs(b.x_min - 0.0) < 1e-6
    assert abs(b.x_max - 1.0) < 1e-6


def test_loft_region_pair_polygon_count_mismatch_raises():
    """One polygon at z_lo vs. two at z_hi raises NotImplementedError naming the entry."""
    import klayout.db as kdb
    import pytest

    from gdswell.visualization import _loft_region_pair

    dbu = 0.001
    bottom = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    top = kdb.Region()
    top.insert(
        kdb.Polygon([kdb.Point(0, 0), kdb.Point(400, 0), kdb.Point(400, 400), kdb.Point(0, 400)])
    )
    top.insert(
        kdb.Polygon(
            [kdb.Point(600, 0), kdb.Point(1000, 0), kdb.Point(1000, 400), kdb.Point(600, 400)]
        )
    )

    with pytest.raises(NotImplementedError, match="MorphEntry"):
        _loft_region_pair(bottom, top, z_lo=0.0, z_hi=0.22, dbu=dbu, entry_name="MorphEntry")


def test_loft_region_pair_point_count_mismatch_raises():
    """A quad at z_lo and a triangle at z_hi (same polygon count, different
    point counts) raises NotImplementedError."""
    import klayout.db as kdb
    import pytest

    from gdswell.visualization import _loft_region_pair

    dbu = 0.001
    bottom = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    top = kdb.Region(kdb.Polygon([kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(500, 1000)]))

    with pytest.raises(NotImplementedError):
        _loft_region_pair(bottom, top, z_lo=0.0, z_hi=0.22, dbu=dbu, entry_name="MorphEntry")
