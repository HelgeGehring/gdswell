# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum
from pathlib import Path

import klayout.db as kdb
import numpy as np
import pytest

import gdswell as gw


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)


@gw.cell
def _cell_my_component(width: float = 10.0) -> gw.Cell:
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=width)
    xs = gw.CrossSection(layer_sections=(ls,))
    c = gw.Cell()
    c.add_polygon(
        [(0, -width / 2), (20, -width / 2), (20, width / 2), (0, width / 2)], layer=MyLayers.WG
    )
    c.add_info("component_type", "waveguide")
    c.add_port(gw.Port(name="o1", position=(0, 0), angle=180, cross_section=xs))
    return c


@gw.cell
def _cell_tapering_wg() -> gw.Cell:
    # width = 2.0 + 3.0 * s
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=2.0 + 3.0 * gw.S)
    xs = gw.CrossSection(layer_sections=(ls,))
    c = gw.Cell()
    c.add_port(gw.Port(name="o1", position=(0, 0), angle=0, cross_section=xs))
    return c


def test_read_gds_basic(tmp_path: Path) -> None:
    gds_path = tmp_path / "test.gds"

    # 1. Create and save a cell
    with gw.Layout() as ly_out:
        c1 = _cell_my_component(width=5.0)
        c1_name = c1.name
        ly_out.write(str(gds_path))

    # 2. Read it back in a new layout
    with gw.Layout() as ly_in:
        # Explicit name (requires prefix)
        c2 = ly_in.read(str(gds_path), "ext", cell_name=c1_name)
        assert c2.name == "ext:" + c1_name
        assert c2.info["component_type"] == "waveguide"
        assert "o1" in c2.ports
        assert c2.ports["o1"].position == (0, 0)

        # Default (top cell, requires prefix)
        c3 = ly_in.read(str(gds_path), "ext")
        assert c3.name == "ext:" + c1_name
        assert c3 is c2  # Should be same object (ext:name)
        assert c3 is c2  # Should be the same object due to caching in ly_in


def test_read_gds_cache_integration(tmp_path: Path) -> None:
    gds_path = tmp_path / "cache_test.gds"

    # 1. Create and save
    with gw.Layout() as ly_out:
        c_orig = _cell_my_component(width=8.0)
        name = c_orig.name
        ly_out.write(str(gds_path))

    # 2. Start new layout, read GDS, then call @cell function
    with gw.Layout() as ly_in:
        # First, read the GDS using _read_internal for cache-like behavior (no prefix)
        c_read = ly_in._read_internal(str(gds_path), cell_name=name)

        # Now call the @cell function with same args
        # It should compute the same name and find the read cell in the layout
        c_called = _cell_my_component(width=8.0)

        assert c_called.name == name
        assert c_called is c_read
        assert c_called.frozen  # Read cells should be frozen if they were frozen when saved


def test_read_gds_error_handling(tmp_path: Path) -> None:
    empty_gds = tmp_path / "empty.gds"
    kdb.Layout().write(str(empty_gds))

    with gw.Layout() as ly:
        with pytest.raises(ValueError, match="No cells found"):
            ly.read(str(empty_gds), "err")

    # Test non-existent cell in a non-empty GDS
    valid_gds = tmp_path / "valid.gds"
    with gw.Layout() as ly_out:
        _cell_my_component(width=5.0)
        ly_out.write(str(valid_gds))

    with gw.Layout() as ly:
        with pytest.raises(ValueError, match="Cell 'NonExistent' not found"):
            ly.read(str(valid_gds), "err", cell_name="NonExistent")


def test_read_gds_multiple_top_cells(tmp_path: Path) -> None:
    gds_path = tmp_path / "multiple.gds"

    # 1. Create two independent top cells
    with gw.Layout() as ly_out:
        c1 = _cell_my_component(width=4.0)
        c2 = _cell_my_component(width=6.0)
        c1_name, c2_name = c1.name, c2.name
        ly_out.write(str(gds_path))

    # 2. Read only one - only that hierarchy should be in the layout
    with gw.Layout() as ly_in:
        ly_in._read_internal(str(gds_path), cell_name=c1_name)

        # c1 should be there
        assert ly_in.cell(c1_name).name == c1_name
        # c2 should NOT be there because we only imported c1's hierarchy
        with pytest.raises(KeyError):
            ly_in.cell(c2_name)


def test_read_gds_sympy_cross_section(tmp_path: Path) -> None:
    gds_path = tmp_path / "sympy.gds"

    # 1. Create and save
    with gw.Layout() as ly_out:
        c_orig = _cell_tapering_wg()
        name = c_orig.name
        ly_out.write(str(gds_path))

    # 2. Read back
    with gw.Layout() as ly_in:
        c_read = ly_in._read_internal(str(gds_path), cell_name=name)
        xs_read = c_read.ports["o1"].cross_section
        ls_read = xs_read.layer_sections[0]

        # Verify it's a sympy expression and not a float/string
        import sympy

        assert isinstance(ls_read.width, sympy.Expr)
        # Check value at s=0 and s=1
        assert float(ls_read._fw(np.array([0.0]))[0]) == 2.0
        assert float(ls_read._fw(np.array([1.0]))[0]) == 5.0


if __name__ == "__main__":
    # For manual running if needed
    pytest.main([__file__])
