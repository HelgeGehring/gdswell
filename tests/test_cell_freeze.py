# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from collections.abc import Mapping

import pytest

import gdswell as gw


@gw.cell
def info_frozen_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_info("author", "Antigravity")
    return c


@gw.cell
def port_frozen_cell() -> gw.Cell:
    c = gw.Cell()
    p1 = gw.Port("p1", (0, 0), 0, cross_section=gw.CrossSection(()))
    c.add_port(p1)
    return c


@gw.cell
def version_frozen_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_info("version", 1)
    return c


@gw.cell
def my_frozen_cell() -> gw.Cell:
    return gw.Cell()


def test_cell_info_immutability() -> None:
    with gw.Layout():
        c = info_frozen_cell()
        assert c.info["author"] == "Antigravity"

        # Verify it's now a Mapping (effectively read-only)
        assert isinstance(c.info, Mapping)

        # Modification should raise TypeError (from MappingProxyType)
        with pytest.raises(TypeError, match="does not support item assignment"):
            c.info["author"] = "Someone else"  # type: ignore[invalid-assignment]

        with pytest.raises(AttributeError, match="has no attribute 'clear'"):
            c.info.clear()  # type: ignore[attr-defined]


def test_cell_ports_immutability() -> None:
    with gw.Layout():
        c = port_frozen_cell()
        assert "p1" in c.ports

        # Verify it's a Mapping
        assert isinstance(c.ports, Mapping)

        # Modification via property should raise TypeError
        with pytest.raises(TypeError, match="does not support item assignment"):
            c.ports["p2"] = gw.Port("p2", (1, 1), 90, cross_section=gw.CrossSection(()))  # type: ignore[invalid-assignment]

        # Modification via add_port should raise RuntimeError
        with pytest.raises(RuntimeError, match="frozen"):
            c.add_port(gw.Port("p2", (1, 1), 90, cross_section=gw.CrossSection(())))


def test_restored_cell_immutability() -> None:
    with gw.Layout() as layout:
        c1 = version_frozen_cell()

        # Wrapped cell around same kdb cell
        c2 = gw.Cell._from_kdb_cell(c1.kdb, layout=layout)

        assert c2.frozen
        assert isinstance(c2.info, Mapping)
        assert c2.info["version"] == 1

        with pytest.raises(TypeError, match="does not support item assignment"):
            c2.info["version"] = 2  # type: ignore[invalid-assignment]

        with pytest.raises(RuntimeError, match="frozen"):
            c2.add_port(gw.Port("p2", (0, 0), 0, cross_section=gw.CrossSection(())))


if __name__ == "__main__":
    pytest.main([__file__])


def test_double_freeze() -> None:
    with gw.Layout():
        c = my_frozen_cell()  # ALREADY frozen by decorator
        # Should raise
        with pytest.raises(RuntimeError, match="already frozen"):
            c.freeze()


def test_freeze_unnamed_raises() -> None:
    c = gw.Cell()
    with pytest.raises(RuntimeError, match="Cannot freeze unnamed cell"):
        c.freeze()
