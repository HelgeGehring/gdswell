# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import json
from pathlib import Path

import gdswell as gw


@gw.cell
def my_component(w: float = 1.0) -> gw.Cell:
    c = gw.Cell()
    c.add_polygon([(0, 0), (w, 0), (w, 1), (0, 1)], layer=gw.Layer(1, 0))
    return c


def test_cache_dependency_file(tmp_path: Path):
    # Setup test cache
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True
    gw.config.debug_cache = True

    gw.clear_cache()

    with gw.Layout():
        c = my_component(w=2.0)
        name = c.name
        oas_file = test_cache_dir / f"{name}.oas"
        dep_file = test_cache_dir / f"{name}.dep"

        assert oas_file.exists()
        assert dep_file.exists()

        with open(dep_file, "r") as f:
            data = json.load(f)

        assert "files" in data
        assert "external_packages" in data
        # Check if THIS file is in the dependencies
        this_file = str(Path(__file__).resolve())
        assert this_file in data["files"]


def test_cache_dependency_file_disabled(tmp_path: Path):
    # Setup test cache
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True
    gw.config.debug_cache = False

    gw.clear_cache()

    with gw.Layout():
        c = my_component(w=3.0)
        name = c.name
        oas_file = test_cache_dir / f"{name}.oas"
        dep_file = test_cache_dir / f"{name}.dep"

        assert oas_file.exists()
        assert not dep_file.exists()
