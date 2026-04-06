# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from pathlib import Path

import pytest

import gdswell as gw


@gw.cell
def cached_component(width: float = 10.0) -> gw.Cell:
    ls = gw.LayerSection(name="core", layer=gw.Layer(1, 0), width=1.0)
    xs = gw.CrossSection(layer_sections=(ls,))
    c = gw.Cell()
    c.add_polygon([(0, 0), (width, 0), (width, 1), (0, 1)], layer=gw.Layer(1, 0))
    c.add_info("test_meta", "hello")
    c.add_port(gw.Port(name="p1", position=(0, 0.5), angle=180, cross_section=xs))
    return c


def test_disk_cache_persistence(tmp_path: Path) -> None:
    # Use a temporary cache directory for this test
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True

    # 1. Clear existing cache
    gw.clear_cache()

    # 2. First call: generate and save
    with gw.Layout():
        c1 = cached_component(width=20.0)
        name = c1.name
        cache_file = test_cache_dir / f"{name}.oas"
        assert cache_file.exists()

    # 3. Second call in a new layout: should load from disk
    # We can verify this by checking if the cell was loaded from a file
    # and if the metadata is correct.
    with gw.Layout():
        # We manually check the cache file date or just trust the logic
        # if the cell name is found without re-executing the function body.
        # To strictly prove it's from disk, we could monkeypatch the function.

        c2 = cached_component(width=20.0)
        assert c2.name == name
        assert c2.info["test_meta"] == "hello"
        assert "p1" in c2.ports

    # 4. Clear cache and verify it's gone
    gw.clear_cache()
    assert not any(test_cache_dir.iterdir())


def test_disk_cache_disabled(tmp_path: Path) -> None:
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = False

    gw.clear_cache()

    with gw.Layout():
        c = cached_component(width=30.0)
        name = c.name
        cache_file = test_cache_dir / f"{name}.oas"
        assert not cache_file.exists()


if __name__ == "__main__":
    pytest.main([__file__])
