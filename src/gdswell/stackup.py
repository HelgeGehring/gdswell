# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from dataclasses import dataclass, field

from gdswell.layer import LayerBase


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
    def uniform(
        cls, name: str, layer: LayerBase, zmin: float, zmax: float
    ) -> StackupEntry:
        """Convenience: 2-key entry with the same layer at zmin and zmax."""
        return cls(name=name, z_to_layer={zmin: layer, zmax: layer})

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
