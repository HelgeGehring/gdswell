# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import klayout.db as kdb

from gdswell.layer import LayerBase

if TYPE_CHECKING:
    import gdswell as gw


@dataclass(frozen=True, eq=False)
class StackupEntry:
    """One logical 3D body: a named cross-section that varies with z.

    ``z_to_layer`` maps absolute z values to ``LayerBase`` recipes. The 3D
    backend (e.g. meshwell) is responsible for interpolating between adjacent
    z-keys when it lofts the prism — typically a linear morph producing
    slanted sidewalls. A single-key entry is a zero-thickness sheet — useful
    as a boundary tag or as a cut surface.
    """

    name: str
    z_to_layer: dict[float, LayerBase] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.z_to_layer) < 1:
            raise ValueError("StackupEntry.z_to_layer must have at least one key")

    @classmethod
    def uniform(cls, name: str, layer: LayerBase, zmin: float, zmax: float) -> StackupEntry:
        """Convenience: 2-key entry with the same layer at zmin and zmax."""
        return cls(name=name, z_to_layer={zmin: layer, zmax: layer})

    # --- algebra -------------------------------------------------------------

    def __add__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=True)
        if rhs is NotImplemented:
            return NotImplemented
        return Stackup(items=(StackupItem(self, True),) + rhs)

    def __sub__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=False)
        if rhs is NotImplemented:
            return NotImplemented
        return Stackup(items=(StackupItem(self, True),) + rhs)

    # --- layer-recipe operations --------------------------------------------

    def map_layers(self, fn: Callable[[LayerBase], LayerBase]) -> StackupEntry:
        """Return a new entry with ``fn`` applied to every layer recipe."""
        return replace(
            self,
            z_to_layer={z: fn(L) for z, L in self.z_to_layer.items()},
        )

    def size(self, dx: float, dy: float | None = None) -> StackupEntry:
        return self.map_layers(lambda L: L.size(dx, dy))

    def transformed(self, t: kdb.Trans | kdb.DTrans) -> StackupEntry:
        return self.map_layers(lambda L: L.transformed(t))

    def round_corners(self, r1: float, r2: float, segments: int) -> StackupEntry:
        return self.map_layers(lambda L: L.round_corners(r1, r2, segments))

    def bbox(self) -> StackupEntry:
        return self.map_layers(lambda L: L.bbox())

    def interacting(self, other: LayerBase, *, invert: bool = False) -> StackupEntry:
        if invert:
            return self.map_layers(lambda L: L.not_interacting(other))
        return self.map_layers(lambda L: L.interacting(other))

    def inside(self, other: LayerBase) -> StackupEntry:
        return self.map_layers(lambda L: L.inside(other))

    def outside(self, other: LayerBase) -> StackupEntry:
        return self.map_layers(lambda L: L.outside(other))

    def overlapping(self, other: LayerBase, min_count: int = 1) -> StackupEntry:
        return self.map_layers(lambda L: L.overlapping(other, min_count))

    # --- equality / hashing ---------------------------------------------------

    def _sorted_items(self) -> tuple[tuple[float, LayerBase], ...]:
        return tuple(sorted(self.z_to_layer.items(), key=lambda kv: kv[0]))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StackupEntry):
            return False
        return self.name == other.name and self._sorted_items() == other._sorted_items()

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                tuple((z, L._hash_string) for z, L in self._sorted_items()),
            )
        )

    @property
    def _hash_string(self) -> str:
        body = ",".join(f"{z}:{L._hash_string}" for z, L in self._sorted_items())
        return f"Entry({self.name},{body})"

    def __repr__(self) -> str:
        body = ", ".join(f"{z}: {L!r}" for z, L in self._sorted_items())
        return f"StackupEntry({self.name!r}, {{{body}}})"


@dataclass(frozen=True)
class StackupItem:
    """One slot in a Stackup: an entry plus a ``keep`` flag.

    ``keep`` is carried through to the resolved output verbatim: every slot
    becomes one ``ResolvedPrism`` (1:1 indexing). Downstream 3D backends use
    the flag to decide whether a prism contributes an output volume or is
    only a cutter referenced by other prisms' ``cut_by``.
    """

    entry: StackupEntry
    keep: bool


@dataclass(frozen=True, eq=False)
class Stackup:
    """An ordered list of (entry, keep) items composed by + / -.

    Composition is strict left-to-right (painter's algorithm). Use parentheses
    for explicit grouping.
    """

    items: tuple[StackupItem, ...] = ()

    @classmethod
    def of(cls, *entries: StackupEntry) -> Stackup:
        return cls(items=tuple(StackupItem(e, True) for e in entries))

    # --- coercion helpers ----------------------------------------------------

    @staticmethod
    def _coerce_items(other: StackupEntry | Stackup, *, keep: bool) -> tuple[StackupItem, ...]:
        if isinstance(other, StackupEntry):
            return (StackupItem(other, keep),)
        if isinstance(other, Stackup):
            if keep:
                return other.items
            return tuple(StackupItem(it.entry, False) for it in other.items)
        return NotImplemented

    # --- algebra -------------------------------------------------------------

    def __add__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=True)
        if rhs is NotImplemented:
            return NotImplemented
        return Stackup(items=self.items + rhs)

    def __sub__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=False)
        if rhs is NotImplemented:
            return NotImplemented
        return Stackup(items=self.items + rhs)

    def __radd__(self, other: StackupEntry) -> Stackup:
        if isinstance(other, StackupEntry):
            return Stackup(items=(StackupItem(other, True),) + self.items)
        return NotImplemented

    def __rsub__(self, other: StackupEntry) -> Stackup:
        if isinstance(other, StackupEntry):
            return Stackup(
                items=(StackupItem(other, True),)
                + tuple(StackupItem(it.entry, False) for it in self.items)
            )
        return NotImplemented

    # --- layer-recipe operations --------------------------------------------

    def map_layers(self, fn: Callable[[LayerBase], LayerBase]) -> Stackup:
        return Stackup(
            items=tuple(StackupItem(it.entry.map_layers(fn), it.keep) for it in self.items)
        )

    def size(self, dx: float, dy: float | None = None) -> Stackup:
        return self.map_layers(lambda L: L.size(dx, dy))

    def transformed(self, t: kdb.Trans | kdb.DTrans) -> Stackup:
        return self.map_layers(lambda L: L.transformed(t))

    def round_corners(self, r1: float, r2: float, segments: int) -> Stackup:
        return self.map_layers(lambda L: L.round_corners(r1, r2, segments))

    def bbox(self) -> Stackup:
        return self.map_layers(lambda L: L.bbox())

    def interacting(self, other: LayerBase, *, invert: bool = False) -> Stackup:
        return Stackup(
            items=tuple(
                StackupItem(it.entry.interacting(other, invert=invert), it.keep)
                for it in self.items
            )
        )

    def inside(self, other: LayerBase) -> Stackup:
        return self.map_layers(lambda L: L.inside(other))

    def outside(self, other: LayerBase) -> Stackup:
        return self.map_layers(lambda L: L.outside(other))

    def overlapping(self, other: LayerBase, min_count: int = 1) -> Stackup:
        return self.map_layers(lambda L: L.overlapping(other, min_count))

    # --- equality / hashing --------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Stackup):
            return False
        return self.items == other.items

    def __hash__(self) -> int:
        return hash(tuple((it.entry, it.keep) for it in self.items))

    @property
    def _hash_string(self) -> str:
        body = ",".join(f"{'+' if it.keep else '-'}{it.entry._hash_string}" for it in self.items)
        return f"Stackup({body})"

    def __repr__(self) -> str:
        body = ", ".join(f"{'+' if it.keep else '-'}{it.entry!r}" for it in self.items)
        return f"Stackup([{body}])"

    def resolve(self, cell: "gw.Cell") -> ResolvedStackup:
        """Materialize each entry's xy regions at its own z-keys (no resampling).
        Populate ``cut_by`` via O(N²) 3D-bbox overlap (z-range gate then xy-bbox
        intersection). The 3D backend performs the actual cuts.
        """
        # 1. Materialize raw per-z regions for every entry slot.
        raw: list[dict[float, kdb.Region]] = [
            {z: L.get_shapes(cell) for z, L in it.entry.z_to_layer.items()} for it in self.items
        ]

        # 2. Per-entry 3D bbox cache (None if entry has no geometry anywhere).
        bboxes: list[tuple[float, float, kdb.Box] | None] = [_entry_3d_bbox(r) for r in raw]

        # 3. For each slot i, find all later slots j whose 3D bbox overlaps i's.
        n = len(self.items)
        cut_by: list[tuple[int, ...]] = []
        for i in range(n):
            bi = bboxes[i]
            if bi is None:
                cut_by.append(())
                continue
            edges = tuple(
                j
                for j in range(i + 1, n)
                if (bj := bboxes[j]) is not None and _bbox3d_overlaps(bi, bj)
            )
            cut_by.append(edges)

        # 4. Emit one ResolvedPrism per slot.
        prisms = tuple(
            ResolvedPrism(
                name=it.entry.name,
                z_to_region=raw[i],
                mesh_order=i,
                keep=it.keep,
                cut_by=cut_by[i],
            )
            for i, it in enumerate(self.items)
        )
        return ResolvedStackup(prisms=prisms)


def _entry_3d_bbox(
    z_to_region: dict[float, kdb.Region],
) -> tuple[float, float, kdb.Box] | None:
    """Return ``(zmin, zmax, xy_bbox)`` for the entry, or ``None`` if it has
    no geometry at any z (every region is empty).

    The xy bbox is the union of per-z region bboxes, expressed as a
    ``kdb.Box`` in dbu. Single-z entries have zmin == zmax. The union
    covers the entry's full extruded footprint, so a downstream backend
    that lofts between z-keys can be bounded by it.
    """
    if not z_to_region:
        return None
    xy = kdb.Box()  # empty
    for r in z_to_region.values():
        if not r.is_empty():
            xy += r.bbox()
    if xy.empty():
        return None
    return min(z_to_region), max(z_to_region), xy


def _bbox3d_overlaps(a: tuple[float, float, kdb.Box], b: tuple[float, float, kdb.Box]) -> bool:
    """True iff the two 3D bboxes overlap. z-range gate then xy-bbox test.

    The z-gate uses strict ``<``, so entries that meet at a single z-plane
    (one ends where the other begins) are treated as overlapping. This is
    conservative on purpose: a 3D backend may loft an entry's footprint
    just past its declared z-keys (curve tolerance, arc fits), so we
    cannot rule the touching case out at bbox level. The cost of a false
    overlap is a no-op cut in the backend; the cost of a missed overlap
    would be silently wrong geometry.
    """
    az0, az1, axy = a
    bz0, bz1, bxy = b
    if az1 < bz0 or bz1 < az0:
        return False
    return not (axy & bxy).empty()


@dataclass(frozen=True)
class ResolvedPrism:
    """The output of ``Stackup.resolve(cell)``: one frozen recipe per source entry.

    ``z_to_region`` maps z values to ``kdb.Region``s at the entry's own z-keys
    (no resampling). ``mesh_order`` equals the entry's position in the source
    ``Stackup``. ``keep`` mirrors ``StackupItem.keep`` — ``False`` prisms are
    cutters retained in the output so ``cut_by`` indices can reference them,
    but downstream backends do not emit them as output volumes. ``cut_by`` is
    a tuple of indices ``j > self.mesh_order`` whose 3D bbox overlaps this
    prism's; downstream backends subtract those prisms' raw solids to obtain
    the final volume.
    """

    name: str
    z_to_region: dict[float, kdb.Region]
    mesh_order: int
    keep: bool = True
    cut_by: tuple[int, ...] = ()


@dataclass(frozen=True)
class ResolvedStackup:
    """Output of ``Stackup.resolve(cell)``: a tuple of prisms indexed 1:1 with
    the source ``Stackup.items``.

    Both ``keep=True`` and ``keep=False`` prisms appear in ``prisms``. The
    1:1 indexing invariant lets ``ResolvedPrism.cut_by`` use compact integer
    indices and matches the painter's-order semantics already encoded in the
    input ``Stackup``.
    """

    prisms: tuple[ResolvedPrism, ...] = ()
