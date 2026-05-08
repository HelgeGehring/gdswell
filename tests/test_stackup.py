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
