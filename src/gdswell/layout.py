# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import contextvars
import threading
from typing import TYPE_CHECKING, Any, ClassVar

import klayout.db as kdb_

if TYPE_CHECKING:
    from gdswell.cell import Cell
    from gdswell.future_cell import FutureCell
    from gdswell.layer import Layer

ACTIVE_LAYOUT: contextvars.ContextVar[Layout | None] = contextvars.ContextVar(
    "ACTIVE_LAYOUT", default=None
)


class Layout:
    """Wrapper around klayout.db.Layout"""

    _default_layout: ClassVar[Layout | None] = None
    _default_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_default(cls) -> Layout:
        """Get the global default layout, creating it if it doesn't exist."""
        if cls._default_layout is None:
            with cls._default_lock:
                if cls._default_layout is None:
                    # We instantiate the default layout and set it
                    # without triggering recursive get_default calls
                    new_layout = cls(name="default_global", set_as_default=False)
                    cls._default_layout = new_layout
                    return new_layout
        return cls._default_layout

    @classmethod
    def get_active(cls) -> Layout:
        """
        Get the currently active Layout from the context variable.
        If no context is active, return the global default.
        """
        active = ACTIVE_LAYOUT.get()
        if active is not None:
            return active
        return cls.get_default()

    def __init__(self, name: str = "main", set_as_default: bool = False):
        self.name = name
        self._kdb_layout = kdb_.Layout()
        self._tokens: contextvars.ContextVar[tuple[contextvars.Token[Layout | None], ...]] = (
            contextvars.ContextVar(f"layout_tokens_{id(self)}", default=())
        )
        self._cells: dict[int, Cell] = {}
        self._cache: dict[str, Cell | FutureCell] = {}
        self._lock = threading.RLock()
        self._pending_cells: set[FutureCell] = set()

        if set_as_default:
            Layout._default_layout = self

    def __enter__(self) -> Layout:
        token = ACTIVE_LAYOUT.set(self)
        self._tokens.set(self._tokens.get() + (token,))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        tokens = self._tokens.get()
        if tokens:
            token = tokens[-1]
            ACTIVE_LAYOUT.reset(token)
            self._tokens.set(tokens[:-1])

    def create_cell(self) -> Cell:
        """Create a new cell in this layout."""
        from gdswell.cell import Cell

        return Cell(layout=self)

    def cell(self, name: str) -> Cell:
        """Find a cell by name."""
        from gdswell.cell import Cell

        # 1. Check if it's already in the proxy/pending cache (for identity preservation)
        with self._lock:
            if name in self._cache:
                return self._cache[name]

        # 2. Fallback to standard lookup
        kdb_cell = self._kdb_layout.cell(name)
        if kdb_cell is None:
            raise KeyError(f"Cell '{name}' not found in layout '{self.name}'")

        # Cell._from_kdb_cell will register in self._cells and self._cache
        return Cell._from_kdb_cell(kdb_cell, layout=self)

    def layer(self, layer: Layer) -> int:
        """Get or create a layer index from a Layer object."""
        from gdswell.layer import Layer

        if not isinstance(layer, Layer):
            raise TypeError(f"layer must be a gdswell.layer.Layer instance, got {type(layer)}")

        layer_index, d = layer.as_tuple()
        info = kdb_.LayerInfo(layer_index, d)
        return self._kdb_layout.layer(info)

    def read(self, filename: str, prefix: str, cell_name: str | None = None) -> Cell:
        """
        Read an external layout file and return a specific cell (or the top cell).
        The imported cell hierarchy is prefixed to avoid name collisions.

        Args:
            filename: Path to the GDS/OASIS file.
            prefix: Prefix to apply to all imported cell names.
            cell_name: Optional name of the cell to retrieve. If None, the first top cell is used.

        Returns:
            A Cell wrapper for the imported cell.
        """
        # Append ':' as a separator that is not allowed in Python function names
        full_prefix = f"{prefix}:"
        return self._read_internal(filename, cell_name=cell_name, prefix=full_prefix)

    def _read_internal(self, filename: str, cell_name: str | None = None, prefix: str = "") -> Cell:
        """
        Internal read for trusted files (e.g., from cache where hashes were checked).
        """
        temp_ly = kdb_.Layout()
        temp_ly.read(filename)

        if cell_name is not None:
            kdb_cell = temp_ly.cell(cell_name)
            if kdb_cell is None:
                raise ValueError(f"Cell '{cell_name}' not found in {filename}")
        else:
            top_cells = temp_ly.top_cells()
            if not top_cells:
                raise ValueError(f"No cells found in {filename}")
            kdb_cell = top_cells[0]
            cell_name = kdb_cell.name

        from gdswell.cell import Cell

        # Import only the selected cell (and its hierarchy) into the current layout.
        Cell._from_kdb_cell(kdb_cell, layout=self, prefix=prefix)

        return self.cell(prefix + cell_name)

    def write(self, filename: str) -> None:
        """Save the layout to a GDS file with metadata properties enabled."""
        self.wait()
        options = kdb_.SaveLayoutOptions()
        options.write_context_info = True
        options.gds2_write_cell_properties = True
        options.gds2_write_file_properties = True
        self._kdb_layout.write(filename, options)

    def show(self, cell: Cell | None = None) -> None:
        """
        Stream the layout to Klive for live viewing in KLayout.
        If a cell is provided, it will be the shown top cell.
        """
        self.wait()
        from gdswell.klive import show

        if cell is not None:
            show(cell.kdb)
        else:
            top_cells = self._kdb_layout.top_cells()
            if not top_cells:
                raise ValueError(f"No cells found in layout '{self.name}'. Cannot stream to Klive.")
            show(top_cells[0])

    def _repr_png_(self) -> bytes:
        """Jupyter Notebook representation."""
        self.wait()
        # Find the first top cell to show
        top_cells = self._kdb_layout.top_cells()
        if not top_cells:
            raise ValueError(f"No cells found in layout '{self.name}'. Cannot generate image.")
        from gdswell.visualization import get_image_bytes

        return get_image_bytes(top_cells[0])

    @property
    def kdb(self) -> kdb_.Layout:
        """Access the underlying klayout.db.Layout"""
        return self._kdb_layout

    def wait(self) -> None:
        """Wait for all pending cells in this layout to complete."""
        # Ensure this layout is active during wait so that FutureCells
        # can safely import themselves into it.
        token = ACTIVE_LAYOUT.set(self)
        try:
            while True:
                with self._lock:
                    if not self._pending_cells:
                        break
                    p = next(iter(self._pending_cells))

                # Call _get_cell WITHOUT holding the layout lock
                p._get_cell()

                with self._lock:
                    self._pending_cells.discard(p)
        finally:
            ACTIVE_LAYOUT.reset(token)
