# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum
from pathlib import Path

import gdswell as gw
from gdswell.future_cell import FutureCell


class Pdk(gw.Layer, Enum):
    WG = (1, 0)


@gw.cell
def subcell(width: float = 1.0) -> gw.Cell:
    c = gw.Cell()
    c.add_polygon(
        [(0, -width / 2), (width, -width / 2), (width, width / 2), (0, width / 2)], layer=Pdk.WG
    )
    return c


@gw.cell
def cell_with_xs(xs: gw.CrossSection) -> gw.Cell:
    c = gw.Cell()
    # In a real scenario, we might use xs to build something
    # For testing cache, just having it as an argument is enough
    return c


def test_cell_section_cache_hit() -> None:
    with gw.Layout():
        sc = subcell(width=2.0)

        cs1 = gw.CellSection(name="test", cell=sc, periodicity=10.0)
        xs1 = gw.CrossSection(cell_sections=(cs1,))

        c1 = cell_with_xs(xs=xs1)

        # Identical CS and XS
        cs2 = gw.CellSection(name="test", cell=sc, periodicity=10.0)
        xs2 = gw.CrossSection(cell_sections=(cs2,))

        c2 = cell_with_xs(xs=xs2)

        assert c1 is c2
        assert c1.name == c2.name


def test_cell_section_cache_miss() -> None:
    with gw.Layout():
        sc = subcell(width=2.0)

        cs1 = gw.CellSection(name="test", cell=sc, periodicity=10.0)
        xs1 = gw.CrossSection(cell_sections=(cs1,))

        c1 = cell_with_xs(xs=xs1)

        # Different periodicity
        cs2 = gw.CellSection(name="test", cell=sc, periodicity=11.0)
        xs2 = gw.CrossSection(cell_sections=(cs2,))

        c2 = cell_with_xs(xs=xs2)

        assert c1 is not c2
        assert c1.name != c2.name


def test_cell_section_cache_different_subcell() -> None:
    with gw.Layout():
        sc1 = subcell(width=2.0)
        sc2 = subcell(width=3.0)

        cs1 = gw.CellSection(name="test", cell=sc1, periodicity=10.0)
        xs1 = gw.CrossSection(cell_sections=(cs1,))

        c1 = cell_with_xs(xs=xs1)

        # Different subcell
        cs2 = gw.CellSection(name="test", cell=sc2, periodicity=10.0)
        xs2 = gw.CrossSection(cell_sections=(cs2,))

        c2 = cell_with_xs(xs=xs2)

        assert c1 is not c2
        assert c1.name != c2.name


def test_cell_section_future_cell_cache() -> None:
    with gw.Layout():
        # Ensure async is True
        gw.config.async_cells = True
        # Use a fresh width to avoid any previous test cache
        sc1 = subcell(width=4.0)
        assert isinstance(sc1, FutureCell)

        cs1 = gw.CellSection(name="test", cell=sc1, periodicity=10.0)
        xs1 = gw.CrossSection(cell_sections=(cs1,))

        c1 = cell_with_xs(xs=xs1)

        # Identical FutureCell (re-calling subcell will return a FutureCell/Cell from cache)
        # In a new layout, subcell(width=4.0) will be a cache miss and return a new FutureCell
        sc2 = subcell(width=4.0)
        cs2 = gw.CellSection(name="test", cell=sc2, periodicity=10.0)
        xs2 = gw.CrossSection(cell_sections=(cs2,))

        c2 = cell_with_xs(xs=xs2)

        assert c1 is c2
        assert c1.name == c2.name


def test_cell_section_disk_cache(tmp_path: Path) -> None:
    # Use a temporary cache directory
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True

    # Clean cache before starting
    gw.clear_cache()

    with gw.Layout():
        # Use a fresh width
        sc = subcell(width=5.0)
        cs = gw.CellSection(name="periodic", cell=sc, periodicity=5.0)
        xs = gw.CrossSection(cell_sections=(cs,))

        c1 = cell_with_xs(xs=xs)
        name = c1.name

        # Verify file exists
        cache_file = test_cache_dir / f"{name}.oas"
        assert cache_file.exists()

    # New layout, should load from disk
    with gw.Layout():
        # Re-defining the same structure should hit disk cache
        sc_same = subcell(width=5.0)
        cs_same = gw.CellSection(name="periodic", cell=sc_same, periodicity=5.0)
        xs_same = gw.CrossSection(cell_sections=(cs_same,))

        c2 = cell_with_xs(xs=xs_same)

        assert c2.name == name

    gw.clear_cache()
