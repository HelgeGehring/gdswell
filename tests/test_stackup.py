# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import gdswell as gw
from gdswell.stackup import StackupEntry


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


from gdswell.stackup import Stackup, StackupItem


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
        ("A", True), ("B", True), ("C", False), ("D", True)
    ]
    nested = a + (b - c) + d
    # Same flat tuple — left-to-right associativity makes this equivalent here.
    assert [(it.entry.name, it.keep) for it in nested.items] == [
        ("A", True), ("B", True), ("C", False), ("D", True)
    ]


def test_stackup_hash_order_sensitive():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    assert hash(a + b) != hash(b + a)


def test_stackup_hash_string_includes_keep_flag():
    a, b = _e("A", 0.0, 1.0), _e("B", 0.0, 1.0)
    assert (a - b)._hash_string != (a + b)._hash_string


import klayout.db as kdb

from gdswell.layer import LayerSize, LayerTransformed, LayerRounded, LayerBBox


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
        ("A", True), ("B", True), ("C", False)
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


from gdswell.layer import (
    LayerInteracting,
    LayerNotInteracting,
    LayerInside,
    LayerOutside,
    LayerOverlapping,
)


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


from gdswell.stackup import ResolvedPrism


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
    bot = StackupEntry.uniform("Bot", Pdk.CLAD, -1.0, -0.5)  # different z-range, different layer
    prisms = (si + bot).resolve(cell)

    assert len(prisms) == 2
    by_name = {p.name: p for p in prisms}
    assert set(by_name) == {"Si", "Bot"}

    # mesh_order matches list position
    assert by_name["Si"].mesh_order == 0
    assert by_name["Bot"].mesh_order == 1

    # Each surviving entry keeps its original z-keys (no cuts forced extra ones).
    assert set(by_name["Si"].z_to_region.keys()) == {0.0, 0.22}
    assert set(by_name["Bot"].z_to_region.keys()) == {-1.0, -0.5}

    # Areas are non-empty and in dbu² (klayout uses 1 nm grid by default; 1µm² = 1e6 dbu²).
    for p in prisms:
        for r in p.z_to_region.values():
            assert r.area() > 0


def test_resolve_returns_frozen_dataclass():
    import dataclasses

    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", Pdk.WG, 0.0, 1.0)
    other = StackupEntry.uniform("Other", Pdk.CLAD, 2.0, 3.0)
    p = (si + other).resolve(cell)[0]
    assert dataclasses.is_dataclass(p)
    # frozen → reassignment must raise
    try:
        p.name = "nope"
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ResolvedPrism should be frozen")


def test_entry_resolve_via_stackup_singleton():
    """A single StackupEntry, lifted into a 1-item Stackup, resolves cleanly."""
    cell = _cell_with_two_squares()
    si = StackupEntry.uniform("Si", Pdk.WG, 0.0, 0.22)
    prisms = Stackup.of(si).resolve(cell)
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


def test_resolve_later_wins_at_shared_z():
    """Two entries with the same z-range overlapping in plan view: later wins."""
    cell = _cell_with_overlap()
    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    prisms = (a + b).resolve(cell)
    by_name = {p.name: p for p in prisms}
    # B's region at z=0 is the full 2x2 square (4 µm² = 4_000_000 dbu²).
    # A's region at z=0, post-overlay, is WG minus CLAD — the WG square is
    # entirely covered by the CLAD 2x2, so A becomes empty and is pruned.
    assert "B" in by_name
    assert "A" not in by_name
    # B's area is unchanged.
    assert by_name["B"].z_to_region[0.0].area() == 4_000_000


def test_resolve_partial_overlap_carves_earlier_entry():
    """A's plan-view region is partially covered by B; A keeps the remainder."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    # A: 2x1 strip on WG from x=0 to x=2
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)
    # B: 1x1 strip on CLAD from x=1 to x=2 (covers right half of A)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    prisms = (a + b).resolve(cell)
    by_name = {p.name: p for p in prisms}
    # A keeps the left half (1 µm² = 1_000_000 dbu²)
    assert by_name["A"].z_to_region[0.0].area() == 1_000_000
    # B is unchanged (1 µm²)
    assert by_name["B"].z_to_region[0.0].area() == 1_000_000


def test_resolve_cut_introduces_global_z_keys_via_morph():
    """A's z=[0,1] is cut by B at z=[0.3,0.6]. After painter's algorithm A
    has new z-keys at 0.3 and 0.6 (linear-morph topology preserved here
    because both layers are simple ``Layer`` rectangles)."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    # A and B both project to the same 2x2 square (so subtraction is exact)
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], Pdk.WG)
    cell.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.3, 0.6)
    prisms = (a + b).resolve(cell)
    by_name = {p.name: p for p in prisms}

    # A has gained z-keys at 0.3 and 0.6 (the cut's range).
    a_keys = sorted(by_name["A"].z_to_region.keys())
    assert a_keys == [0.0, 0.3, 0.6, 1.0]

    # At z=0.0, A is unchanged (full 2x2 = 4e6 dbu²).
    assert by_name["A"].z_to_region[0.0].area() == 4_000_000
    # At z=0.3 and z=0.6, A is fully cut by B (empty).
    assert by_name["A"].z_to_region[0.3].area() == 0
    assert by_name["A"].z_to_region[0.6].area() == 0
    # At z=1.0, A is unchanged again.
    assert by_name["A"].z_to_region[1.0].area() == 4_000_000


def test_resolve_topology_mismatch_raises_on_resample():
    """Entry's two z-key regions have different topology; a cut forces
    resampling at an intermediate z, which raises NotImplementedError."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    # WG has a 1x1 square; CLAD has two disjoint squares (different topology)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.CLAD)
    cell.add_polygon([(2, 0), (3, 0), (3, 1), (2, 1)], Pdk.CLAD)

    a = StackupEntry("A", {0.0: Pdk.WG, 1.0: Pdk.CLAD})  # 1 polygon → 2 polygons
    b = StackupEntry.uniform("B", Pdk.MASK, 0.5, 0.7)
    # If MASK is empty in this cell, the cut is trivial and no resample needed.
    # Add a MASK polygon to force the cut to actually do work.
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.MASK)

    import pytest
    with pytest.raises(NotImplementedError, match="topology"):
        (a + b).resolve(cell)


def test_resolve_keep_false_cuts_but_does_not_appear():
    """A - B: B cuts A but is dropped from output."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)    # A's projection
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)  # B's projection (right half)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    prisms = (a - b).resolve(cell)
    names = [p.name for p in prisms]
    assert names == ["A"]
    # A has the left half left over (1 µm²)
    [a_out] = prisms
    assert a_out.z_to_region[0.0].area() == 1_000_000


def test_resolve_drops_empty_entries():
    """A entirely covered by B → A drops from output."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    prisms = (a + b).resolve(cell)
    assert [p.name for p in prisms] == ["B"]


def test_resolve_re_add_after_cut():
    """A - B + A: strict painter's-order semantics.

    Walk left-to-right:
      1. Register A (full WG strip).
      2. B (keep=False) is added; subtract B from A → A_1 = WG \\ CLAD = left half.
      3. A_2 (full WG strip) is added; subtract A_2 from A_1 AND from B.
         A_1 = (WG \\ CLAD) \\ WG = empty → pruned.
         B is keep=False → also dropped.
         A_2 has nothing after it → unchanged.
    Net: a single "A" prism equal to the full WG strip.
    """
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    # Two layers projecting to the same 2x1 strip
    cell.add_polygon([(0, 0), (2, 0), (2, 1), (0, 1)], Pdk.WG)
    cell.add_polygon([(1, 0), (2, 0), (2, 1), (1, 1)], Pdk.CLAD)

    a = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)
    a2 = StackupEntry.uniform("A", Pdk.WG, 0.0, 1.0)  # same name allowed
    b = StackupEntry.uniform("B", Pdk.CLAD, 0.0, 1.0)
    prisms = (a - b + a2).resolve(cell)

    assert [p.name for p in prisms] == ["A"]
    assert prisms[0].z_to_region[0.0].area() == 2_000_000


def test_resolve_single_key_zero_thickness_sheet_preserved():
    """A single-z-key entry is a zero-thickness sheet; its region is preserved."""
    layout = gw.Layout()
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)

    sheet = StackupEntry("Sheet", {0.5: Pdk.WG})
    [p] = Stackup.of(sheet).resolve(cell)
    assert list(p.z_to_region.keys()) == [0.5]
    assert p.z_to_region[0.5].area() == 1_000_000


def test_top_level_exports():
    import gdswell as gw
    assert gw.StackupEntry is StackupEntry
    assert gw.Stackup is Stackup
    assert gw.ResolvedPrism is ResolvedPrism
