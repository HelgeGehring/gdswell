# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from typing import TYPE_CHECKING

import klayout.db as kdb_

if TYPE_CHECKING:
    from gdswell.cell import Cell


from gdswell.port import Port


class Instance(Mapping[str, Port]):
    """Wrapper around klayout.db.Instance with port-aware feature."""

    def __init__(self, kdb_instance: kdb_.Instance, cell: Cell, name: str):
        self._kdb_instance = kdb_instance
        self._cell = cell
        self._name = name

    @property
    def dtrans(self) -> kdb_.DTrans:
        """The transformation of this instance."""
        return self._kdb_instance.dtrans

    @property
    def cell(self) -> Cell:
        """The cell this instance refers to."""
        return self._cell

    @property
    def name(self) -> str:
        """The name of this instance."""
        return self._name

    @property
    def kdb(self) -> kdb_.Instance:
        """Access the underlying klayout.db.Instance"""
        return self._kdb_instance

    @property
    def x(self) -> float:
        """The x-coordinate of this instance's origin."""
        return self.dtrans.disp.x

    @property
    def y(self) -> float:
        """The y-coordinate of this instance's origin."""
        return self.dtrans.disp.y

    @property
    def position(self) -> tuple[float, float]:
        """The (x, y) position of this instance's origin."""
        disp = self.dtrans.disp
        return (disp.x, disp.y)

    @property
    def ports(self) -> tuple[Port, ...]:
        """Access the transformed ports of this instance."""
        return tuple(self._transformed_ports.values())

    @cached_property
    def _transformed_ports(self) -> dict[str, Port]:
        """Internal cache for transformed ports."""
        trans = self.dtrans
        return {name: p.transformed(trans) for name, p in self._cell.ports.items()}

    def __getitem__(self, name: str) -> Port:
        """Access a port of the instanced cell, transformed to the parent coordinate system."""
        return self._transformed_ports[name]

    def values(self):
        return self._transformed_ports.values()

    def items(self):
        return self._transformed_ports.items()

    def __iter__(self):
        return iter(self._cell.ports)

    def __len__(self) -> int:
        return len(self._cell.ports)
