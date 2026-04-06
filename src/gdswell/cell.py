# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import abc
import types
import uuid
from collections import defaultdict
from collections.abc import Mapping
from itertools import count
from typing import TYPE_CHECKING, Any, Callable, Literal, Sequence

import klayout.db as kdb_

if TYPE_CHECKING:
    from gdswell.layer import Layer
    from gdswell.layout import Layout

from gdswell.instance import Instance
from gdswell.port import Port


class Cell(metaclass=abc.ABCMeta):
    """Wrapper around klayout.db.Cell"""

    validators: list[Callable[[Cell], Any]] = []

    def __init__(self, layout: Layout | None = None):
        """Initialize a new Cell wrapper."""
        from gdswell.layout import ACTIVE_LAYOUT, Layout

        self._layout = layout if layout is not None else ACTIVE_LAYOUT.get() or Layout.get_default()

        self._frozen = False
        self._info_data: dict[str, Any] = {}
        self._ports_data: dict[str, Port] = {}
        self._instances_data: list[Instance] | None = []
        self._name_counters: defaultdict[str, count] = defaultdict(count)
        self._function_name: str | None = None
        self._function_module: str | None = None

        cell_name = f"UnnamedCell_{uuid.uuid4().hex[:8]}"
        self._kdb_cell = self._layout.kdb.create_cell(cell_name)

        # Register this cell wrapper in the layout so identity is preserved
        with self._layout._lock:
            self._layout._cells[self._kdb_cell.cell_index()] = self
            if self.name and not self.name.startswith("UnnamedCell_"):
                self._layout._cache[self.name] = self

    @classmethod
    def _from_kdb_cell(
        cls, kdb_cell: kdb_.Cell, layout: Layout | None = None, prefix: str = ""
    ) -> Cell:
        """
        Create a Cell wrapper from a klayout.db.Cell.
        If the kdb_cell is from a different layout, it is copied into the target layout.
        """
        from gdswell.layout import ACTIVE_LAYOUT, Layout
        from gdswell.persistence import copy_kdb_cell, restore_cell_metadata

        ly = layout if layout is not None else ACTIVE_LAYOUT.get() or Layout.get_default()
        if not isinstance(kdb_cell, kdb_.Cell):
            raise TypeError("kdb_cell must be an instance of klayout.db.Cell")

        # Identity preservation: Check if this kdb_cell already has a wrapper in target layout
        if kdb_cell.layout() == ly.kdb:
            cell_index = kdb_cell.cell_index()
            if cell_index in ly._cells:
                return ly._cells[cell_index]
        else:
            # It's from a different layout. Get or create the local version.
            kdb_cell = copy_kdb_cell(kdb_cell, ly.kdb, prefix=prefix)
            # Check if THAT local cell already has a wrapper
            cell_index = kdb_cell.cell_index()
            if cell_index in ly._cells:
                return ly._cells[cell_index]

        # Use __new__ to avoid double initialization if we were to call cls()
        instance = cls.__new__(cls)
        instance._layout = ly
        instance._frozen = True
        instance._info_data = {}
        instance._ports_data = {}
        instance._instances_data = None  # Lazy population
        instance._name_counters = defaultdict(count)
        instance._function_name = None
        instance._function_module = None
        instance._kdb_cell = kdb_cell

        # Restore info and ports from metadata if they exist
        restore_cell_metadata(instance)

        # Register this cell wrapper in the layout so identity is preserved
        with ly._lock:
            ly._cells[instance._kdb_cell.cell_index()] = instance
            if instance.name and instance.name not in ly._cache:
                ly._cache[instance.name] = instance
        return instance

    @property
    def name(self) -> str:
        """The name of the cell."""
        return self._kdb_cell.name

    @property
    def function_name(self) -> str | None:
        """The name of the function that generated this cell, if any."""
        return self._function_name

    @property
    def function_module(self) -> str | None:
        """The module of the function that generated this cell, if any."""
        return self._function_module

    def __repr__(self) -> str:
        return f"Cell(name='{self.name}')"

    def __hash__(self) -> int:
        return hash(self.name)

    @property
    def layout(self) -> Layout:
        """The layout this cell belongs to."""
        return self._layout

    @property
    def frozen(self) -> bool:
        """Whether the cell is frozen and cannot be modified."""
        return self._frozen

    def freeze(self) -> None:
        """Freeze the cell to prevent further modifications."""
        if self._frozen:
            raise RuntimeError(f"Cell '{self.name}' is already frozen.")

        if self.name.startswith("UnnamedCell_"):
            raise RuntimeError(
                f"Cannot freeze unnamed cell '{self.name}'. "
                "Cells must be explicitly named by the @cell decorator before freezing."
            )

        # Store metadata before freezing
        from gdswell.persistence import save_cell_metadata

        save_cell_metadata(self)

        self._frozen = True

        # Run registered validators (e.g., netlist extraction)
        for validator in Cell.validators:
            validator(self)

    @property
    def info(self) -> Mapping[str, Any]:
        """User metadata dictionary for this cell."""
        return types.MappingProxyType(self._info_data)

    def add_info(self, key: str, value: Any) -> None:
        """Add metadata info to the cell."""
        self._check_frozen()
        self._info_data[key] = value

    def add_port(self, port: Port) -> None:
        """Add a port to the cell."""
        self._check_frozen()
        if port.name in self._ports_data:
            raise ValueError(f"Port '{port.name}' already exists in cell '{self.name}'.")
        self._ports_data[port.name] = port

    def __getitem__(self, name: str) -> Port:
        """Access a port by name."""
        if name not in self._ports_data:
            raise KeyError(
                f"Port '{name}' not found in cell '{self.name}'. "
                f"Available ports: {list(self._ports_data.keys())}"
            )
        return self._ports_data[name]

    @property
    def ports(self) -> Mapping[str, Port]:
        """Dictionary of ports in this cell."""
        return types.MappingProxyType(self._ports_data)

    @property
    def instances(self) -> Sequence[Instance]:
        """Sequence of instances in this cell."""
        if self._instances_data is None:
            # Lazy population from KLayout
            self._instances_data = []
            # We need to ensure name counters are consistent if we already have some names?
            # Actually, for a cell loaded from KLayout, name counters should start fresh.
            for kdb_inst in self._kdb_cell.each_inst():
                sub_kdb_cell = self.layout.kdb.cell(kdb_inst.cell_index)
                sub_cell = Cell._from_kdb_cell(sub_kdb_cell, layout=self.layout)
                inst_name = f"{sub_cell.name}_{next(self._name_counters[sub_cell.name])}"
                self._instances_data.append(Instance(kdb_inst, sub_cell, name=inst_name))

        return tuple(self._instances_data)

    def _check_frozen(self) -> None:
        """Internal helper to raise an error if the cell is frozen."""
        if self._frozen:
            raise RuntimeError(f"Cell '{self.name}' is frozen and cannot be modified.")

    def layer(self, layer: Layer) -> int:
        """Get or create a layer index in this cell's layout."""
        return self._layout.layer(layer)

    def bbox(self, layer: Layer | None = None) -> kdb_.DBox:
        """
        Return the bounding box of the cell in microns.
        If layer is specified, return the bbox for that layer only.
        """
        if layer is not None:
            layer_index = self.layer(layer)
            return self._kdb_cell.dbbox(layer_index)
        return self._kdb_cell.dbbox()

    def is_empty(self, layer: Layer | None = None) -> bool:
        """
        Return True if the cell is empty.
        If layer is specified, return True if that layer is empty.
        """
        if layer is not None:
            layer_index = self.layer(layer)
            return self._kdb_cell.shapes(layer_index).is_empty()
        return self._kdb_cell.is_empty()

    def add_polygon(self, pts: list[tuple[float, float]], layer: Layer) -> kdb_.Shape:
        """
        Add a polygon to the cell on the specified layer.
        Points should be provided in micron units.
        """
        self._check_frozen()
        layer_index = self.layer(layer)
        dpts = [kdb_.DPoint(x, y) for x, y in pts]
        dpoly = kdb_.DPolygon(dpts)
        return self._kdb_cell.shapes(layer_index).insert(dpoly)

    def add_label(
        self,
        text: str,
        position: tuple[float, float],
        layer: Layer,
        rotation: Literal[0, 90, 180, 270] = 0,
    ) -> kdb_.Shape:
        """
        Add a GDSII label (text object) to the cell.

        Args:
            text: The text content of the label.
            position: The (x, y) position of the label in microns.
            layer: The layer to place the label on.
            rotation: Angle in degrees (0, 90, 180, or 270).
        """
        self._check_frozen()
        layer_index = self.layer(layer)
        x, y = position
        rot_index = {0: 0, 90: 1, 180: 2, 270: 3}[rotation]
        trans = kdb_.DTrans(rot_index, False, kdb_.DVector(x, y))
        dtext = kdb_.DText(text, trans)
        return self._kdb_cell.shapes(layer_index).insert(dtext)

    def add_region(self, region: kdb_.Region, layer: Layer) -> None:
        """
        Add a Region containing multiple shapes to the cell on the specified layer.
        """
        self._check_frozen()
        layer_index = self.layer(layer)
        self._kdb_cell.shapes(layer_index).insert(region)

    def add_ref(
        self,
        cell: Cell,
        origin: tuple[float, float] = (0.0, 0.0),
        rotation: Literal[0, 90, 180, 270] = 0,
        mirror: bool = False,
    ) -> Instance:
        """
        Add a reference (instance) to another cell.
        Returns an Instance wrapper.
        """
        self._check_frozen()

        if not cell.frozen:
            raise RuntimeError(
                f"Cannot add reference to cell '{cell.name}' because it is not frozen. "
                f"Cells must be frozen before they can be added to other cells."
            )

        if cell.layout is not self.layout:
            # Automatic import if cell is from a different layout (common with async cells)
            cell = Cell._from_kdb_cell(cell.kdb, layout=self.layout)

        if cell.layout is not self.layout:
            raise ValueError("Cannot instantiate a cell from a different layout")

        if rotation % 90 != 0:
            raise ValueError(f"Rotation must be a multiple of 90 degrees, got {rotation}")

        x, y = origin
        # Create a Manhattan transformation (DTrans)
        final_trans = kdb_.DTrans(rotation // 90, mirror, x, y)
        dinst = kdb_.DCellInstArray(cell.kdb.cell_index(), final_trans)
        kdb_inst = self._kdb_cell.insert(dinst)
        inst_name = f"{cell.name}_{next(self._name_counters[cell.name])}"
        inst = Instance(kdb_inst, cell, name=inst_name)
        if self._instances_data is None:
            self._instances_data = []
        self._instances_data.append(inst)

        return inst

    def add_ref_connected(
        self,
        cell: Cell,
        port_name: str,
        target_port: Port,
        ignore_xs_mismatch: bool = False,
        mirror: bool = False,
    ) -> Instance:
        """
        Add a reference to 'cell' such that its port 'port_name' connects to 'target_port'.
        'target_port' is expected to be a Port object already transformed into this cell's
        coordinate system if it originates from a sub-instance.
        """
        # 1. Get the source port
        source_port = cell[port_name]

        # 2. Check cross-section matching
        if not ignore_xs_mismatch:
            if source_port.cross_section != target_port.cross_section:
                raise ValueError(
                    f"Cross-section mismatch when connecting '{port_name}' of cell '{cell.name}' "
                    f"to target port '{target_port.name}'.\n"
                    f"Source XS: {source_port.cross_section}\n"
                    f"Target XS: {target_port.cross_section}"
                )

        # 3. Calculate transformation
        rot = (target_port.angle + 180 - (-1 if mirror else 1) * source_port.angle) % 360

        if rot % 90 != 0:
            raise ValueError(
                f"Connection results in non-90 degree rotation ({rot}). "
                "Only Manhattan (90 degree) connections are supported."
            )

        # Calculate where the source port WOULD be if we only applied rotation/mirroring at origin
        # (Using Port.transformed for cleaner geometric calculation)
        temp_trans = kdb_.DTrans(rot // 90, mirror, 0, 0)
        transformed_source_p = source_port.transformed(temp_trans)
        tsx, tsy = transformed_source_p.position

        # Translation: target_pos - transformed_source_pos
        tx = target_port.position[0] - tsx
        ty = target_port.position[1] - tsy

        return self.add_ref(cell, origin=(tx, ty), rotation=rot, mirror=mirror)

    def to_image(self, filename: str, width: int = 800, height: int = 600) -> None:
        """
        Export the cell's layout as a PNG image.

        Args:
            filename: The name of the file to save the image to (should end in .png).
            width: The width of the image in pixels.
            height: The height of the image in pixels.
        """
        self.layout.wait()
        from gdswell.visualization import export_image

        export_image(self.kdb, filename, width, height)

    def _repr_png_(self) -> bytes:
        """Jupyter Notebook representation."""
        self.layout.wait()
        from gdswell.visualization import get_image_bytes

        return get_image_bytes(self.kdb)

    def show(self) -> None:
        """Stream the cell to Klive for live viewing in KLayout."""
        self._layout.show(self)

    def write(self, filename: str) -> None:
        """Save the layout this cell belongs to as a GDS file."""
        self._layout.write(filename)

    @property
    def kdb(self) -> kdb_.Cell:
        """Access the underlying klayout.db.Cell"""
        return self._kdb_cell
