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
