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

    ``z_to_layer`` maps absolute z values to ``LayerBase`` recipes. Between
    adjacent z-keys the cross-section is linearly morphed (slanted sidewalls).
    A single-key entry is a zero-thickness sheet — useful as a boundary tag
    or as a cut surface.
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

    ``keep=False`` items participate in painter's-algorithm cuts but are
    dropped from the resolved output.
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
        return NotImplemented  # type: ignore[return-value]

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

    def resolve(self, cell: "gw.Cell") -> list[ResolvedPrism]:
        """Resolve the stackup against ``cell`` via painter's algorithm."""
        if not self.items:
            return []

        # Step 1: materialize each entry's regions at its own keys.
        per_entry: list[dict[float, kdb.Region]] = [
            _materialize(it.entry, cell) for it in self.items
        ]

        # Step 2: compute the global z-axis (union of all entries' keys).
        global_zs = sorted({z for regions in per_entry for z in regions})

        # Step 3: re-sample each entry onto every global z that falls in its
        # own [zmin, zmax] (so cuts can apply uniformly).
        resampled: list[dict[float, kdb.Region]] = []
        for regions in per_entry:
            if not regions:
                resampled.append({})
                continue
            zmin, zmax = min(regions), max(regions)
            sampled: dict[float, kdb.Region] = {}
            for z in global_zs:
                if zmin <= z <= zmax:
                    sampled[z] = _resample_entry(regions, z)
            resampled.append(sampled)

        # Step 4: walk in order, painter-style. Each new entry B subtracts
        # itself from all previously-seen entries A at every shared z.
        for j in range(len(resampled)):
            B = resampled[j]
            for i in range(j):
                A = resampled[i]
                for z, regionB in B.items():
                    if z in A:
                        A[z] = A[z] - regionB

        # Step 5 & 6: filter keep=False, drop empty, emit ResolvedPrisms.
        out: list[ResolvedPrism] = []
        for idx, (it, regions) in enumerate(zip(self.items, resampled)):
            if not it.keep:
                continue
            if all(r.is_empty() for r in regions.values()):
                continue
            out.append(
                ResolvedPrism(
                    name=it.entry.name,
                    z_to_region=regions,
                    mesh_order=idx,
                )
            )
        return out


@dataclass(frozen=True)
class ResolvedPrism:
    """The output of ``Stackup.resolve(cell)``: one frozen recipe per surviving entry.

    ``z_to_region`` maps z values (the entry's original keys plus any keys
    introduced by cuts during resolution) to ``kdb.Region``s, post-cut and
    post-priority. ``mesh_order`` reflects position in the original Stackup
    (later = higher priority = larger ``mesh_order``).
    """

    name: str
    z_to_region: dict[float, kdb.Region]
    mesh_order: int


def _materialize(entry: StackupEntry, cell: "gw.Cell") -> dict[float, kdb.Region]:
    """Compute the ``kdb.Region`` for every z-key in ``entry``."""
    return {z: L.get_shapes(cell) for z, L in entry.z_to_layer.items()}


def _interp_region(r0: kdb.Region, r1: kdb.Region, t: float) -> kdb.Region:
    """Linear morph between two regions of identical topology.

    Topology must match: same polygon count, and corresponding polygons must
    have the same point count. We interpolate vertex positions at parameter
    ``t`` ∈ [0, 1]. Mismatched topology raises ``NotImplementedError``.

    For ``t == 0`` we return ``r0.dup()``, for ``t == 1`` we return ``r1.dup()``
    (avoiding floating-point drift on exact endpoints).
    """
    if t == 0.0:
        return r0.dup()
    if t == 1.0:
        return r1.dup()

    polys0 = list(r0.each())
    polys1 = list(r1.each())
    if len(polys0) != len(polys1):
        raise NotImplementedError(
            f"Cannot linearly interpolate regions with mismatched topology: "
            f"{len(polys0)} vs {len(polys1)} polygons. "
            f"Either keep both z-key layers topology-equivalent (e.g. via "
            f".size(...)), or split the entry into multiple entries."
        )

    out = kdb.Region()
    for p0, p1 in zip(polys0, polys1):
        hull0 = list(p0.each_point_hull())
        hull1 = list(p1.each_point_hull())
        if len(hull0) != len(hull1):
            raise NotImplementedError(
                f"Cannot linearly interpolate polygons with mismatched topology: "
                f"{len(hull0)} vs {len(hull1)} hull points."
            )
        # holes must also match in count
        nholes0, nholes1 = p0.holes(), p1.holes()
        if nholes0 != nholes1:
            raise NotImplementedError(
                f"Cannot linearly interpolate polygons with mismatched hole "
                f"counts: {nholes0} vs {nholes1}."
            )
        morphed_hull = [
            kdb.Point(
                int(round(a.x + (b.x - a.x) * t)),
                int(round(a.y + (b.y - a.y) * t)),
            )
            for a, b in zip(hull0, hull1)
        ]
        morphed = kdb.Polygon(morphed_hull)
        for h in range(nholes0):
            holes0 = list(p0.each_point_hole(h))
            holes1 = list(p1.each_point_hole(h))
            if len(holes0) != len(holes1):
                raise NotImplementedError(
                    f"Cannot linearly interpolate hole {h} with mismatched "
                    f"point counts: {len(holes0)} vs {len(holes1)}."
                )
            morphed.insert_hole(
                [
                    kdb.Point(
                        int(round(a.x + (b.x - a.x) * t)),
                        int(round(a.y + (b.y - a.y) * t)),
                    )
                    for a, b in zip(holes0, holes1)
                ]
            )
        out.insert(morphed)
    return out


def _resample_entry(z_to_region: dict[float, kdb.Region], z: float) -> kdb.Region:
    """Return the entry's region at z. Strictly inside the entry's range, the
    region is interpolated between adjacent original keys (linear morph).

    The caller must ensure ``min(keys) <= z <= max(keys)``; otherwise this
    returns an empty region (entry has no volume there).
    """
    keys = sorted(z_to_region.keys())
    if z < keys[0] or z > keys[-1]:
        return kdb.Region()
    if z in z_to_region:
        return z_to_region[z].dup()
    # find bracketing keys
    for k0, k1 in zip(keys, keys[1:]):
        if k0 <= z <= k1:
            t = (z - k0) / (k1 - k0)
            return _interp_region(z_to_region[k0], z_to_region[k1], t)
    return kdb.Region()  # unreachable
