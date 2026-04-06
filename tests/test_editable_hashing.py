# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import json
import types
import unittest.mock as mock

import gdswell.hashing
from gdswell.hashing import get_module_dependencies


def test_editable_hashing(tmp_path):
    # Clear caches
    gdswell.hashing._MODULE_DEP_CACHE.clear()
    gdswell.hashing._is_package_editable.cache_clear()

    # 1. Create a "package" outside the root
    external_root = tmp_path / "external_pkg"
    external_root.mkdir()
    ext_mod_path = external_root / "ext_mod.py"
    ext_mod_path.write_text("def bar(): pass")

    # 2. Mock a module for this package
    ext_mod = types.ModuleType("ext_mod")
    ext_mod.__file__ = str(ext_mod_path)
    ext_mod.__name__ = "ext_mod"

    # 3. Mock the project module that imports it
    proj_root = tmp_path / "project"
    proj_root.mkdir()
    proj_mod_path = proj_root / "proj_mod.py"
    proj_mod_path.write_text("import ext_mod")

    proj_mod = types.ModuleType("proj_mod")
    proj_mod.__file__ = str(proj_mod_path)
    proj_mod.__name__ = "proj_mod"
    setattr(proj_mod, "ext_mod", ext_mod)

    # 4. Mock distribution and version
    with (
        mock.patch("gdswell.hashing.distribution") as mock_dist,
        mock.patch("gdswell.hashing.version") as mock_ver,
        mock.patch.dict("sys.modules", {"ext_mod": ext_mod, "proj_mod": proj_mod}),
    ):
        mock_d = mock.MagicMock()
        # Simulate direct_url.json with editable: true
        mock_d.read_text.return_value = json.dumps({"dir_info": {"editable": True}})
        mock_dist.return_value = mock_d
        mock_ver.return_value = "1.0.0"

        # 5. Run get_module_dependencies
        deps, external_pkgs = get_module_dependencies(proj_mod, proj_root)

        # 6. Verify ext_mod_path is in deps (crawled)
        # because it is editable, even though it is outside proj_root
        assert ext_mod_path in deps
        assert not any("ext_mod==" in p for p in external_pkgs)


def test_non_editable_hashing(tmp_path):
    # Clear caches
    gdswell.hashing._MODULE_DEP_CACHE.clear()
    gdswell.hashing._is_package_editable.cache_clear()

    # 1. Create a "package" in site-packages (simulated by path)
    sp_root = tmp_path / "site-packages"
    sp_root.mkdir()
    ext_mod_path = sp_root / "ext_mod.py"
    ext_mod_path.write_text("def bar(): pass")

    # 2. Mock a module for this package
    ext_mod = types.ModuleType("ext_mod")
    ext_mod.__file__ = str(ext_mod_path)
    ext_mod.__name__ = "ext_mod"

    # 3. Mock the project module that imports it
    proj_root = tmp_path / "project"
    proj_root.mkdir()
    proj_mod_path = proj_root / "proj_mod.py"
    proj_mod_path.write_text("import ext_mod")

    proj_mod = types.ModuleType("proj_mod")
    proj_mod.__file__ = str(proj_mod_path)
    proj_mod.__name__ = "proj_mod"
    setattr(proj_mod, "ext_mod", ext_mod)

    # 4. Mock distribution and version (NON-EDITABLE)
    with (
        mock.patch("gdswell.hashing.distribution") as mock_dist,
        mock.patch("gdswell.hashing.version") as mock_ver,
        mock.patch.dict("sys.modules", {"ext_mod": ext_mod, "proj_mod": proj_mod}),
    ):
        # distribution(ext_mod) fails or returns no direct_url
        mock_dist.side_effect = Exception("Not found")
        mock_ver.return_value = "1.0.0"

        # 5. Run get_module_dependencies
        deps, external_pkgs = get_module_dependencies(proj_mod, proj_root)

        # 6. Verify ext_mod is in external_pkgs (fast path) and NOT in deps
        assert "ext_mod==1.0.0" in external_pkgs
        assert ext_mod_path not in deps


if __name__ == "__main__":
    import pytest

    pytest.main([__file__])
