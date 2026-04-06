# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from gdswell.cell import Cell
from gdswell.components.straight import straight
from gdswell.cross_section import CrossSectionCallable
from gdswell.decorator import cell


@cell
def coupler(
    cross_section: CrossSectionCallable, length: float, gap: float, npoints: int = 2
) -> Cell:
    """
    Create a directional coupler component.

    Args:
        cross_section: The cross-section to use for both waveguides.
        length: The length of the coupling region.
        gap: The distance between the centers of the two waveguides.
        npoints: Number of points along the length for evaluation.
    """
    c = Cell()

    # Create the straight waveguide component
    s = straight(cross_section=cross_section, length=length, npoints=npoints)

    # Add two instances of the straight waveguide at the specified gap
    inst_top = c.add_ref(s, origin=(0.0, gap / 2))
    inst_bottom = c.add_ref(s, origin=(0.0, -gap / 2))

    # Promote and rename ports
    c.add_port(inst_top["0"].renamed("w0"))
    c.add_port(inst_top["1"].renamed("e0"))
    c.add_port(inst_bottom["0"].renamed("w1"))
    c.add_port(inst_bottom["1"].renamed("e1"))

    c.add_info("length", length)

    return c
