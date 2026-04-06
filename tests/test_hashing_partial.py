# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import functools
from typing import Any

from gdswell.cell import Cell
from gdswell.decorator import cell
from gdswell.layout import Layout


@cell
def component_a(x: float, y: float, z: float = 3.0) -> Cell:
    c = Cell()
    c.add_info("x", x)
    c.add_info("y", y)
    c.add_info("z", z)
    return c


@cell
def component_b(sub_comp: Any) -> Cell:
    c = Cell()
    # In a real case, we might call sub_comp() here
    return c


def test_partial_hashing():
    with Layout():
        # 1. Basic partial
        p1 = functools.partial(component_a, x=1.0)
        b1 = component_b(sub_comp=p1)

        # 2. Same partial parameters should yield same cell name for component_b
        p2 = functools.partial(component_a, x=1.0)
        b2 = component_b(sub_comp=p2)
        assert b1.name == b2.name

        # 3. Different partial parameters should yield different cell name
        p3 = functools.partial(component_a, x=2.0)
        b3 = component_b(sub_comp=p3)
        assert b1.name != b3.name

        # 4. Nested partials
        p4 = functools.partial(p1, y=2.0)
        b4 = component_b(sub_comp=p4)

        p5 = functools.partial(component_a, x=1.0, y=2.0)
        b5 = component_b(sub_comp=p5)
        assert b4.name == b5.name


def test_complete_partial():
    with Layout():
        # A partial that has all required arguments
        p = functools.partial(component_a, x=1.0, y=2.0)
        # component_b should still be able to hash it
        b = component_b(sub_comp=p)
        assert "component_b_" in b.name


def test_partial_vs_full_cell():
    with Layout():
        # A partial that is complete should still hash differently than the realized cell
        # because one is a partial and the other is a Cell object.
        p = functools.partial(component_a, x=1.0, y=2.0, z=3.0)
        c = component_a(x=1.0, y=2.0, z=3.0)

        b_p = component_b(sub_comp=p)
        b_c = component_b(sub_comp=c)

        # They should be different because 'p' is a partial (uses suffix _partial in hash)
        # and 'c' is a realized Cell (uses its name).
        assert b_p.name != b_c.name


@cell
def component_c(sub_comp_proto: Any, y_val: float) -> Cell:
    c = Cell()
    # Initialize the partial here
    sub_cell = sub_comp_proto(y=y_val)
    c.add_ref(sub_cell)
    return c


@cell
def component_d(y: float) -> Cell:
    c = Cell()
    c.add_info("y", y)
    return c


def test_initialize_partial_in_cell():
    with Layout():
        p = functools.partial(component_a, x=1.0)

        # This should work and result in a cell that contains a component_a(x=1.0, y=2.0)
        c_top = component_c(sub_comp_proto=p, y_val=2.0)

        assert len(c_top.instances) == 1
        inst = c_top.instances[0]
        assert "component_a" in inst.cell.name

        # Verify identity preservation
        c_top_2 = component_c(sub_comp_proto=p, y_val=2.0)
        assert c_top is c_top_2
        assert c_top.instances[0].cell is inst.cell


def test_direct_function_parameter():
    with Layout():
        # Passing component_d directly without functools.partial
        # component_c will call it with y=5.0
        c_top_d = component_c(sub_comp_proto=component_d, y_val=5.0)
        assert len(c_top_d.instances) == 1
        assert "component_d" in c_top_d.instances[0].cell.name
