# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

import gdswell as gw


@gw.cell
def _cell_empty() -> gw.Cell:
    return gw.Cell()


def test_add_ref_unfrozen_raises():
    with gw.Layout():
        c1 = gw.Cell()
        c2 = gw.Cell()

        with pytest.raises(RuntimeError, match="is not frozen"):
            c1.add_ref(c2)


def test_add_ref_connected_unfrozen_raises():
    xs = gw.CrossSection(())
    with gw.Layout():
        c1 = gw.Cell()
        c2 = gw.Cell()
        p2 = gw.Port(name="p1", position=(0, 0), angle=0, cross_section=xs)
        c2.add_port(p2)

        target_port = gw.Port(name="tp", position=(10, 10), angle=180, cross_section=xs)

        with pytest.raises(RuntimeError, match="is not frozen"):
            c1.add_ref_connected(c2, "p1", target_port)


def test_add_ref_frozen_works():
    with gw.Layout():
        c1 = gw.Cell()
        c2 = _cell_empty()

        # Should work
        c1.add_ref(c2)


def test_add_ref_decorated_works():
    with gw.Layout():
        c1 = gw.Cell()
        c2 = _cell_empty()

        # Should work because @cell freezes the cell
        c1.add_ref(c2)


def test_add_ref_cross_layout_frozen_works():
    with gw.Layout(name="ly1"):
        c_src = _cell_empty()
        src_name = c_src.name

    with gw.Layout(name="ly2") as ly2:
        c_dst = gw.Cell()
        # Should work: it will be automatically imported and frozen in ly2
        c_dst.add_ref(c_src)
        # Check that a cell with the same name was added as a reference
        called_names = [ly2.kdb.cell(idx).name for idx in c_dst.kdb.called_cells()]
        assert src_name in called_names


def test_add_ref_cross_layout_unfrozen_raises():
    with gw.Layout(name="ly1"):
        c_src = gw.Cell()
        # NOT frozen

    with gw.Layout(name="ly2"):
        c_dst = gw.Cell()
        with pytest.raises(RuntimeError, match="is not frozen"):
            c_dst.add_ref(c_src)
