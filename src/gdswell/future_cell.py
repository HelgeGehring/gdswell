# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gdswell.cell import Cell

if TYPE_CHECKING:
    from gdswell.layout import Layout
    from gdswell.port import Port


# Pre-calculate set of attributes that should NOT be delegated to the realized cell.
_FUTURE_CELL_ATTRS = frozenset(
    (
        "_future",
        "_cell",
        "_get_cell",
        "__class__",
        "__repr__",
        "__hash__",
        "__eq__",
        "__ne__",
        "__dir__",
        "_repr_png_",
        "_unique_name",
        "_home_layout",
    )
)


class FutureCell(Cell):
    """A proxy for a Cell that is being generated in a background thread."""

    def __init__(self, future_or_cell: Any, home_layout: Layout, unique_name: str):
        # We don't call super().__init__ because that would create a kdb cell
        # in the current layout context immediately.
        if isinstance(future_or_cell, Cell):
            object.__setattr__(self, "_future", None)
            object.__setattr__(self, "_cell", future_or_cell)
        else:
            object.__setattr__(self, "_future", future_or_cell)
            object.__setattr__(self, "_cell", None)

        object.__setattr__(self, "_home_layout", home_layout)
        object.__setattr__(self, "_unique_name", unique_name)

    def _get_cell(self) -> Cell:
        cell = cast(Cell, object.__getattribute__(self, "_cell"))
        if cell is not None:
            return cell

        future = object.__getattribute__(self, "_future")
        if future is None:
            raise RuntimeError("FutureCell has neither cell nor future")

        home_ly = object.__getattribute__(self, "_home_layout")
        raw_cell = cast(Cell, future.result())

        # If we are currently in the home layout's thread/context,
        # we can safely import the cell into it and cache it.
        from gdswell.layout import ACTIVE_LAYOUT

        if ACTIVE_LAYOUT.get() is home_ly:
            cell = Cell._from_kdb_cell(raw_cell.kdb, layout=home_ly)
            object.__setattr__(self, "_cell", cell)

            # Remove from layout's pending set, but KEEP in spectator's PENDING_CACHE
            # to maintain identity preservation for future @cell calls.
            home_ly._pending_cells.discard(self)

            return cell

        # If we are in another context (e.g. another thread), return the raw cell.
        # The caller (like add_ref) will handle importing it into their own layout.
        return raw_cell

    def __getattribute__(self, name: str) -> Any:
        # Fast path for FutureCell's own attributes
        if name in _FUTURE_CELL_ATTRS:
            return object.__getattribute__(self, name)

        # Delegate everything else to the realized cell
        # We inline _get_cell's common case here for speed
        cell = cast(Cell, object.__getattribute__(self, "_cell"))
        if cell is not None:
            return getattr(cell, name)

        return getattr(self._get_cell(), name)

    def __getitem__(self, name: str) -> Port:
        # Inline common case
        cell = cast(Cell, object.__getattribute__(self, "_cell"))
        if cell is not None:
            return cell[name]
        return self._get_cell()[name]

    def __hash__(self) -> int:
        return hash(
            (
                id(object.__getattribute__(self, "_home_layout")),
                object.__getattribute__(self, "_unique_name"),
            )
        )

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FutureCell):
            return object.__getattribute__(self, "_home_layout") is object.__getattribute__(
                other, "_home_layout"
            ) and object.__getattribute__(self, "_unique_name") == object.__getattribute__(
                other, "_unique_name"
            )
        # Access real cell for comparison with other Cell objects
        return bool(self._get_cell() == other)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __dir__(self) -> list[str]:
        """Support autocompletion by merging FutureCell and realized Cell attributes."""
        own_attrs = set(super().__dir__())
        try:
            cell_attrs = set(dir(self._get_cell()))
            return sorted(own_attrs | cell_attrs)
        except Exception:
            return sorted(own_attrs)

    def _repr_png_(self) -> bytes:
        """Jupyter Notebook representation."""
        return self._get_cell()._repr_png_()

    def __repr__(self) -> str:
        cell = object.__getattribute__(self, "_cell")
        if cell:
            return repr(cell)
        future = object.__getattribute__(self, "_future")
        return f"FutureCell(running={future.running()})"


Cell.register(FutureCell)
