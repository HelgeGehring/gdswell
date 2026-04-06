# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal

import klayout.db as kdb

if TYPE_CHECKING:
    from gdswell.cell import Cell
    from gdswell.cross_section import CrossSection


import math


@dataclass(frozen=True)
class Port:
    """A port is a reference point in a cell with a position and orientation."""

    name: str
    position: tuple[float, float]
    angle: Literal[0, 90, 180, 270]  # angle in degrees, pointing outwards
    cross_section: CrossSection
    cells: dict[str, Cell] = field(default_factory=dict)

    @property
    def x(self) -> float:
        return self.position[0]

    @property
    def y(self) -> float:
        return self.position[1]

    def __post_init__(self) -> None:
        if self.angle % 90 != 0:
            raise ValueError(f"Port angle must be a multiple of 90 degrees, got {self.angle}")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Port):
            return False
        return (
            self.cross_section == other.cross_section
            and (self.angle == other.angle)
            and math.isclose(self.position[0], other.position[0], abs_tol=1e-6)
            and math.isclose(self.position[1], other.position[1], abs_tol=1e-6)
        )

    @cached_property
    def _hash_string(self) -> str:
        """Cached deterministic string for hashing."""
        # Quantize position to match 1e-6 tolerance in __eq__ as closely as possible
        x_str = f"{self.position[0]:.6f}"
        y_str = f"{self.position[1]:.6f}"
        return f"Port({x_str},{y_str},{self.angle},{self.cross_section._hash_string})"

    def __hash__(self) -> int:
        return hash(self._hash_string)

    def connects_to(self, other: Port) -> bool:
        """Returns True if this port connects to another port spatially."""
        # A connection requires exact spatial matching and opposite orientations (180 deg)
        if (self.angle + 180) % 360 != other.angle:
            return False
        if self.cross_section != other.cross_section:
            return False
        return math.isclose(self.position[0], other.position[0], abs_tol=1e-6) and math.isclose(
            self.position[1], other.position[1], abs_tol=1e-6
        )

    def transformed(self, transformation: kdb.DTrans) -> Port:
        """Returns a new Port with the transformation applied."""
        x, y = self.position
        dpt = kdb.DPoint(x, y)
        trans_dpt = transformation * dpt

        # Transform the angle
        # For DTrans, .angle is the rotation index (0, 1, 2, 3)
        rot_deg = transformation.angle * 90
        new_angle = ((-self.angle if transformation.is_mirror() else self.angle) + rot_deg) % 360

        return replace(
            self, position=(trans_dpt.x, trans_dpt.y), angle=new_angle, cells=self.cells.copy()
        )

    def renamed(self, new_name: str) -> Port:
        """Returns a new Port with a different name."""
        return replace(self, name=new_name)

    def with_cross_section(self, cross_section: CrossSection) -> Port:
        """Returns a new Port with a different cross-section."""
        return replace(self, cross_section=cross_section)

    def flipped(self) -> Port:
        """Returns a new Port with the angle flipped by 180 degrees."""
        return replace(self, angle=int((self.angle + 180) % 360))

    def with_cell(self, name: str, cell: Cell) -> Port:
        """Returns a new Port with an additional geometry cell attached."""
        new_cells = self.cells.copy()
        new_cells[name] = cell
        return replace(self, cells=new_cells)

    def to_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable dictionary representation of the port."""
        d: dict[str, Any] = {
            "name": self.name,
            "position": self.position,
            "angle": self.angle,
        }
        if self.cross_section is not None:
            d["cross_section"] = self.cross_section.to_dict()
        if self.cells:
            d["cells"] = {name: cell.name for name, cell in self.cells.items()}
        return d
