# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import klayout.db as kdb_

if TYPE_CHECKING:
    from gdswell.cell import Cell
    from gdswell.layout import Layout


def _serialize_info(data: Any) -> Any:
    """Recursively convert objects with to_dict to serializable dictionaries."""
    if isinstance(data, dict):
        return {k: _serialize_info(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialize_info(v) for v in data]
    if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
        return data.to_dict()
    return data


def _deserialize_info(data: Any, layout: Layout) -> Any:
    """Recursively reconstruct objects from serializable dictionaries."""
    if isinstance(data, dict):
        if "__type__" in data:
            if data["__type__"] == "Layer":
                from gdswell.layer import Layer

                return Layer.from_dict(data)
        return {k: _deserialize_info(v, layout) for k, v in data.items()}
    if isinstance(data, list):
        return [_deserialize_info(v, layout) for v in data]
    return data


def save_cell_metadata(cell: Cell) -> None:
    """Store cell info and ports as JSON metadata in the klayout cell."""
    try:
        info_json = json.dumps(_serialize_info(cell._info_data))
        cell.kdb.add_meta_info(kdb_.LayoutMetaInfo("cell_info", info_json, None, True))
    except Exception as e:
        print(f"Error saving cell info for {cell.name}: {e}")
        print(cell._info_data)
        raise e

    try:
        ports_data = {name: port.to_dict() for name, port in cell._ports_data.items()}
        ports_json = json.dumps(ports_data)
        cell.kdb.add_meta_info(kdb_.LayoutMetaInfo("ports", ports_json, None, True))
    except Exception as e:
        print(f"Error saving ports for {cell.name}: {e}")
        print(cell._ports_data)
        raise e


def restore_cell_metadata(cell: Cell) -> None:
    """Read cell info and ports from klayout metadata and restore them to the Cell wrapper."""
    for meta in cell.kdb.each_meta_info():
        if meta.name == "cell_info":
            cell._info_data = _deserialize_info(json.loads(meta.value), cell.layout)
            if not isinstance(cell._info_data, dict):
                raise ValueError("cell_info must be a dictionary")
        elif meta.name == "function_name":
            cell._function_name = meta.value
        elif meta.name == "function_module":
            cell._function_module = meta.value
        elif meta.name == "ports":
            ports_data = json.loads(meta.value)
            if not isinstance(ports_data, dict):
                raise ValueError("ports must be a dictionary")

            from gdswell.cell import Cell
            from gdswell.config import config
            from gdswell.port import Port

            for port_name, data in ports_data.items():
                # Convert position list back to tuple
                if "position" in data:
                    data["position"] = tuple(data["position"])

                # Restore cells mapping
                if "cells" in data:
                    resolved_cells = {}
                    for name, cell_name in data["cells"].items():
                        # 1. Check layout cache first (handles Cell and FutureCell)
                        res_cell = cell.layout._cache.get(cell_name)

                        if not res_cell:
                            # 2. Check klayout cells
                            kdb_cell = cell.layout.kdb.cell(cell_name)
                            if not kdb_cell and config.use_disk_cache:
                                # 3. Try to load from disk cache
                                cache_file = config.cache_dir / f"{cell_name}.oas"
                                if cache_file.exists():
                                    cell.layout._read_internal(str(cache_file), cell_name=cell_name)
                                    kdb_cell = cell.layout.kdb.cell(cell_name)

                            if kdb_cell:
                                res_cell = Cell._from_kdb_cell(kdb_cell, layout=cell.layout)

                        if res_cell:
                            resolved_cells[name] = res_cell

                    data["cells"] = resolved_cells

                # Restore CrossSection if it exists
                if "cross_section" in data and data["cross_section"] is not None:
                    from gdswell.cross_section import CrossSection

                    data["cross_section"] = CrossSection.from_dict(
                        data["cross_section"], layout=cell.layout
                    )

                cell._ports_data[port_name] = Port(**data)


def copy_kdb_cell(
    source_cell: kdb_.Cell, target_layout: kdb_.Layout, prefix: str = ""
) -> kdb_.Cell:
    """Recursively copy a cell hierarchy, reusing cells by name (with optional prefix)."""
    target_name = prefix + source_cell.name
    existing = target_layout.cell(target_name)
    if existing:
        return existing

    target_cell = target_layout.create_cell(target_name)
    source_layout = source_cell.layout()

    # Copy shapes using native C++ method (much faster than Python loop)
    target_cell.copy_shapes(source_cell)

    # Copy instances
    for inst in source_cell.each_inst():
        source_child = source_layout.cell(inst.cell_index)
        target_child = copy_kdb_cell(source_child, target_layout, prefix=prefix)
        # Use the transformation from the source instance
        target_cell.insert(kdb_.DCellInstArray(target_child.cell_index(), inst.dtrans))

    # Copy metadata
    for meta in source_cell.each_meta_info():
        target_cell.add_meta_info(meta)

    return target_cell
