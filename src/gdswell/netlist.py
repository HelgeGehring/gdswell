# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Protocol

from gdswell.cell import Cell
from gdswell.instance import Instance
from gdswell.port import Port


@dataclass(frozen=True)
class Endpoint:
    """An endpoint represents a specific port on an instantiated subcell."""

    inst: str  # Name of the instance (e.g., 'straight_0')
    port: str  # Name of the port on that instance

    def __repr__(self) -> str:
        return f"{self.inst}.{self.port}"


@dataclass(frozen=True)
class Connection:
    """A connection between two endpoints within a cell."""

    endpoint1: Endpoint
    endpoint2: Endpoint

    def __repr__(self) -> str:
        return f"{self.endpoint1} <-> {self.endpoint2}"


@dataclass(frozen=True)
class Netlist:
    """The complete single-level netlist of a parent cell."""

    instances: dict[str, Cell]  # Map of instance names to their definitions
    connections: list[Connection]  # List of internal connections
    exposed_ports: dict[str, Endpoint]  # Map of parent exposed ports to internal endpoints

    def __repr__(self) -> str:
        lines = ["Netlist("]
        if self.instances:
            lines.append("  Instances:")
            for name, cell in self.instances.items():
                lines.append(f"    {name} ({cell.name})")
        if self.connections:
            lines.append("  Connections:")
            for conn in self.connections:
                lines.append(f"    {conn}")
        if self.exposed_ports:
            lines.append("  Exposed Ports:")
            for p_name, ep in self.exposed_ports.items():
                lines.append(f"    {p_name} -> {ep}")
        lines.append(")")
        return "\n".join(lines)


def extract_netlist(cell: Cell) -> Netlist:
    """
    Dynamically extract the single-level netlist of a cell by performing
    a spatial collision check between its internal instances and exposed ports.
    """

    if not cell.frozen:
        raise RuntimeError(f"Cell '{cell.name}' must be frozen before extracting netlist.")

    dbu = cell.layout.kdb.dbu
    instances: dict[str, Cell] = {inst.name: inst.cell for inst in cell.instances}
    connections: list[Connection] = []
    exposed_ports: dict[str, Endpoint] = {}

    # Track which instance ports are already connected or exposed
    port_usage: dict[Endpoint, str] = {}

    # Spatial hash: (dbu_x, dbu_y) -> list[tuple[Instance, Port]]
    ports_at_pos: dict[tuple[int, int], list[tuple[Instance, Port]]] = {}

    instances_with_ports = [inst for inst in cell.instances if len(inst) > 0]
    for inst in instances_with_ports:
        for port in inst.values():
            # Round position to DBU grid to handle floating point jitter
            key = (int(round(port.position[0] / dbu)), int(round(port.position[1] / dbu)))
            ports_at_pos.setdefault(key, []).append((inst, port))

    # 1. Check for internal connections between sub-cells
    for ports in ports_at_pos.values():
        if len(ports) < 2:
            continue

        # Check all pairs at this position
        for (inst_a, port_a), (inst_b, port_b) in combinations(ports, 2):
            if inst_a is inst_b:
                continue

            if port_a.connects_to(port_b):
                ep_a, ep_b = Endpoint(inst_a.name, port_a.name), Endpoint(inst_b.name, port_b.name)

                # Validation: No double-usage
                if ep_a in port_usage:
                    raise RuntimeError(
                        f"Port '{port_a.name}' of instance '{inst_a.name}' "
                        f"is already {port_usage[ep_a]}."
                    )
                if ep_b in port_usage:
                    raise RuntimeError(
                        f"Port '{port_b.name}' of instance '{inst_b.name}' "
                        f"is already {port_usage[ep_b]}."
                    )

                port_usage[ep_a] = "connected"
                port_usage[ep_b] = "connected"
                connections.append(Connection(ep_a, ep_b))

    # 2. Check for bindings from parent cell ports to internal sub-cells
    for p_p_name, p_port in cell.ports.items():
        # Parent port is in the same coordinate system as transformed instance ports
        key = (int(round(p_port.position[0] / dbu)), int(round(p_port.position[1] / dbu)))
        candidates = ports_at_pos.get(key, [])

        for inst, s_port in candidates:
            if p_port == s_port:
                ep = Endpoint(inst.name, s_port.name)
                # Validation: No composite connection/exposure
                if ep in port_usage:
                    raise RuntimeError(
                        f"Port '{s_port.name}' of instance '{inst.name}' "
                        f"is already {port_usage[ep]}."
                    )

                port_usage[ep] = "exposed"
                exposed_ports[p_p_name] = ep
                break

    return Netlist(instances, connections, exposed_ports)


class Processor(Protocol):
    """Protocol for hierarchical path processors."""

    def __call__(self, cell: Cell, sub_results: dict[str, Any], netlist: Netlist) -> Any:
        """Process a cell and its sub-results."""
        ...


def hierarchical_extract(
    cell: Cell,
    processor_mapping: dict[str, Processor],
    memo: dict[Cell, Any] | None = None,
) -> Any:
    """
    Recursively extract properties from a cell hierarchy using a processor mapping.

    Args:
        cell: The top-level cell to start extraction from.
        processor_mapping: Mapping of cell generating function names to processors.
            Processors take (cell, sub_results, netlist) and return a value.
        memo: Optional dictionary for memoization of results.

    Returns:
        The result of the processor for the top-level cell.
    """
    if memo is None:
        memo = {}

    if cell in memo:
        return memo[cell]

    # 1. Process sub-instances first (depth-first)
    sub_results = {}
    for inst in cell.instances:
        sub_results[inst.name] = hierarchical_extract(inst.cell, processor_mapping, memo)

    # 2. Extract netlist for the current level
    netlist = extract_netlist(cell)

    # 3. Apply processor if matching
    func_name = cell.function_name
    result: Any
    if func_name in processor_mapping:
        result = processor_mapping[func_name](cell, sub_results, netlist)
    else:
        # Default: just return sub_results
        result = sub_results

    memo[cell] = result
    return result


# Register netlist extraction as a cell validator
# Cell.validators.append(extract_netlist)
