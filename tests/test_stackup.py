# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import dataclasses
from enum import Enum

import klayout.db as kdb

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
from gdswell.stackup import ResolvedPrism, ResolvedStackup, Stackup, StackupEntry, StackupItem


class Pdk(gw.Layer, Enum):
    WG = (1, 0)
    CLAD = (2, 0)
    MASK = (3, 0)


def test_entry_construction_minimum():
    e = StackupEntry("Si", {0.0: Pdk.WG, 0.22: Pdk.WG.size(-0.05)})
    assert e.name == "Si"
    assert set(e.z_to_layer.keys()) == {0.0, 0.22}


def test_entry_single_key_allowed():
    # Zero-thickness sheet — useful as boundary tag / cut surface.
    e = StackupEntry("Sheet", {0.0: Pdk.WG})
    assert len(e.z_to_layer) == 1


def test_entry_uniform_helper():
    e = StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22)
    assert e.name == "Si"
    assert e.z_to_layer == {0.0: Pdk.WG, 0.22: Pdk.WG}


def test_entry_equal_and_hashable():
    a = StackupEntry("Si", {0.0: Pdk.WG, 0.22: Pdk.WG.size(-0.05)})
    b = StackupEntry("Si", {0.22: Pdk.WG.size(-0.05), 0.0: Pdk.WG})  # dict order
    assert a == b
    assert hash(a) == hash(b)
    # Different name → not equal
    c = StackupEntry("SiN", {0.0: Pdk.WG, 0.22: Pdk.WG.size(-0.05)})
    assert a != c


def test_entry_hash_string_deterministic():
    a = StackupEntry("Si", {0.0: Pdk.WG, 0.22: Pdk.WG.size(-0.05)})
    b = StackupEntry("Si", {0.22: Pdk.WG.size(-0.05), 0.0: Pdk.WG})
    assert a._hash_string == b._hash_string
    assert "Si" in a._hash_string


def _e(name, *zs):
    return StackupEntry(name, {z: Pdk.WG for z in zs})


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
    e = StackupEntry("Si", {0.0: Pdk.WG, 1.0: Pdk.WG.size(-0.05)})
    sized = e.size(0.1)
    assert isinstance(sized, StackupEntry)
    assert sized.name == "Si"
    for L in sized.z_to_layer.values():
        assert isinstance(L, LayerSize)
    # original is untouched
    assert all(not isinstance(L, LayerSize) or L.dx == -0.05 for L in e.z_to_layer.values())


def test_entry_size_dy_independent():
    e = StackupEntry.uniform("X", Pdk.WG, 0.0, 1.0)
    sized = e.size(0.2, 0.3)
    for L in sized.z_to_layer.values():
        assert isinstance(L, LayerSize)
        assert L.dx == 0.2 and L.dy == 0.3


def test_entry_transformed_wraps_every_layer():
    e = StackupEntry.uniform("X", Pdk.WG, 0.0, 1.0)
    t = kdb.DTrans(1.0, 2.0)
    out = e.transformed(t)
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerTransformed)


def test_entry_round_corners_wraps_every_layer():
    e = StackupEntry.uniform("X", Pdk.WG, 0.0, 1.0)
    out = e.round_corners(0.1, 0.1, 16)
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerRounded)


def test_entry_bbox_wraps_every_layer():
    e = StackupEntry.uniform("X", Pdk.WG, 0.0, 1.0)
    out = e.bbox()
    for L in out.z_to_layer.values():
        assert isinstance(L, LayerBBox)


def test_entry_map_layers_general():
    e = StackupEntry("X", {0.0: Pdk.WG, 1.0: Pdk.CLAD})
    out = e.map_layers(lambda L: L + Pdk.MASK)  # boolean union with MASK
    for L in out.z_to_layer.values():
        # The result is a LayerUnion of the original and Pdk.MASK
        assert hasattr(L, "left") and hasattr(L, "right")


def test_stackup_size_applies_to_all_entries_including_cuts():
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", Pdk.MASK, 0.0, 1.0)
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
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    stack = a + b
    out = stack.map_layers(lambda L: L.size(0.5))
    for it in out.items:
        for L in it.entry.z_to_layer.values():
            assert isinstance(L, LayerSize)
            assert L.dx == 0.5


def test_entry_filters_wrap_every_layer():
    e = StackupEntry.uniform("X", Pdk.WG, 0.0, 1.0)

    inter = e.interacting(Pdk.MASK)
    for L in inter.z_to_layer.values():
        assert isinstance(L, LayerInteracting)

    not_inter = e.interacting(Pdk.MASK, invert=True)
    for L in not_inter.z_to_layer.values():
        assert isinstance(L, LayerNotInteracting)

    ins = e.inside(Pdk.MASK)
    for L in ins.z_to_layer.values():
        assert isinstance(L, LayerInside)

    outs = e.outside(Pdk.MASK)
    for L in outs.z_to_layer.values():
        assert isinstance(L, LayerOutside)

    overlap = e.overlapping(Pdk.MASK, min_count=2)
    for L in overlap.z_to_layer.values():
        assert isinstance(L, LayerOverlapping)
        assert L.min_count == 2


def test_stackup_filters_apply_to_all_entries():
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    out = (a + b).inside(Pdk.MASK)
    for it in out.items:
        for L in it.entry.z_to_layer.values():
            assert isinstance(L, LayerInside)


def _cell_with_two_squares():
    """A cell with a 1x1 µm square on Pdk.WG at origin, and another on Pdk.CLAD shifted right."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], Pdk.CLAD)
    return cell


def test_resolve_non_overlapping_entries():
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22)
    bot = StackupEntry.uniform("Bot", Pdk.CLAD, -1.0, -0.5)
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
    si = StackupEntry.uniform("Si", Pdk.WG, 0.0, 1.0)
    other = StackupEntry.uniform("Other", Pdk.CLAD, 2.0, 3.0)
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
    si = StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22)
    prisms = Stackup.of(si).resolve(cell).prisms
    assert len(prisms) == 1
    assert prisms[0].name == "Si"
    assert set(prisms[0].z_to_region.keys()) == {0.0, 0.22}


def _cell_with_overlap():
    """1x1 square on WG at origin; bigger 2x2 square on CLAD covering it."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)], Pdk.CLAD)
    return cell


def test_resolve_overlapping_entries_keep_raw_regions():
    """Resolve no longer performs 2D cuts. Two entries that overlap in xy
    both appear with their un-subtracted raw regions; the painter's
    'later-wins' semantics is now the 3D backend's responsibility."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
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
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
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
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], Pdk.WG)
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.3, 0.6)
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
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.CLAD)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], Pdk.CLAD)

    a = StackupEntry("A", {0.0: Pdk.WG, 1.0: Pdk.CLAD})
    b = StackupEntry.uniform("B", Pdk.MASK, 0.5, 0.7)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.MASK)

    # Should not raise.
    rs = (a + b).resolve(cell)
    assert len(rs.prisms) == 2


def test_resolve_keep_false_appears_with_keep_false_flag():
    """keep=False entries appear in prisms with keep=False so cut_by can
    reference them. The downstream backend skips emitting their volume."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
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
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    # CLAD has no shapes in this cell.

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)  # B's layer is empty
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
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    a2 = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
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
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)

    sheet = StackupEntry("Sheet", {0.5: Pdk.WG})
    [p] = Stackup.of(sheet).resolve(cell).prisms
    assert list(p.z_to_region.keys()) == [0.5]
    assert p.z_to_region[0.5].area() == 1_000_000


def test_top_level_exports():
    import gdswell as gw

    assert gw.StackupEntry is StackupEntry
    assert gw.Stackup is Stackup
    assert gw.ResolvedPrism is ResolvedPrism
    assert gw.ResolvedStackup is ResolvedStackup


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
    a = StackupEntry("A", {0.0: Pdk.WG, 0.5: Pdk.WG.size(-0.1), 1.0: Pdk.WG.size(-0.2)})
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.7, 1.3)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert sorted(by_name["A"].z_to_region) == [0.0, 0.5, 1.0]
    assert sorted(by_name["B"].z_to_region) == [0.7, 1.3]


def test_resolve_index_invariant():
    """len(rs.prisms) == len(stack.items); each prism.mesh_order == its index."""
    cell = _cell_with_two_squares()
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", Pdk.MASK, 0.0, 1.0)
    stack = a + b - c
    rs = stack.resolve(cell)
    assert len(rs.prisms) == len(stack.items) == 3
    for i, p in enumerate(rs.prisms):
        assert p.mesh_order == i


def test_resolve_cut_by_disjoint_z_no_edge():
    """Two entries with overlapping xy but disjoint z get no cut_by edge."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 0.5)
    b = StackupEntry.uniform("B", Pdk.CLAD, 1.0, 1.5)  # above A, disjoint
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert by_name["A"].cut_by == ()
    assert by_name["B"].cut_by == ()


def test_resolve_cut_by_disjoint_xy_bbox_no_edge():
    """Two entries with overlapping z but disjoint xy bboxes get no edge."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(10, 0), (11, 0), (11, 1), (10, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    by_name = {p.name: p for p in rs.prisms}
    assert by_name["A"].cut_by == ()
    assert by_name["B"].cut_by == ()


def test_resolve_cut_by_overlapping_bbox_emits_edge():
    """Two entries whose 3D bboxes overlap → cut_by edge from earlier to later."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    rs = (a + b).resolve(cell)
    # Index 0 = A; index 1 = B. cut_by is forward-only.
    assert rs.prisms[0].cut_by == (1,)
    assert rs.prisms[1].cut_by == ()


def test_resolve_cut_by_painter_order_forward_only():
    """cut_by indices are strictly greater than the prism's own index.
    Also confirms at least one prism has a non-empty cut_by so the assertion
    is not vacuously satisfied."""
    cell = _cell_with_overlap()
    cell.add_polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)], Pdk.MASK)
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    c = StackupEntry.uniform("C", Pdk.MASK, 0.0, 1.0)
    rs = (a + b + c).resolve(cell)
    # Guard against vacuous pass: at least one prism must have a cut_by edge.
    assert any(p.cut_by for p in rs.prisms)
    for i, p in enumerate(rs.prisms):
        for j in p.cut_by:
            assert j > i


def test_resolve_cut_by_includes_keep_false_cutter():
    """A keep=False cutter still produces a cut_by edge into earlier entries."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    rs = (a - b).resolve(cell)
    # B is keep=False but lives in slot 1; A's cut_by references it.
    assert rs.prisms[0].keep is True
    assert rs.prisms[1].keep is False
    assert rs.prisms[0].cut_by == (1,)
