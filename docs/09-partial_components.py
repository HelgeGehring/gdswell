# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
"""
# Partial Components example

This example demonstrates how to use `functools.partial` with `@cell` decorated functions
to create partially specified components that can be passed as parameters to other components.
"""

import functools
from enum import Enum
from typing import Callable

from gdswell.cell import Cell
from gdswell.decorator import cell
from gdswell.layer import Layer
from gdswell.layout import Layout


# Define layers
class Layers(Layer, Enum):
    WG = (1, 0)
    SLAB = (2, 0)


@cell
def straight(width: float = 0.5, length: float = 10.0, layer: Layer = Layers.WG) -> Cell:
    """A simple straight waveguide."""
    c = Cell()
    c.add_polygon(
        [(0, -width / 2), (length, -width / 2), (length, width / 2), (0, width / 2)], layer=layer
    )
    return c


@cell
def component_with_sub(sub_comp_proto: Callable[..., Cell], spacing: float = 2.0) -> Cell:
    """
    A component that takes a 'protocol' or 'partial' for a sub-component
    and instantiates it multiple times with specific parameters.
    """
    c = Cell()

    # Instantiate the sub-component.
    # If sub_comp_proto is a partial, it will combine parameters.
    # If it's a function, it will be called with these parameters.
    c.add_ref(sub_comp_proto(width=0.4))
    c.add_ref(sub_comp_proto(width=0.6), origin=(0, spacing))

    return c


if __name__ == "__main__":
    with Layout(name="partial_example") as ly:
        # Option 1: Use functools.partial to pre-specify some arguments (e.g. length)
        # component_with_sub will provide 'width' later.
        partial_straight = functools.partial(straight, length=20.0)

        top = component_with_sub(sub_comp_proto=partial_straight)

        # Option 2: Pass the function directly if it can handle the arguments provided
        # by component_with_sub (in this case 'width').
        # Note: straight has a default for 'length', so it works!
        top_direct = component_with_sub(sub_comp_proto=straight)

        print(f"Top cell with partial: {top.name}")
        print(f"Top cell with direct function: {top_direct.name}")

        # You can also pass a partial that is already complete,
        # but it will be overridden or merged if those args are passed again.

        top.write("partial_example.gds")
        print("\nExported to partial_example.gds")
