# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import functools
import json
from enum import Enum
from typing import Any, Callable, cast

import gdswell as gw


class Pdk(gw.Layer, Enum):
    WG = (1, 0)


@gw.cell
def my_rectangle(width: float = 10.0, height: float = 5.0) -> gw.Cell:
    layout = gw.Layout.get_active()
    # The cell caching decorator automatically renames it, so we can pass anything here initially
    c = layout.create_cell()
    c.add_polygon([(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)], layer=Pdk.WG)
    return c


def test_cell_decorator_caching() -> None:
    layout = gw.Layout("test_decorator_layout")

    with layout:
        # Create identical cells
        c1 = my_rectangle(width=20.0, height=10.0)
        c2 = my_rectangle(width=20.0, height=10.0)

        # They should be literally the exact same instance in memory
        assert c1 is c2
        assert c1.name.startswith("my_rectangle_")
        # Suffix is 17 chars (8 char param hash + 1 char separator + 8 char source hash)
        expected_len = len("my_rectangle_") + 17
        assert len(c1.name) == expected_len

        # Verify internal properties
        assert c1.kdb.meta_info("function_name").value == "my_rectangle"

        # The params are now stored as a JSON string
        params = json.loads(c1.kdb.meta_info("params").value)
        assert params["height"] == "10.0"
        assert params["width"] == "20.0"

        # Create a differently parameterized cell
        c3 = my_rectangle(width=15.0, height=10.0)

        # Should be a separate instance with a different name
        assert c3 is not c1
        assert c3.name.startswith("my_rectangle_")
        assert len(c3.name) == len("my_rectangle_") + 17


def test_cell_decorator_default_arguments() -> None:
    layout = gw.Layout("test_decorator_defaults")

    with layout:
        # One with implicit defaults, one with explicit defaults matching the signature
        c1 = my_rectangle()
        c2 = my_rectangle(width=10.0, height=5.0)

        # Because we bind and apply_defaults, they should hit the same cache entry
        assert c1 is c2
        assert c1.name.startswith("my_rectangle_")
        assert len(c1.name) == len("my_rectangle_") + 17


@gw.cell
def invalid_cell(points: list[Any]) -> gw.Cell:
    layout = gw.Layout.get_active()
    return layout.create_cell()


def test_cell_decorator_unhashable_args() -> None:
    layout = gw.Layout("test_unhashable")

    with layout:
        try:
            invalid_cell(cast(list[Any], set([1, 2, 3])))
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "must be hashable" in str(e) or "unhashable" in str(e)


if __name__ == "__main__":
    test_cell_decorator_caching()
    test_cell_decorator_default_arguments()
    test_cell_decorator_unhashable_args()
    print("Tests passed")


@gw.cell
def inner_cell(x: int = 1, y: int = 2) -> gw.Cell:
    layout = gw.Layout.get_active()
    c = layout.create_cell()
    return c


@gw.cell
def outer_cell(inner_func: Callable[[], gw.Cell] = inner_cell) -> gw.Cell:
    layout = gw.Layout.get_active()
    c = layout.create_cell()
    c.add_ref(inner_func(), origin=(0, 0))
    return c


def test_cell_decorator_function_args() -> None:
    layout = gw.Layout("test_func_args")

    with layout:
        # Default
        c1 = outer_cell()
        # Explicit passing identical function
        c2 = outer_cell(inner_func=inner_cell)
        assert c1 is c2
        assert c1.name == c2.name


def test_cell_decorator_partial_args() -> None:
    layout = gw.Layout("test_partial_args")

    with layout:
        # Pass a partial with no kwargs (should be same as inner_cell default?)
        # Wait, a partial with no kwargs might not hash exactly the same as inner_cell
        # because it evaluates to inner_cell(x=1, y=2) and inner_cell is inner_cell(x=1, y=2)
        # However, due to function signature binding, they will both
        # serialize to inner_cell(x=1, y=2)
        p1 = functools.partial(inner_cell)
        c1 = outer_cell(inner_func=p1)

        # They should match the original because defaults are applied correctly
        c_orig = outer_cell()
        assert c1 is c_orig

        # Now pass a partial with a distinct arg
        p2 = functools.partial(inner_cell, x=10)
        c2 = outer_cell(inner_func=p2)

        # Test nested partial
        p3 = functools.partial(functools.partial(inner_cell, y=20), x=10)
        c3 = outer_cell(inner_func=p3)

        assert c2 is not c_orig if "c_orig" in locals() else c1
        assert c3 is not c2

        # Another matching set
        p3_alt = functools.partial(p2, y=20)
        c3_alt = outer_cell(inner_func=p3_alt)

        assert c3 is c3_alt


if __name__ == "__main__":
    test_cell_decorator_function_args()
    test_cell_decorator_partial_args()
