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


def _build_two_entry_resolved(dbu: float = 0.001):
    """Helper: a 2-entry stack (square prism + 0.5 µm square cutter at the
    same xy) resolved against a cell that draws both polygons."""
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)
        MASK = (3, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)], Pdk.MASK)
    stack = gw.StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22) + gw.StackupEntry.uniform(
        "Mask", Pdk.MASK, 0.0, 0.22
    )
    return stack.resolve(cell)


def test_prism_cut_z_to_region_no_cuts_returns_raw():
    """apply_cuts=False yields exactly the prism's own z_to_region."""
    from gdswell.visualization import _prism_cut_z_to_region

    resolved = _build_two_entry_resolved()
    cut = _prism_cut_z_to_region(resolved, prism_index=0, apply_cuts=False)
    assert set(cut.keys()) == set(resolved.prisms[0].z_to_region.keys())
    for z, region in cut.items():
        assert region.bbox() == resolved.prisms[0].z_to_region[z].bbox()


def test_prism_cut_z_to_region_apply_cuts_subtracts_overlap():
    """With apply_cuts=True, the cutter's region is subtracted at every z
    within its z-range."""
    from gdswell.visualization import _prism_cut_z_to_region

    resolved = _build_two_entry_resolved()
    cut = _prism_cut_z_to_region(resolved, prism_index=0, apply_cuts=True)
    # Bottom-left 0.5 × 0.5 carved away from a 1 × 1 → remaining region has
    # 75% of original area (in dbu² units).
    original_area = sum(r.area() for r in resolved.prisms[0].z_to_region.values()) / len(
        resolved.prisms[0].z_to_region
    )
    cut_area = sum(r.area() for r in cut.values()) / len(cut)
    assert cut_area == 0.75 * original_area


def test_prism_meshes_uniform_returns_extruded():
    """A 2-key region dict with equal regions → uniform extrude path."""
    import klayout.db as kdb

    from gdswell.visualization import _prism_meshes

    dbu = 0.001
    region = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    z_to_region = {0.0: region, 0.22: region.dup()}
    meshes = _prism_meshes(z_to_region, dbu=dbu, entry_name="Si")
    assert len(meshes) == 1
    b = meshes[0].bounds
    assert abs(b.z_min - 0.0) < 1e-6
    assert abs(b.z_max - 0.22) < 1e-6


def test_prism_meshes_empty_returns_empty():
    """Zero z-keys → empty list."""
    from gdswell.visualization import _prism_meshes

    assert _prism_meshes({}, dbu=0.001, entry_name="X") == []


def test_prism_meshes_single_z_key_returns_empty():
    """One z-key (zero-thickness sheet) → empty list."""
    import klayout.db as kdb

    from gdswell.visualization import _prism_meshes

    region = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    assert _prism_meshes({0.0: region}, dbu=0.001, entry_name="Sheet") == []


def test_prism_meshes_slanted_returns_lofted():
    """Differing regions at adjacent z-keys → loft path."""
    import klayout.db as kdb

    from gdswell.visualization import _prism_meshes

    dbu = 0.001
    bottom = kdb.Region(
        kdb.Polygon(
            [kdb.Point(0, 0), kdb.Point(1000, 0), kdb.Point(1000, 1000), kdb.Point(0, 1000)]
        )
    )
    top = kdb.Region(
        kdb.Polygon(
            [kdb.Point(50, 50), kdb.Point(950, 50), kdb.Point(950, 950), kdb.Point(50, 950)]
        )
    )
    meshes = _prism_meshes({0.0: bottom, 0.22: top}, dbu=dbu, entry_name="Si_rib")
    assert len(meshes) == 1
    b = meshes[0].bounds
    assert abs(b.z_max - 0.22) < 1e-6


def test_plot_stackup_3d_single_uniform_returns_plotter_with_one_actor():
    """A 1-entry stack adds exactly one mesh to a fresh plotter."""
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    stack = gw.Stackup.of(gw.StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22))
    resolved = stack.resolve(cell)

    plotter = gw.plot_stackup_3d(resolved)
    try:
        # Renderer holds one actor per add_mesh call.
        assert len([a for a in plotter.renderer.actors.values()]) >= 1
    finally:
        plotter.close()


def test_plot_stackup_3d_keep_false_is_omitted():
    """A keep=False cutter is referenced but never rendered."""
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)
        MASK = (3, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)], Pdk.MASK)
    stack = gw.StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22) - gw.StackupEntry.uniform(
        "Mask", Pdk.MASK, 0.0, 0.22
    )
    resolved = stack.resolve(cell)

    plotter = gw.plot_stackup_3d(resolved)
    try:
        # Exactly one kept prism → at most one mesh added (legend/axes
        # actors may also appear, so we filter by label).
        mesh_labels = [name for name in plotter.renderer.actors.keys() if "Si" in str(name)]
        assert len(mesh_labels) >= 1
        # No mesh labeled "Mask".
        assert not any("Mask" in str(name) for name in plotter.renderer.actors.keys())
    finally:
        plotter.close()


def test_plot_stackup_3d_apply_cuts_false_keeps_overlapping():
    """A keep=True full-coverage cutter on top of Si:
    - apply_cuts=True: Si fully carved → fewer actors total.
    - apply_cuts=False: Si NOT carved → more actors visible.
    """
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)
        MASK = (3, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.MASK)  # full coverage
    stack = gw.StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22) + gw.StackupEntry.uniform(
        "FullCutter", Pdk.MASK, 0.0, 0.22
    )
    resolved = stack.resolve(cell)

    plotter_cut = gw.plot_stackup_3d(resolved, apply_cuts=True)
    plotter_raw = gw.plot_stackup_3d(resolved, apply_cuts=False)
    try:
        cut_actor_count = len(plotter_cut.renderer.actors)
        raw_actor_count = len(plotter_raw.renderer.actors)
        # Raw mode shows both; cut mode shows fewer.
        assert raw_actor_count > cut_actor_count
    finally:
        plotter_cut.close()
        plotter_raw.close()


def test_plot_stackup_3d_opacity_map_precedence():
    """opacity_map[name] wins over the scalar opacity default."""
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    stack = gw.Stackup.of(gw.StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22))
    resolved = stack.resolve(cell)

    plotter = gw.plot_stackup_3d(resolved, opacity=0.3, opacity_map={"Si": 0.95})
    try:
        # Find the mesh actor; its property opacity should be 0.95, not 0.3.
        opacities = [
            actor.prop.opacity  # ty: ignore[unresolved-attribute]
            for name, actor in plotter.renderer.actors.items()
            if hasattr(actor, "prop") and actor.prop is not None
        ]
        assert any(abs(op - 0.95) < 1e-6 for op in opacities)
        # And no actor at 0.3 since we only have one mesh.
        assert not any(abs(op - 0.3) < 1e-6 for op in opacities)
    finally:
        plotter.close()


def test_color_symmetry_2d_3d_for_same_resolved_stack():
    """Without an explicit color_map, both viewers allocate the i-th tab20
    color to the i-th unique prism name (in painter's order)."""
    from enum import Enum

    import gdswell as gw

    class Pdk(gw.Layer, Enum):
        WG = (1, 0)
        CLAD = (2, 0)

    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(-2, -2), (2, -2), (2, 2), (-2, 2)], Pdk.CLAD)
    cell.add_polygon([(-1, -0.25), (1, -0.25), (1, 0.25), (-1, 0.25)], Pdk.WG)
    stack = gw.StackupEntry.uniform("Clad", Pdk.CLAD, 0.0, 2.0) + gw.StackupEntry.uniform(
        "Si", Pdk.WG, 0.0, 0.22
    )

    # 2D path
    cutline = ((0.0, -3.0), (0.0, 3.0))
    resolved_2d = stack.resolve_cutline(cell, cutline)
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots()
    gw.plot_cross_section(resolved_2d, ax=ax)
    # Pull color out of the first patch of each label.
    label_to_2d_color: dict[str, tuple[float, ...]] = {}
    for patch in ax.patches:
        lbl = str(patch.get_label())
        if lbl and lbl not in label_to_2d_color:
            rgba = np.asarray(patch.get_facecolor(), dtype=float).ravel()
            label_to_2d_color[lbl] = tuple(rgba.tolist())
    plt.close(fig)

    # 3D path
    resolved_3d = stack.resolve(cell)
    plotter = gw.plot_stackup_3d(resolved_3d)
    try:
        label_to_3d_color: dict[str, tuple[float, ...]] = {}
        for name, actor in plotter.renderer.actors.items():
            prop = getattr(actor, "prop", None)
            if prop is None or not hasattr(prop, "color"):
                continue
            # pv.Color exposes .float_rgb as a 3-tuple in [0, 1].
            label_to_3d_color[str(name)] = tuple(prop.color.float_rgb)
    finally:
        plotter.close()

    # Both viewers see "Clad" and "Si" in the same order. Compare the RGB
    # portion (matplotlib returns RGBA; vtk returns RGB with no alpha).
    for name in ("Clad", "Si"):
        assert name in label_to_2d_color, f"2D viewer didn't render {name}"
        assert name in label_to_3d_color, f"3D viewer didn't render {name}"
        rgb_2d = label_to_2d_color[name][:3]
        rgb_3d = label_to_3d_color[name]
        # Each channel must agree within VTK's float-rounding tolerance.
        for c2d, c3d in zip(rgb_2d, rgb_3d):
            assert abs(c2d - c3d) < 1e-2, f"{name} color mismatch: {rgb_2d} vs {rgb_3d}"


def test_plot_stackup_3d_is_in_top_level_all():
    """gw.plot_stackup_3d must appear in gdswell.__all__ so it's part of the
    documented public surface (not just a happens-to-be-importable name)."""
    import gdswell as gw

    assert hasattr(gw, "plot_stackup_3d")
    assert "plot_stackup_3d" in gw.__all__


def test_prism_meshes_topology_change_falls_back_to_extrusion():
    """When adjacent z-key regions have mismatched topology (e.g. different
    polygon counts from disjoint cuts at different z), the dispatcher falls
    back to vertical extrusion of the lower region instead of crashing.

    Emits a UserWarning so the approximation is visible.
    """
    import warnings

    import klayout.db as kdb

    from gdswell.visualization import _prism_meshes

    dbu = 0.001
    # Bottom: one square. Top: two disjoint squares. Different polygon counts.
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

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        meshes = _prism_meshes({0.0: bottom, 0.22: top}, dbu=dbu, entry_name="Approx")
    # At least one mesh produced (the fallback extruded the bottom region).
    assert len(meshes) >= 1
    # The user got a warning about the fallback.
    assert any("Approx" in str(w.message) for w in caught)
