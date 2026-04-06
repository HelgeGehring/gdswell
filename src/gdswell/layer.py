# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import klayout.db as kdb

from gdswell.decorator import cell

if TYPE_CHECKING:
    from gdswell.cell import Cell


class LayerBase:
    """Base class for layers and layer operations."""

    @property
    def _hash_string(self) -> str:
        """Deterministic string for hashing."""
        raise NotImplementedError()

    def get_shapes(self, cell: Cell) -> kdb.Region:
        """Returns a kdb.Region containing the shapes of this layer in the cell."""
        raise NotImplementedError()

    def __add__(self, other: LayerBase) -> LayerUnion:
        return LayerUnion(self, other)

    def __or__(self, other: LayerBase) -> LayerUnion:
        return LayerUnion(self, other)

    def __sub__(self, other: LayerBase) -> LayerDifference:
        return LayerDifference(self, other)

    def __and__(self, other: LayerBase) -> LayerIntersection:
        return LayerIntersection(self, other)

    def __xor__(self, other: LayerBase) -> LayerXor:
        return LayerXor(self, other)

    def size(self, dx: float, dy: float | None = None) -> LayerSize:
        """Enlarge or shrink the layer's shapes by the given distance."""
        return LayerSize(self, dx, dy)

    def transformed(self, t: kdb.Trans | kdb.DTrans) -> LayerTransformed:
        """Apply a transformation to the layer's shapes."""
        return LayerTransformed(self, t)

    def bbox(self) -> LayerBBox:
        """Return the bounding box of the layer's shapes."""
        return LayerBBox(self)

    def round_corners(self, radius1: float, radius2: float, segments: int) -> LayerRounded:
        """
        Round the corners of the shapes.
        Signature: round_corners(radius1, radius2, segments)
        """
        return LayerRounded(self, radius1, float(radius2), segments)

    def interacting(self, other: LayerBase) -> LayerInteracting:
        """Select shapes that touch or overlap with 'other'."""
        return LayerInteracting(self, other)

    def not_interacting(self, other: LayerBase) -> LayerNotInteracting:
        """Select shapes that do NOT touch or overlap with 'other'."""
        return LayerNotInteracting(self, other)

    def inside(self, other: LayerBase) -> LayerInside:
        """Select shapes that are completely inside 'other'."""
        return LayerInside(self, other)

    def outside(self, other: LayerBase) -> LayerOutside:
        """Select shapes that are completely outside 'other'."""
        return LayerOutside(self, other)

    def overlapping(self, other: LayerBase, min_count: int = 1) -> LayerOverlapping:
        """Select shapes that overlap with at least 'min_count' shapes of 'other'."""
        return LayerOverlapping(self, other, min_count)

    def onto(self, target: Layer) -> LayerMapping:
        """Map this geometrical recipe onto a specific target layer."""
        return LayerMapping({target: self})


@dataclass(frozen=True, repr=False)
class Layer(LayerBase):
    """
    Base class for defining GDS layers.
    Can be used directly or as a mixin for Enums.

    Example:
        class MyLayers(Layer, Enum):
            WG = (1, 0)
            CLADDING = (2, 0)
    """

    layer: int
    datatype: int

    @property
    def _hash_string(self) -> str:
        return f"L({self.layer},{self.datatype})"

    def to_dict(self) -> dict[str, Any]:
        return {"__type__": "Layer", "layer": self.layer, "datatype": self.datatype}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | tuple[int, int]) -> Layer:
        if isinstance(data, (tuple, list)):
            return cls(int(data[0]), int(data[1]))
        return cls(int(data["layer"]), int(data["datatype"]))

    def as_tuple(self) -> tuple[int, int]:
        return (self.layer, self.datatype)

    def get_shapes(self, cell: Cell) -> kdb.Region:
        layer_index = cell.layer(self)
        return kdb.Region(cell.kdb.begin_shapes_rec(layer_index))

    def __eq__(self, other: object) -> bool:
        """Equality only depends on layer and datatype."""
        if isinstance(other, Layer):
            return self.layer == other.layer and self.datatype == other.datatype
        return False

    def __hash__(self) -> int:
        return hash((self.layer, self.datatype))

    def __repr__(self) -> str:
        # If it's an Enum member, it will have a name attribute
        if hasattr(self, "base_name"):
            return f"Layer.{self.base_name}({self.layer}, {self.datatype})"
        if hasattr(self, "name"):
            return f"Layer.{self.name}({self.layer}, {self.datatype})"
        return f"Layer({self.layer}, {self.datatype})"


@dataclass(frozen=True, repr=False)
class AllLayers(LayerBase):
    """Operation that selects shapes from all layers in the cell."""

    def get_shapes(self, cell: Cell) -> kdb.Region:
        region = kdb.Region()
        # Recursive insertion from all layers
        for layer_index in cell.layout.kdb.layer_indexes():
            region.insert(cell.kdb.begin_shapes_rec(layer_index))
        return region

    @property
    def _hash_string(self) -> str:
        return "AllLayers()"

    def __repr__(self) -> str:
        return "AllLayers()"


@dataclass(frozen=True)
class LayerMapping:
    mappings: dict[Layer, LayerBase]

    def __add__(self, other: LayerMapping) -> LayerMapping:
        new_mappings = self.mappings.copy()
        for target, source in other.mappings.items():
            if target in new_mappings:
                new_mappings[target] = new_mappings[target] + source
            else:
                new_mappings[target] = source
        return LayerMapping(new_mappings)

    def apply(self, cell: Cell) -> Cell:
        """Apply the mappings in-place to the provided cell."""
        for target, source in self.mappings.items():
            region = source.get_shapes(cell)
            cell.add_region(region, target)
        return cell

    def __call__(self, cell: Cell) -> Cell:
        """Create a new decorated cell with the mappings applied."""
        return _apply_layer_mapping(cell, self)

    def __repr__(self) -> str:
        # Sort mappings by target layer for deterministic repr
        sorted_mappings = sorted(self.mappings.items(), key=lambda x: (x[0].layer, x[0].datatype))
        mappings_str = ", ".join(f"{k!r}: {v!r}" for k, v in sorted_mappings)
        return f"LayerMapping({{{mappings_str}}})"

    def __hash__(self) -> int:
        # Sort items for deterministic hash
        sorted_items = tuple(
            sorted(self.mappings.items(), key=lambda x: (x[0].layer, x[0].datatype))
        )
        return hash(sorted_items)

    @property
    def _hash_string(self) -> str:
        # Sort mappings by target layer for deterministic hash string
        sorted_mappings = sorted(self.mappings.items(), key=lambda x: (x[0].layer, x[0].datatype))
        mappings_str = ",".join(f"{k._hash_string}:{v._hash_string}" for k, v in sorted_mappings)
        return f"LayerMapping({{{mappings_str}}})"


@cell
def _apply_layer_mapping(source: Cell, mapping: LayerMapping) -> Cell:
    """Internal cell function to apply layer mappings to a source cell."""
    from gdswell.cell import Cell

    # Create a new cell and add the source cell as a reference
    new_cell = Cell(layout=source.layout)
    new_cell.add_ref(source)

    # Apply the mappings to the new cell
    mapping.apply(new_cell)

    return new_cell


# --- Operation Base Classes ---


@dataclass(frozen=True)
class LayerBinary(LayerBase):
    """Base class for geometric operations involving two source layers."""

    left: LayerBase
    right: LayerBase


# --- Boolean Operations ---


@dataclass(frozen=True)
class LayerUnion(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        region = self.left.get_shapes(cell) + self.right.get_shapes(cell)
        region.merge()
        return region

    @property
    def _hash_string(self) -> str:
        return f"({self.left._hash_string}|{self.right._hash_string})"


@dataclass(frozen=True)
class LayerDifference(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell) - self.right.get_shapes(cell)

    @property
    def _hash_string(self) -> str:
        return f"({self.left._hash_string}-{self.right._hash_string})"


@dataclass(frozen=True)
class LayerIntersection(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell) & self.right.get_shapes(cell)

    @property
    def _hash_string(self) -> str:
        return f"({self.left._hash_string}&{self.right._hash_string})"


@dataclass(frozen=True)
class LayerXor(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell) ^ self.right.get_shapes(cell)

    @property
    def _hash_string(self) -> str:
        return f"({self.left._hash_string}^out{self.right._hash_string})"


# --- Unary Geometric Operations ---


@dataclass(frozen=True)
class LayerSize(LayerBase):
    layer: LayerBase
    dx: float
    dy: float | None = None

    def get_shapes(self, cell: Cell) -> kdb.Region:
        dbu = cell.layout.kdb.dbu
        dx_dbu = int(round(self.dx / dbu))
        dy_dbu = int(round(self.dy / dbu)) if self.dy is not None else dx_dbu
        return self.layer.get_shapes(cell).sized(dx_dbu, dy_dbu)

    @property
    def _hash_string(self) -> str:
        dy_str = f",{self.dy:.6f}" if self.dy is not None else ""
        return f"Size({self.layer._hash_string},{self.dx:.6f}{dy_str})"


@dataclass(frozen=True)
class LayerTransformed(LayerBase):
    layer: LayerBase
    t: kdb.Trans | kdb.DTrans

    def get_shapes(self, cell: Cell) -> kdb.Region:
        # Convert DTrans to Trans if needed (Regions use integer transformations)
        t = self.t
        if isinstance(t, kdb.DTrans):
            t = t.to_itype(cell.layout.kdb.dbu)
        return self.layer.get_shapes(cell).transformed(t)

    @property
    def _hash_string(self) -> str:
        # DTrans/Trans repr is deterministic enough but we might want to be more specific
        return f"Transformed({self.layer._hash_string},{self.t!r})"


@dataclass(frozen=True)
class LayerBBox(LayerBase):
    layer: LayerBase

    def get_shapes(self, cell: Cell) -> kdb.Region:
        # Optimization for AllLayers shortcut
        if isinstance(self.layer, AllLayers):
            return kdb.Region(cell.kdb.bbox())

        region = self.layer.get_shapes(cell)
        return kdb.Region(region.bbox())

    @property
    def _hash_string(self) -> str:
        return f"BBox({self.layer._hash_string})"


@dataclass(frozen=True)
class LayerRounded(LayerBase):
    layer: LayerBase
    radius1: float
    radius2: float
    segments: int

    def get_shapes(self, cell: Cell) -> kdb.Region:
        dbu = cell.layout.kdb.dbu
        r1_dbu = int(round(self.radius1 / dbu))
        r2_dbu = int(round(self.radius2 / dbu))
        region = self.layer.get_shapes(cell).dup()
        region.round_corners(r1_dbu, r2_dbu, self.segments)
        return region

    @property
    def _hash_string(self) -> str:
        return (
            f"Rounded({self.layer._hash_string},{self.radius1:.6f},"
            f"{self.radius2:.6f},{self.segments})"
        )


# --- Interaction Filters ---


@dataclass(frozen=True)
class LayerInteracting(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell).interacting(self.right.get_shapes(cell))

    @property
    def _hash_string(self) -> str:
        return f"Interacting({self.left._hash_string},{self.right._hash_string})"


@dataclass(frozen=True)
class LayerNotInteracting(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        r_left = self.left.get_shapes(cell)
        return r_left - r_left.interacting(self.right.get_shapes(cell))

    @property
    def _hash_string(self) -> str:
        return f"NotInteracting({self.left._hash_string},{self.right._hash_string})"


@dataclass(frozen=True)
class LayerInside(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell).inside(self.right.get_shapes(cell))

    @property
    def _hash_string(self) -> str:
        return f"Inside({self.left._hash_string},{self.right._hash_string})"


@dataclass(frozen=True)
class LayerOutside(LayerBinary):
    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell).outside(self.right.get_shapes(cell))

    @property
    def _hash_string(self) -> str:
        return f"Outside({self.left._hash_string},{self.right._hash_string})"


@dataclass(frozen=True)
class LayerOverlapping(LayerBinary):
    min_count: int = 1

    def get_shapes(self, cell: Cell) -> kdb.Region:
        return self.left.get_shapes(cell).overlapping(self.right.get_shapes(cell), self.min_count)

    @property
    def _hash_string(self) -> str:
        return f"Overlapping({self.left._hash_string},{self.right._hash_string},{self.min_count})"
