# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import unittest.mock as mock
from pathlib import Path

import gdswell.hashing
from gdswell.hashing import get_module_dependencies, get_total_source_hash


def test_version_hash_invalidation():
    # Clear cache before starting
    gdswell.hashing._SOURCE_HASH_CACHE.clear()

    def dummy_func():
        pass

    root = Path("/tmp")  # Dummy root

    # We patch inside gdswell.hashing because that's where they are used
    with (
        mock.patch("gdswell.hashing.sys") as mock_sys,
        mock.patch("gdswell.hashing.get_module_dependencies") as mock_get_deps,
    ):
        # Case 1: Python version change
        mock_get_deps.return_value = (set(), set())
        mock_sys.version = "3.13.0"

        hash1 = get_total_source_hash(dummy_func, root)

        gdswell.hashing._SOURCE_HASH_CACHE.clear()
        mock_sys.version = "3.14.0"
        hash2 = get_total_source_hash(dummy_func, root)

        assert hash1 != hash2, "Hash should change when Python version changes"

        # Case 2: External dependency version change
        mock_sys.version = "3.13.0"
        # get_module_dependencies now returns pre-formatted name==version strings
        mock_get_deps.return_value = (set(), {"klayout==0.30.7"})

        gdswell.hashing._SOURCE_HASH_CACHE.clear()
        hash3 = get_total_source_hash(dummy_func, root)

        mock_get_deps.return_value = (set(), {"klayout==0.30.8"})
        gdswell.hashing._SOURCE_HASH_CACHE.clear()
        hash4 = get_total_source_hash(dummy_func, root)

        assert hash3 != hash4, "Hash should change when external dependency version changes"


def test_get_module_dependencies_external(tmp_path: Path):
    # Create a dummy module that looks like it's in site-packages
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    ext_mod_path = site_packages / "external_pkg.py"
    ext_mod_path.write_text("def foo(): pass")

    import importlib.util

    spec = importlib.util.spec_from_file_location("external_pkg", str(ext_mod_path))
    assert spec is not None
    assert spec.loader is not None
    ext_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ext_mod)

    # Create a project module that imports it
    project_root = tmp_path / "project"
    project_root.mkdir()
    proj_mod_path = project_root / "proj_mod.py"
    proj_mod_path.write_text("import external_pkg")

    spec = importlib.util.spec_from_file_location("proj_mod", str(proj_mod_path))
    assert spec is not None
    proj_mod = importlib.util.module_from_spec(spec)
    # We need to make external_pkg available for import
    import sys

    sys.modules["external_pkg"] = ext_mod
    # And we add external_pkg to proj_mod's globals so get_module_dependencies finds it
    setattr(proj_mod, "external_pkg", ext_mod)

    # No need to mock packages_distributions anymore as it's not used.
    # Instead, we mock version() to return a predictable version for the mock module.
    with mock.patch("gdswell.hashing.version") as mock_v:
        mock_v.return_value = "1.2.3"
        project_deps, external_pkgs = get_module_dependencies(proj_mod, project_root)

        assert "external_pkg==1.2.3" in external_pkgs
        assert proj_mod_path in project_deps


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
