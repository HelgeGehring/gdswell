# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import dataclasses
from enum import Enum

import klayout.db as kdb
import pytest

import gdswell as gw
from gdswell.layer import (
    LayerBBox,
    LayerInside,
    LayerInteracting,
    LayerNotInteracting,
    LayerOutside,
    LayerOverlapping,
    LayerRounded,
    LayerSize,
    LayerTransformed,
)
from gdswell.stackup import (
    ResolvedPrism,
    ResolvedStackup,
    ResolvedStackup2D,
    Stackup,
    StackupEntry,
    StackupItem,
)


class PDK(gw.Layer, Enum):
    WG = (1, 0)
    CLAD = (2, 0)
    MASK = (3, 0)


def test_entry_construction_minimum():
    e = StackupEntry("Si", {0.0: PDK.WG, 0.22: PDK.WG.size(-0.05)})
    assert e.name == "Si"
    assert set(e.z_to_layer.keys()) == {0.0, 0.22}


def test_entry_single_key_allowed():
    # Zero-thickness sheet — useful as boundary tag / cut surface.
    e = StackupEntry("Sheet", {0.0: PDK.WG})
    assert len(e.z_to_layer) == 1


def test_entry_uniform_helper():
    e = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    assert e.name == "Si"
    assert e.z_to_layer == {0.0: PDK.WG, 0.22: PDK.WG}


def test_entry_equal_and_hashable():
    a = StackupEntry("Si", {0.0: PDK.WG, 0.22: PDK.WG.size(-0.05)})
    b = StackupEntry("Si", {0.22: PDK.WG.size(-0.05), 0.0: PDK.WG})  # dict order
    assert a == b
    assert hash(a) == hash(b)
    # Different name → not equal
    c = StackupEntry("SiN", {0.0: PDK.WG, 0.22: PDK.WG.size(-0.05)})
    assert a != c


def test_entry_hash_string_deterministic():
    a = StackupEntry("Si", {0.0: PDK.WG, 0.22: PDK.WG.size(-0.05)})
    b = StackupEntry("Si", {0.22: PDK.WG.size(-0.05), 0.0: PDK.WG})
    assert a._hash_string == b._hash_string
    assert "Si" in a._hash_string


def _e(name, *zs):
    return StackupEntry(name, {z: PDK.WG for z in zs})


def test_stackup_from_entry_plus_entry():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    s = a + b
    assert isinstance(s, Stackup)
    assert s.items == (StackupItem(a, True), StackupItem(b, True))


def test_stackup_from_entry_minus_entry():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    s = a - b
    assert s.items == (StackupItem(a, True), StackupItem(b, False))


def test_stackup_extends_left():
    a, b, c = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0), _e("C", 0.0, 1.0)
    s = (a + b) + c
    assert s.items == (
        StackupItem(a, True),
        StackupItem(b, True),
        StackupItem(c, True),
    )


def test_stackup_extends_right():
    a, b, c = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0), _e("C", 0.0, 1.0)
    s = a + (b + c)
    assert s.items == (
        StackupItem(a, True),
        StackupItem(b, True),
        StackupItem(c, True),
    )


def test_stackup_minus_stack_marks_all_keep_false():
    a, b, c = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0), _e("C", 0.0, 1.0)
    s = a - (b + c)
    assert s.items == (
        StackupItem(a, True),
        StackupItem(b, False),
        StackupItem(c, False),
    )


def test_stackup_painters_order_with_parentheses():
    # (A + B) - C + D vs A + (B - C) + D — different cut targets.
    a, b, c, d = (_e(n, 0.0, 1.0) for n in "ABCD")
    flat = (a + b) - c + d
    assert [(it.entry.name, it.keep) for it in flat.items] == [
        ("A", True),
        ("B", True),
        ("C", False),
        ("D", True),
    ]
    nested = a + (b - c) + d
    # Same flat tuple — left-to-right associativity makes this equivalent here.
    assert [(it.entry.name, it.keep) for it in nested.items] == [
        ("A", True),
        ("B", True),
        ("C", False),
        ("D", True),
    ]


def test_stackup_hash_order_sensitive():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    assert hash(a + b) != hash(b + a)


def test_stackup_hash_string_includes_keep_flag():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    assert (a - b)._hash_string != (a + b)._hash_string


def test_entry_size_wraps_every_layer():
    e = StackupEntry("Si", {0.0: PDK.WG, 1.0: PDK.WG.size(-0.05)})
    sized = e.size(0.1)
    assert isinstance(sized, StackupEntry)
    assert sized.name == "Si"
    for L in sized.z_to_layer.values():
        assert isinstance(L, LayerSize)
    # original is untouched
    assert all(not isinstance(L, LayerSize) or L.dx == -0.05 for L in e.z_to_layer.values())


def test_entry_size_dy_independent():
    e = StackupEntry.uniform("X", PDK.WG, 0.0, 1.0)
    sized = e.size(0.2, 0.3)
    for L in sized.z_to_layer.values():
        assert isinstance(L, LayerSize)
        assert L.dx == 0.2 and L.dy == 0.3


def test_entry_transformed_wraps_every_layer():
    e = StackupEntry.uniform("X", PDK.WG, 0.0, 1.0)
    t = kdb.DTrans(1.0, 2.0)
    out = e.transformed(t)
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerTransformed)


def test_entry_round_corners_wraps_every_layer():
    e = StackupEntry.uniform("X", PDK.WG, 0.0, 1.0)
    out = e.round_corners(0.1, 0.1, 16)
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerRounded)


def test_entry_bbox_wraps_every_layer():
    e = StackupEntry.uniform("X", PDK.WG, 0.0, 1.0)
    out = e.bbox()
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerBBox)


def test_entry_map_layers_general():
    e = StackupEntry("X", {0.0: PDK.WG, 1.0: PDK.CLAD})
    out = e.map_layers(lambda L: L + PDK.MASK)  # boolean union with MASK
    for L in out.z_to_layer.values():
        # The result is a LayerUnion of the original and PDK.MASK
        assert hasattr(L, "left") and hasattr(L, "right")


def test_stackup_size_applies_to_all_entries_including_cuts():
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", PDK.MASK, 0.0, 1.0)
    stack = (a + b - c).size(0.1)
    assert [(it.entry.name, it.keep) for it in stack.items] == [
        ("A", True),
        ("B", True),
        ("C", False),
    ]
    for it in stack.items:
        for L in it.entry.z_to_layer.values():
            assert isinstance(L, LayerSize)
            assert L.dx == 0.1


def test_stackup_map_layers_passthrough():
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    stack = a + b
    out = stack.map_layers(lambda L: L.size(0.5))
    for it in out.items:
        for L in it.entry.z_to_layer.values():
            assert isinstance(L, LayerSize)
            assert L.dx == 0.5


def test_entry_filters_wrap_every_layer():
    e = StackupEntry.uniform("X", PDK.WG, 0.0, 1.0)

    inter = e.interacting(PDK.MASK)
    for L in inter.z_to_layer.values():
        assert isinstance(L, LayerInteracting)

    not_inter = e.interacting(PDK.MASK, invert=True)
    for L in not_inter.z_to_layer.values():
        assert isinstance(L, LayerNotInteracting)

    ins = e.inside(PDK.MASK)
    for L in ins.z_to_layer.values():
        assert isinstance(L, LayerInside)

    outs = e.outside(PDK.MASK)
    for L in outs.z_to_layer.values():
        assert isinstance(L, LayerOutside)

    overlap = e.overlapping(PDK.MASK, min_count=2)
    for L in overlap.z_to_layer.values():
        assert isinstance(L, LayerOverlapping)
        assert L.min_count == 2


def test_stackup_filters_apply_to_all_entries():
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    out = (a + b).inside(PDK.MASK)
    for it in out.items:
        for L in it.entry.z_to_layer.values():
            assert isinstance(L, LayerInside)


def _cell_with_two_squares():
    """A cell with a 1x1 µm square on PDK.WG at origin, and another on PDK.CLAD shifted right."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], PDK.CLAD)
    return cell


def test_resolve_non_overlapping_entries():
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    bot = StackupEntry.uniform("Bot", PDK.CLAD, -1.0, -0.5)
    rs = (si + bot).resolve(cell)

    assert len(rs.prisms) == 2
    by_name = {p.name: p for p in rs.prisms}
    assert set(by_name) == {"Si", "Bot"}
    assert by_name["Si"].mesh_order == 0
    assert by_name["Bot"].mesh_order == 1

    # No resampling — each entry keeps its own z-keys.
    assert set(by_name["Si"].z_to_region.keys()) == {0.0, 0.22}
    assert set(by_name["Bot"].z_to_region.keys()) == {-1.0, -0.5}

    for p in rs.prisms:
        for r in p.z_to_region.values():
            assert r.area() > 0


def test_resolve_returns_frozen_dataclass():
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 1.0)
    other = StackupEntry.uniform("Other", PDK.CLAD, 2.0, 3.0)
    p = (si + other).resolve(cell).prisms[0]
    assert dataclasses.is_dataclass(p)
    # frozen → reassignment must raise
    try:
        p.name = "nope"  # type: ignore[assignment]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ResolvedPrism should be frozen")


def test_entry_resolve_via_stackup_singleton():
    """A single StackupEntry, lifted into a 1-item Stackup, resolves cleanly."""
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    prisms = Stackup.of(si).resolve(cell).prisms
    assert len(prisms) == 1
    assert prisms[0].name == "Si"
    assert set(prisms[0].z_to_region.keys()) == {0.0, 0.22}


def _cell_with_overlap():
    """1x1 square on WG at origin; bigger 2x2 square on CLAD covering it."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)], PDK.CLAD)
    return cell


def test_resolve_overlapping_entries_keep_raw_regions():
    """Resolve no longer performs 2D cuts. Two entries that overlap in xy
    both appear with their un-subtracted raw regions; the painter's
    'later-wins' semantics is now the 3D backend's responsibility."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    # Both entries present.
    assert set(by_name) == {"A", "B"}
    # A's raw region is the 1x1 WG square (1 µm² = 1_000_000 dbu²); not subtracted.
    assert by_name["A"].z_to_region[0.0].area() == 1_000_000
    # B's raw region is the 2x2 CLAD square (4 µm²).
    assert by_name["B"].z_to_region[0.0].area() == 4_000_000


def test_resolve_partial_overlap_keeps_raw_regions():
    """Resolve no longer carves earlier entries; both keep their raw regions."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    # A's raw region: 2x1 = 2 µm² (un-carved).
    assert by_name["A"].z_to_region[0.0].area() == 2_000_000
    # B unchanged.
    assert by_name["B"].z_to_region[0.0].area() == 1_000_000


def test_resolve_no_global_z_resample():
    """Each entry keeps its own z-keys; no resampling, no morph."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], PDK.WG)
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.3, 0.6)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}

    # A keeps {0.0, 1.0}; B keeps {0.3, 0.6}. No resampling.
    assert sorted(by_name["A"].z_to_region) == [0.0, 1.0]
    assert sorted(by_name["B"].z_to_region) == [0.3, 0.6]
    # A's region at its own z-keys is the un-carved 2x2.
    assert by_name["A"].z_to_region[0.0].area() == 4_000_000
    assert by_name["A"].z_to_region[1.0].area() == 4_000_000


def test_resolve_mismatched_topology_no_longer_raises():
    """Different polygon counts at adjacent z-keys used to raise during
    resample. With cuts moved to 3D, resolve no longer resamples, so the
    error is gone."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.CLAD)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], PDK.CLAD)

    a = StackupEntry("A", {0.0: PDK.WG, 1.0: PDK.CLAD})
    b = StackupEntry.uniform("B", PDK.MASK, 0.5, 0.7)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.MASK)

    # Should not raise.
    rs = (a + b).resolve(cell)
    assert len(rs.prisms) == 2


def test_resolve_keep_false_appears_with_keep_false_flag():
    """keep=False entries appear in prisms with keep=False so cut_by can
    reference them. The downstream backend skips emitting their volume."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a - b).resolve(cell)
    assert [p.name for p in rs.prisms] == ["A", "B"]
    assert [p.keep for p in rs.prisms] == [True, False]
    # A's raw region unchanged.
    assert rs.prisms[0].z_to_region[0.0].area() == 2_000_000


def test_resolve_preserves_empty_entry_slot():
    """An entry whose layer recipe yields no shapes still appears in prisms
    (with empty regions) so the 1:1 index invariant holds. Downstream skips
    emitting a volume."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    # CLAD has no shapes in this cell.

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)  # B's layer is empty
    rs = (a + b).resolve(cell)
    assert [p.name for p in rs.prisms] == ["A", "B"]
    # B's regions are empty at all its z-keys.
    for r in rs.prisms[1].z_to_region.values():
        assert r.is_empty()


def test_resolve_three_slots_with_duplicate_names_preserved():
    """A - B + A under the new resolver: all three slots appear with raw
    regions; duplicate name "A" is passed through. The 3D backend uses
    cut_by + mesh_order to compute final volumes."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    a2 = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a - b + a2).resolve(cell)

    assert [p.name for p in rs.prisms] == ["A", "B", "A"]
    assert [p.keep for p in rs.prisms] == [True, False, True]
    # All three regions are the raw materializations.
    assert rs.prisms[0].z_to_region[0.0].area() == 2_000_000  # A: full strip
    assert rs.prisms[1].z_to_region[0.0].area() == 1_000_000  # B: right half
    assert rs.prisms[2].z_to_region[0.0].area() == 2_000_000  # A2: full strip


def test_resolve_single_key_zero_thickness_sheet_preserved():
    """A single-z-key entry is a zero-thickness sheet; its region is preserved."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)

    sheet = StackupEntry("Sheet", {0.5: PDK.WG})
    [p] = Stackup.of(sheet).resolve(cell).prisms
    assert list(p.z_to_region.keys()) == [0.5]
    assert p.z_to_region[0.5].area() == 1_000_000


def test_top_level_exports():
    import gdswell as gw
    from gdswell.stackup import ResolvedPolygon2D, ResolvedStackup2D
    from gdswell.visualization import plot_cross_section

    assert gw.StackupEntry is StackupEntry
    assert gw.Stackup is Stackup
    assert gw.ResolvedPrism is ResolvedPrism
    assert gw.ResolvedStackup is ResolvedStackup
    assert gw.ResolvedPolygon2D is ResolvedPolygon2D
    assert gw.ResolvedStackup2D is ResolvedStackup2D
    assert gw.plot_cross_section is plot_cross_section


def test_resolved_prism_has_keep_default_true():
    """New `keep` field — defaults True for back-compat."""
    p = ResolvedPrism(name="X", z_to_region={0.0: kdb.Region()}, mesh_order=0)
    assert p.keep is True


def test_resolved_prism_has_cut_by_default_empty():
    """New `cut_by` field — defaults to empty tuple."""
    p = ResolvedPrism(name="X", z_to_region={0.0: kdb.Region()}, mesh_order=0)
    assert p.cut_by == ()


def test_resolved_prism_accepts_keep_and_cut_by_kwargs():
    p = ResolvedPrism(
        name="X",
        z_to_region={0.0: kdb.Region()},
        mesh_order=2,
        keep=False,
        cut_by=(3, 5),
    )
    assert p.keep is False
    assert p.cut_by == (3, 5)


def test_resolved_stackup_holds_prisms_tuple():
    p0 = ResolvedPrism(name="A", z_to_region={0.0: kdb.Region()}, mesh_order=0)
    p1 = ResolvedPrism(name="B", z_to_region={0.0: kdb.Region()}, mesh_order=1)
    rs = ResolvedStackup(prisms=(p0, p1))
    assert rs.prisms == (p0, p1)


def test_resolved_stackup_is_frozen():
    rs = ResolvedStackup(prisms=())
    try:
        rs.prisms = ()  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ResolvedStackup should be frozen")


def test_resolved_stackup_default_empty():
    rs = ResolvedStackup()
    assert rs.prisms == ()


def test_resolve_preserves_own_z_keys():
    """Each prism's z_to_region keys exactly match its entry's z_to_layer keys."""
    cell = _cell_with_two_squares()
    a = StackupEntry("A", {0.0: PDK.WG, 0.5: PDK.WG.size(-0.1), 1.0: PDK.WG.size(-0.2)})
    b = StackupEntry.uniform("B", PDK.CLAD, 0.7, 1.3)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert sorted(by_name["A"].z_to_region) == [0.0, 0.5, 1.0]
    assert sorted(by_name["B"].z_to_region) == [0.7, 1.3]


def test_resolve_index_invariant():
    """len(rs.prisms) == len(stack.items); each prism.mesh_order == its index."""
    cell = _cell_with_two_squares()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", PDK.MASK, 0.0, 1.0)
    stack = a + b - c
    rs = stack.resolve(cell)
    assert len(rs.prisms) == len(stack.items) == 3
    for i, p in enumerate(rs.prisms):
        assert p.mesh_order == i


def test_resolve_cut_by_disjoint_z_no_edge():
    """Two entries with overlapping xy but disjoint z get no cut_by edge."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 0.5)
    b = StackupEntry.uniform("B", PDK.CLAD, 1.0, 1.5)  # above A, disjoint
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert by_name["A"].cut_by == ()
    assert by_name["B"].cut_by == ()


def test_resolve_cut_by_disjoint_xy_bbox_no_edge():
    """Two entries with overlapping z but disjoint xy bboxes get no edge."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(10, 0), (11, 0), (11, 1), (10, 1)], PDK.CLAD)

    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert by_name["A"].cut_by == ()
    assert by_name["B"].cut_by == ()


def test_resolve_cut_by_overlapping_bbox_emits_edge():
    """Two entries whose 3D bboxes overlap → cut_by edge from earlier to later."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    # Index 0 = A; index 1 = B. cut_by is forward-only.
    assert rs.prisms[0].cut_by == (1,)
    assert rs.prisms[1].cut_by == ()


def test_resolve_cut_by_painter_order_forward_only():
    """cut_by indices are strictly greater than the prism's own index.
    Also confirms at least one prism has a non-empty cut_by so the assertion
    is not vacuously satisfied."""
    cell = _cell_with_overlap()
    cell.add_polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)], PDK.MASK)
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", PDK.MASK, 0.0, 1.0)
    rs = (a + b + c).resolve(cell)
    # Guard against vacuous pass: at least one prism must have a cut_by edge.
    assert any(p.cut_by for p in rs.prisms)
    for i, p in enumerate(rs.prisms):
        for j in p.cut_by:
            assert j > i


def test_resolve_cut_by_includes_keep_false_cutter():
    """A keep=False cutter still produces a cut_by edge into earlier entries."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs = (a - b).resolve(cell)
    # B is keep=False but lives in slot 1; A's cut_by references it.
    assert rs.prisms[0].keep is True
    assert rs.prisms[1].keep is False
    assert rs.prisms[0].cut_by == (1,)


# ---- 2D resolve: data model ----------------------------------------------


def test_resolved_polygon_2d_default_fields():
    """New ResolvedPolygon2D defaults keep=True, cut_by=()."""
    from gdswell.stackup import ResolvedPolygon2D

    p = ResolvedPolygon2D(name="X", region=kdb.Region(), mesh_order=0)
    assert p.name == "X"
    assert p.region.is_empty()
    assert p.mesh_order == 0
    assert p.keep is True
    assert p.cut_by == ()


def test_resolved_polygon_2d_accepts_keep_and_cut_by():
    from gdswell.stackup import ResolvedPolygon2D

    p = ResolvedPolygon2D(name="X", region=kdb.Region(), mesh_order=2, keep=False, cut_by=(3, 5))
    assert p.keep is False
    assert p.cut_by == (3, 5)


def test_resolved_polygon_2d_is_frozen():
    from gdswell.stackup import ResolvedPolygon2D

    p = ResolvedPolygon2D(name="X", region=kdb.Region(), mesh_order=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.name = "Y"  # type: ignore[misc]


def test_resolved_stackup_2d_default_empty():
    from gdswell.stackup import ResolvedStackup2D

    rs2 = ResolvedStackup2D()
    assert rs2.polygons == ()


def test_resolved_stackup_2d_holds_polygons_tuple():
    from gdswell.stackup import ResolvedPolygon2D, ResolvedStackup2D

    p0 = ResolvedPolygon2D(name="A", region=kdb.Region(), mesh_order=0)
    p1 = ResolvedPolygon2D(name="B", region=kdb.Region(), mesh_order=1)
    rs2 = ResolvedStackup2D(polygons=(p0, p1))
    assert rs2.polygons == (p0, p1)


# ---- 2D resolve: _cutline_intervals --------------------------------------


def test_cutline_intervals_single_interval():
    """A cutline that crosses one rectangular region produces one interval."""
    from gdswell.stackup import _cutline_intervals

    region = kdb.Region(kdb.Box(0, 0, 2000, 2000))  # 2x2 µm at origin (dbu=0.001)
    cutline_edge = kdb.Edge(kdb.Point(-500, 1000), kdb.Point(2500, 1000))
    intervals = _cutline_intervals(region, cutline_edge)
    # The cutline enters the region at s=500 dbu and exits at s=2500 dbu
    # (since the cutline starts at x=-500 in dbu).
    assert intervals == ((500, 2500),)


def test_cutline_intervals_two_disjoint_intervals():
    """A cutline that crosses two disconnected components → two intervals."""
    from gdswell.stackup import _cutline_intervals

    region = kdb.Region()
    region.insert(kdb.Box(0, 0, 1000, 1000))  # 1x1 µm at origin
    region.insert(kdb.Box(2000, 0, 3000, 1000))  # 1x1 µm shifted right
    cutline_edge = kdb.Edge(kdb.Point(-500, 500), kdb.Point(3500, 500))
    intervals = _cutline_intervals(region, cutline_edge)
    assert intervals == ((500, 1500), (2500, 3500))


def test_cutline_intervals_no_overlap_empty():
    """Cutline that misses the region returns an empty tuple."""
    from gdswell.stackup import _cutline_intervals

    region = kdb.Region(kdb.Box(0, 0, 1000, 1000))
    cutline_edge = kdb.Edge(kdb.Point(0, 2000), kdb.Point(1000, 2000))
    intervals = _cutline_intervals(region, cutline_edge)
    assert intervals == ()


def test_cutline_intervals_empty_region():
    """An empty region returns an empty tuple."""
    from gdswell.stackup import _cutline_intervals

    region = kdb.Region()
    cutline_edge = kdb.Edge(kdb.Point(0, 0), kdb.Point(1000, 0))
    intervals = _cutline_intervals(region, cutline_edge)
    assert intervals == ()


def test_cutline_intervals_sorted_by_start():
    """Returned intervals are sorted by s_start ascending, regardless of
    klayout's internal ordering of result edges."""
    from gdswell.stackup import _cutline_intervals

    region = kdb.Region()
    # Three boxes intentionally not in left-to-right order.
    region.insert(kdb.Box(5000, 0, 6000, 1000))
    region.insert(kdb.Box(0, 0, 1000, 1000))
    region.insert(kdb.Box(2500, 0, 3500, 1000))
    cutline_edge = kdb.Edge(kdb.Point(-500, 500), kdb.Point(6500, 500))
    intervals = _cutline_intervals(region, cutline_edge)
    starts = [s0 for s0, _ in intervals]
    assert starts == sorted(starts)
    assert intervals == ((500, 1500), (3000, 4000), (5500, 6500))


# ---- 2D resolve: _loft_intervals -----------------------------------------


def test_loft_intervals_rectangle_two_z_keys():
    """Two z-keys with identical single intervals → axis-aligned rectangle."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((100, 500),),
        1.0: ((100, 500),),
    }
    dbu = 0.001  # 1 nm grid (1 µm == 1000 dbu)
    region = _loft_intervals(z_to_intervals, dbu, name="X")
    polys = list(region.each())
    assert len(polys) == 1
    box = polys[0].bbox()
    # Rectangle from s=100..500 dbu, z=0..1000 dbu (1 µm at dbu=0.001).
    assert box.left == 100
    assert box.right == 500
    assert box.bottom == 0
    assert box.top == 1000


def test_loft_intervals_trapezoid_two_z_keys():
    """Different interval widths at z_lo vs z_hi → trapezoid."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((0, 1000),),
        1.0: ((200, 800),),
    }
    dbu = 0.001
    region = _loft_intervals(z_to_intervals, dbu, name="X")
    polys = list(region.each())
    assert len(polys) == 1
    hull = list(polys[0].each_point_hull())
    # 4 vertices: (0,0), (1000,0), (800,1000), (200,1000). Order may vary,
    # but the set is fixed.
    vertex_set = {(p.x, p.y) for p in hull}
    assert vertex_set == {(0, 0), (1000, 0), (800, 1000), (200, 1000)}


def test_loft_intervals_two_intervals_paired_index_wise():
    """Two intervals at each z-key → two trapezoids, paired by sorted index."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((0, 100), (500, 600)),
        1.0: ((10, 90), (510, 590)),
    }
    dbu = 0.001
    region = _loft_intervals(z_to_intervals, dbu, name="X")
    region.merge()
    polys = list(region.each())
    assert len(polys) == 2
    # First poly is the left pair (small s), second the right pair.
    polys_sorted = sorted(polys, key=lambda p: p.bbox().left)
    assert polys_sorted[0].bbox().left == 0
    assert polys_sorted[0].bbox().right == 100
    assert polys_sorted[1].bbox().left == 500
    assert polys_sorted[1].bbox().right == 600


def test_loft_intervals_three_z_keys_stacked():
    """Three z-keys with the same interval produce stacked rectangles that
    merge into one taller rectangle after Region.merge()."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((0, 500),),
        0.5: ((0, 500),),
        1.0: ((0, 500),),
    }
    dbu = 0.001
    region = _loft_intervals(z_to_intervals, dbu, name="X")
    region.merge()
    polys = list(region.each())
    assert len(polys) == 1
    box = polys[0].bbox()
    assert box.left == 0
    assert box.right == 500
    assert box.bottom == 0
    assert box.top == 1000


def test_loft_intervals_empty_at_one_z_key_skips_pair():
    """If one z-key in a pair has no intervals, no polygon is emitted for
    that pair (and no error is raised)."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((0, 500),),
        1.0: (),
    }
    dbu = 0.001
    region = _loft_intervals(z_to_intervals, dbu, name="X")
    assert region.is_empty()


def test_loft_intervals_count_mismatch_raises():
    """Non-empty intervals with different counts at adjacent z-keys →
    NotImplementedError naming the entry and z-values."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {
        0.0: ((0, 500),),
        1.0: ((0, 200), (300, 500)),
    }
    dbu = 0.001
    with pytest.raises(NotImplementedError, match="entry 'X'.*z=0.0.*z=1.0"):
        _loft_intervals(z_to_intervals, dbu, name="X")


def test_loft_intervals_single_z_key_empty():
    """A single-z-key entry (zero-thickness sheet) produces an empty region
    in 2D output (sheet semantics are 3D-only per the spec)."""
    from gdswell.stackup import _loft_intervals

    z_to_intervals: dict[float, tuple[tuple[int, int], ...]] = {0.5: ((100, 500),)}
    dbu = 0.001
    region = _loft_intervals(z_to_intervals, dbu, name="Sheet")
    assert region.is_empty()


# ---- 2D resolve: Stackup.resolve_cutline ---------------------------------


def _cutline(p0, p1):
    """Convenience: build the public-API cutline tuple from two (x, y) points."""
    return (p0, p1)


def test_resolve_cutline_returns_resolved_stackup_2d():
    """resolve_cutline returns ResolvedStackup2D with 1:1 indexing."""
    from gdswell.stackup import ResolvedStackup2D

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    bot = StackupEntry.uniform("Bot", PDK.CLAD, -1.0, -0.5)
    rs2 = (si + bot).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    assert isinstance(rs2, ResolvedStackup2D)
    assert len(rs2.polygons) == 2
    assert [p.name for p in rs2.polygons] == ["Si", "Bot"]
    assert [p.mesh_order for p in rs2.polygons] == [0, 1]
    assert [p.keep for p in rs2.polygons] == [True, True]


def test_resolve_cutline_single_rectangle_entry():
    """A 1x1 WG square at xy=(0..1, 0..1), entry z=[0, 0.22], cutline through
    y=0.5: 2D region is a 1µm × 0.22µm rectangle in (s, z) space."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((-0.5, 0.5), (1.5, 0.5)))
    region = rs2.polygons[0].region
    region.merge()
    polys = list(region.each())
    assert len(polys) == 1
    box = polys[0].bbox()
    # cutline starts at x=-0.5 µm; enters region at x=0 → s=500 dbu; exits
    # at x=1 → s=1500 dbu. z from 0 to 0.22 µm → 0 to 220 dbu.
    assert box.left == 500
    assert box.right == 1500
    assert box.bottom == 0
    assert box.top == 220


def test_resolve_cutline_trapezoid_from_size_shrink():
    """An entry whose top z-key shrinks its xy region produces a trapezoid
    with slanted sidewalls in the (s, z) output."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    entry = StackupEntry("Si", {0.0: PDK.WG, 1.0: PDK.WG.size(-0.2)})
    rs2 = Stackup.of(entry).resolve_cutline(cell, _cutline((-0.5, 0.5), (1.5, 0.5)))
    region = rs2.polygons[0].region
    polys = list(region.each())
    assert len(polys) == 1
    hull = sorted(((p.x, p.y) for p in polys[0].each_point_hull()))
    # 4 vertices:
    #   bottom z=0: s=500..1500 (cutline enters at x=0, exits at x=1).
    #   top z=1µm=1000dbu: WG shrunk by 0.2 µm → x=0.2..0.8 → s=700..1300.
    assert hull == sorted([(500, 0), (1500, 0), (1300, 1000), (700, 1000)])


def test_resolve_cutline_missing_entry_empty_region():
    """An entry whose xy region is empty in this cell produces an empty
    2D region but keeps its slot in polygons (1:1 invariant)."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    # CLAD has no shapes in this cell.
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs2 = (a + b).resolve_cutline(cell, _cutline((-0.5, 0.5), (1.5, 0.5)))
    assert [p.name for p in rs2.polygons] == ["A", "B"]
    assert not rs2.polygons[0].region.is_empty()
    assert rs2.polygons[1].region.is_empty()


def test_resolve_cutline_cutline_misses_layout():
    """A cutline that doesn't cross any region → every prism has an empty
    region but is still emitted (1:1 invariant)."""
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((100.0, 100.0), (200.0, 100.0)))
    assert len(rs2.polygons) == 1
    assert rs2.polygons[0].region.is_empty()
    assert rs2.polygons[0].cut_by == ()


def test_resolve_cutline_two_disjoint_components_paired():
    """When an entry has two disjoint xy components and the cutline crosses
    both, each z-key has two intervals; the lofted region has two pieces."""
    cell = _cell_with_two_squares()
    # _cell_with_two_squares puts WG at (0,0)-(1,1) and CLAD at (2,0)-(3,1).
    # Use a layer recipe that unions both layers so the entry has 2 components.
    entry = StackupEntry.uniform("Both", PDK.WG + PDK.CLAD, 0.0, 0.22)
    rs2 = Stackup.of(entry).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    region = rs2.polygons[0].region
    region.merge()
    polys = sorted(region.each(), key=lambda p: p.bbox().left)
    assert len(polys) == 2
    # First component: WG square at x=0..1, cutline starts at x=-1 → s=1000..2000.
    assert polys[0].bbox().left == 1000
    assert polys[0].bbox().right == 2000
    # Second component: CLAD square at x=2..3 → s=3000..4000.
    assert polys[1].bbox().left == 3000
    assert polys[1].bbox().right == 4000


def test_resolve_cutline_topology_mismatch_raises():
    """An entry whose two z-keys have different interval counts on the
    cutline raises NotImplementedError naming the entry and z-values."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    # WG has one square; CLAD has two squares. Same entry has WG at z=0 and
    # CLAD at z=1 → cutline crosses 1 interval at z=0 and 2 at z=1.
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], PDK.CLAD)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], PDK.CLAD)
    entry = StackupEntry("A", {0.0: PDK.WG, 1.0: PDK.CLAD})
    with pytest.raises(NotImplementedError, match="entry 'A'.*z=0.0.*z=1.0"):
        Stackup.of(entry).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))


def test_resolve_cutline_cut_by_overlapping_2d_bbox():
    """Two entries whose 2D cutline-plane bboxes overlap → cut_by edge."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs2 = (a + b).resolve_cutline(cell, _cutline((-2.0, 0.5), (2.0, 0.5)))
    assert rs2.polygons[0].cut_by == (1,)
    assert rs2.polygons[1].cut_by == ()


def test_resolve_cutline_cut_by_disjoint_2d_bbox_no_edge():
    """Two entries whose 3D bboxes overlap but whose 2D projections don't
    overlap (one above the other in z, disjoint z-ranges) → no edge."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 0.4)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.6, 1.0)
    rs2 = (a + b).resolve_cutline(cell, _cutline((-2.0, 0.5), (2.0, 0.5)))
    # A's region spans z=0..0.4 µm; B's spans z=0.6..1.0 µm. Disjoint in z
    # (and therefore in 2D bbox), so no cut_by edge.
    assert rs2.polygons[0].cut_by == ()
    assert rs2.polygons[1].cut_by == ()


def test_resolve_cutline_keep_false_appears_with_keep_false_flag():
    """keep=False entries appear in polygons with keep=False so cut_by
    can reference them."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs2 = (a - b).resolve_cutline(cell, _cutline((-2.0, 0.5), (2.0, 0.5)))
    assert [p.name for p in rs2.polygons] == ["A", "B"]
    assert [p.keep for p in rs2.polygons] == [True, False]
    assert rs2.polygons[0].cut_by == (1,)


# ---- 2D resolve: resolve_cross_section -----------------------------------


def test_resolve_cross_section_simple_two_layer_profile():
    """A CrossSection with two LayerSections + a 2-key Stackup → expected
    rectangles in the output 2D region."""
    from gdswell.cross_section import CrossSection, LayerSection

    xs = CrossSection(
        layer_sections=(LayerSection(name="core", layer=PDK.WG, width=0.5, offset=0.0),)
    )
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cross_section(xs)
    region = rs2.polygons[0].region
    polys = list(region.each())
    assert len(polys) == 1
    box = polys[0].bbox()
    # In dbu (dbu=0.001 by default). CrossSection profile is width=0.5 µm
    # centred at y=0 → y∈[-0.25, 0.25]. The synthetic-straight cutline is
    # vertical, perpendicular to the straight, so s = y - y_min_with_margin.
    # The 2D region's height (in y) is the z-thickness = 0.22 µm → 220 dbu.
    assert box.top - box.bottom == 220
    # The 2D region's width (in x = s) is the CrossSection's width = 0.5 µm
    # → 500 dbu.
    assert box.right - box.left == 500


def test_resolve_cross_section_returns_resolved_stackup_2d():
    """Type and 1:1 indexing invariant."""
    from gdswell.cross_section import CrossSection, LayerSection
    from gdswell.stackup import ResolvedStackup2D

    xs = CrossSection(
        layer_sections=(LayerSection(name="core", layer=PDK.WG, width=0.5, offset=0.0),)
    )
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs2 = (a + b).resolve_cross_section(xs)
    assert isinstance(rs2, ResolvedStackup2D)
    assert len(rs2.polygons) == 2
    assert [p.name for p in rs2.polygons] == ["A", "B"]


def test_resolve_cross_section_cell_sections_warning():
    """A CrossSection with CellSections issues UserWarning naming the
    workaround (use resolve_cutline on a real cell)."""
    from gdswell.cross_section import CellSection, CrossSection, LayerSection

    sub_cell = gw.Cell(layout=gw.Layout())
    xs = CrossSection(
        layer_sections=(LayerSection(name="core", layer=PDK.WG, width=0.5, offset=0.0),),
        cell_sections=(CellSection(name="anchor", cell=sub_cell, periodicity=10.0),),
    )
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    with pytest.warns(UserWarning, match="anchor.*resolve_cutline"):
        Stackup.of(si).resolve_cross_section(xs)


def test_resolve_cross_section_topology_mismatch_impossible():
    """The synthetic-straight path always produces matching interval counts
    (one per LayerSection at every z-key). Even with size-shrunk z-keys,
    no NotImplementedError fires."""
    from gdswell.cross_section import CrossSection, LayerSection

    xs = CrossSection(
        layer_sections=(LayerSection(name="core", layer=PDK.WG, width=0.5, offset=0.0),)
    )
    # Entry shrinks WG at the top z-key — would mismatch via a manual
    # resolve_cutline if the cell had multiple disconnected WG components.
    # Through resolve_cross_section the cell has a single rectangle, so
    # the cutline crosses one interval at every z-key.
    entry = StackupEntry("Si", {0.0: PDK.WG, 1.0: PDK.WG.size(-0.1)})
    rs2 = Stackup.of(entry).resolve_cross_section(xs)
    region = rs2.polygons[0].region
    polys = list(region.each())
    assert len(polys) == 1  # one trapezoid; no exception raised.


# ---- dbu round-trip ------------------------------------------------------


def test_resolved_stackup_dbu_default():
    """ResolvedStackup default dbu is 0.001 (klayout's default 1 nm grid)."""
    rs = ResolvedStackup()
    assert rs.dbu == 0.001


def test_resolve_populates_dbu_from_cell():
    """Stackup.resolve(cell) populates dbu from cell.layout.kdb.dbu."""
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs = Stackup.of(si).resolve(cell)
    assert rs.dbu == cell.layout.kdb.dbu


def test_resolved_stackup_2d_dbu_default():
    """ResolvedStackup2D default dbu is 0.001."""
    from gdswell.stackup import ResolvedStackup2D

    rs2 = ResolvedStackup2D()
    assert rs2.dbu == 0.001


def test_resolve_cutline_populates_dbu():
    """resolve_cutline populates dbu from cell.layout.kdb.dbu."""
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    assert rs2.dbu == cell.layout.kdb.dbu


def test_resolve_cross_section_populates_dbu():
    """resolve_cross_section inherits dbu from its synthetic Cell (klayout default 0.001)."""
    from gdswell.cross_section import CrossSection, LayerSection

    xs = CrossSection(
        layer_sections=(LayerSection(name="core", layer=PDK.WG, width=0.5, offset=0.0),)
    )
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cross_section(xs)
    assert rs2.dbu == 0.001


# ---- plot_cross_section --------------------------------------------------


def test_plot_cross_section_returns_axes():
    """plot_cross_section returns a matplotlib Axes."""
    import matplotlib

    matplotlib.use("Agg")  # non-interactive backend for CI
    from gdswell.visualization import plot_cross_section

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    ax = plot_cross_section(rs2)
    import matplotlib.axes

    assert isinstance(ax, matplotlib.axes.Axes)


def test_plot_cross_section_uses_provided_ax():
    """When passed an existing Axes, plot_cross_section draws on it and returns it."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from gdswell.visualization import plot_cross_section

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    fig, my_ax = plt.subplots()
    returned_ax = plot_cross_section(rs2, ax=my_ax)
    assert returned_ax is my_ax


def test_plot_cross_section_empty_input_no_raise():
    """plot_cross_section accepts an empty ResolvedStackup2D without raising."""
    import matplotlib

    matplotlib.use("Agg")
    from gdswell.visualization import plot_cross_section

    ax = plot_cross_section(ResolvedStackup2D())
    import matplotlib.axes

    assert isinstance(ax, matplotlib.axes.Axes)


def test_plot_cross_section_legend_entries_match_kept_names():
    """Legend has one entry per unique kept prism name."""
    import matplotlib

    matplotlib.use("Agg")
    from gdswell.visualization import plot_cross_section

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    bot = StackupEntry.uniform("Bot", PDK.CLAD, -1.0, -0.5)
    rs2 = (si + bot).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    ax = plot_cross_section(rs2)
    legend = ax.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert sorted(labels) == ["Bot", "Si"]


def test_plot_cross_section_apply_cuts_omits_fully_carved_region():
    """With apply_cuts=True, a prism whose region is fully covered by a
    later cutter contributes no patches. With apply_cuts=False, it still
    appears."""
    import matplotlib

    matplotlib.use("Agg")
    from gdswell.visualization import plot_cross_section

    cell = _cell_with_overlap()
    # A's xy region (the 1x1 WG square) is entirely covered by B (the 2x2 CLAD
    # square). After painter's-algorithm 2D carve, A is fully removed.
    a = StackupEntry.uniform("A", PDK.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", PDK.CLAD, 0.0, 1.0)
    rs2 = (a + b).resolve_cutline(cell, _cutline((-2.0, 0.5), (2.0, 0.5)))

    # apply_cuts=True: A's patches absent from the legend (its final region is empty).
    ax_cut = plot_cross_section(rs2, apply_cuts=True)
    legend_cut = ax_cut.get_legend()
    assert legend_cut is not None
    labels_cut = [t.get_text() for t in legend_cut.get_texts()]
    assert "A" not in labels_cut
    assert "B" in labels_cut

    # apply_cuts=False: A appears (raw region).
    ax_raw = plot_cross_section(rs2, apply_cuts=False)
    legend_raw = ax_raw.get_legend()
    assert legend_raw is not None
    labels_raw = [t.get_text() for t in legend_raw.get_texts()]
    assert "A" in labels_raw
    assert "B" in labels_raw


def test_plot_cross_section_color_map_override():
    """color_map overrides the palette for the named prism."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors

    from gdswell.visualization import plot_cross_section

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", PDK.WG, 0.0, 0.22)
    rs2 = Stackup.of(si).resolve_cutline(cell, _cutline((-1.0, 0.5), (4.0, 0.5)))
    ax = plot_cross_section(rs2, color_map={"Si": "#ff0000"})
    # Find the patch labelled "Si" and check its facecolor.
    target = mcolors.to_rgba("#ff0000")
    patches_for_si = [p for p in ax.patches if p.get_label() == "Si"]
    assert patches_for_si, "Si patch not rendered"
    # Compare RGB (ignore alpha, which the plotter may set independently).
    assert patches_for_si[0].get_facecolor()[:3] == target[:3]
