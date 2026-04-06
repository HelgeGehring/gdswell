# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import ast
import functools
import hashlib
import importlib.util
import inspect
import sys
from functools import lru_cache
from importlib.metadata import distribution, version
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Dict, Set, Tuple, cast

if TYPE_CHECKING:
    pass


def get_project_file_hash(path: Path) -> str:
    """Read and hash file content, cached by (path, mtime).
    Now uses the unified _inspect_project_file for consistency."""
    h, _ = _inspect_project_file(path)
    return h


# Cache for file hash and static imports: path -> (mtime, hash, imports)
_PROJECT_FILE_CACHE: Dict[Path, Tuple[float, str, Set[Tuple[str, int]]]] = {}

# Cache for module dependencies: (module, root, mtime) -> (Set[Path], Set[str])
_MODULE_DEP_CACHE: Dict[Tuple[ModuleType, Path, float], Tuple[Set[Path], Set[str]]] = {}


def _inspect_project_file(path: Path) -> Tuple[str, Set[Tuple[str, int]]]:
    """Read file once, compute SHA1 hash, and extract imports via AST.
    Returns (hash, set_of_tuples(module_name, level))."""
    path = path.resolve()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "", set()

    if path in _PROJECT_FILE_CACHE:
        # Note: We still return from cache if mtime matches
        cached_mtime, cached_hash, cached_imports = _PROJECT_FILE_CACHE[path]
        if cached_mtime == mtime:
            return cached_hash, cached_imports

    try:
        content_bytes = path.read_bytes()
        h = hashlib.sha1(content_bytes).hexdigest()

        # Static Analysis (AST)
        content_str = content_bytes.decode("utf-8")
        tree = ast.parse(content_str)
        imports: Set[Tuple[str, int]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add((alias.name, 0))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add((node.module, node.level))
                elif node.level > 0:
                    # e.g. "from . import x" -> module is None, level is 1
                    imports.add(("", node.level))
    except (OSError, UnicodeDecodeError, SyntaxError):
        # Fallback to empty if we can't parse it
        return "", set()

    res = (h, imports)
    _PROJECT_FILE_CACHE[path] = (mtime, h, imports)
    return res


def _resolve_module_info(
    name: str, package: str | None, level: int = 0
) -> Tuple[Path | None, str | None]:
    """Find the file path and top-level package name for a module name, without importing it."""
    try:
        # 1. Resolve relative name if needed
        if level > 0:
            name = importlib.util.resolve_name("." * level + name, package)

        if not name:
            return None, None

        top_level = name.split(".")[0]

        # 2. Check if already loaded to avoid slow find_spec
        if name in sys.modules:
            mod = sys.modules[name]
            if hasattr(mod, "__file__") and mod.__file__:
                return Path(mod.__file__).resolve(), top_level
            return None, top_level

        # 3. Use find_spec for static resolution
        spec = importlib.util.find_spec(name)
        if spec and spec.has_location and spec.origin:
            return Path(spec.origin).resolve(), top_level

        return None, top_level
    except (ImportError, AttributeError, ValueError, TypeError):
        return None, None


@lru_cache(maxsize=None)
def _is_package_editable(package_name: str) -> bool:
    """Check if a package is installed in editable mode."""
    try:
        dist = distribution(package_name)
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            import json

            data = json.loads(direct_url)
            return data.get("dir_info", {}).get("editable", False)
    except Exception:
        pass
    return False


def get_module_dependencies(module: ModuleType, root: Path) -> Tuple[Set[Path], Set[str]]:
    """Recursively find all project modules and external packages imported by the given module."""
    if not (hasattr(module, "__file__") and module.__file__):
        return set(), set()

    mod_path = Path(module.__file__).resolve()
    if not str(mod_path).startswith(str(root)):
        return set(), set()

    # Try cache
    try:
        mtime = mod_path.stat().st_mtime
    except OSError:
        mtime = 0.0

    cache_key = (module, root, mtime)
    if cache_key in _MODULE_DEP_CACHE:
        return _MODULE_DEP_CACHE[cache_key]

    deps: Set[Path] = set()
    external_pkgs: Set[str] = set()
    seen_paths: Set[Path] = set()

    # We use a BFS queue of (path, module_name, package_context)
    # package_context is needed for relative import resolution
    # Start with the input module
    parent_package = getattr(module, "__package__", None)
    queue = [(mod_path, module.__name__, parent_package)]
    seen_paths.add(mod_path)

    while queue:
        curr_path, curr_name, curr_package = queue.pop(0)
        path_str = str(curr_path)
        top_level = curr_name.split(".")[0] if curr_name else ""

        # 1. External package detection (site-packages or venv)
        if ".venv" in path_str or "site-packages" in path_str:
            if not _is_package_editable(top_level):
                # Try to get version from sys.modules or importlib.metadata
                v = None
                if curr_name and curr_name in sys.modules:
                    v = getattr(sys.modules[curr_name], "__version__", None)
                if not v and top_level:
                    try:
                        v = version(top_level)
                    except Exception:
                        v = None

                if v:
                    external_pkgs.add(f"{top_level}=={v}")
                    continue  # Stop crawling frozen packages

            # If NO version or it IS editable, we CONTINUE to crawl recursively (Deep Path)

        # 2. Local/Editable check
        is_local = path_str.startswith(str(root))
        is_editable = not is_local and _is_package_editable(top_level)

        if not is_local and not is_editable:
            continue

        # 3. Solid Hashing and Discovery
        deps.add(curr_path)
        _, static_imports = _inspect_project_file(curr_path)

        for imp_name, level in static_imports:
            # Resolve to file path
            o_path, o_top = _resolve_module_info(imp_name, curr_package, level)
            if o_path and o_path not in seen_paths:
                # Determine absolute module name for the discovered file
                # To get the correct package context, we try to use sys.modules
                # or derive it from the spec if we had it.
                # For simplicity, we just use the name from resolve_name if level > 0
                abs_name = imp_name
                if level > 0:
                    try:
                        abs_name = importlib.util.resolve_name("." * level + imp_name, curr_package)
                    except Exception:
                        pass

                # New package context for the next iteration
                new_package = abs_name.rpartition(".")[0] if "." in abs_name else abs_name

                seen_paths.add(o_path)
                queue.append((o_path, abs_name, new_package))

    res = (deps, external_pkgs)
    _MODULE_DEP_CACHE[cache_key] = res
    return res


# Cache for total source hashes: func -> (hash, deps, external_pkgs)
_SOURCE_HASH_CACHE: Dict[Callable[..., Any], Tuple[str, Set[Path], Set[str]]] = {}


def get_total_source_hash(func: Callable[..., Any], root: Path) -> Tuple[str, Set[Path], Set[str]]:
    """Compute a combined hash of the function's module, its project dependencies,
    external packages, and python version.
    Returns (hash, deps, external_pkgs)."""
    if func in _SOURCE_HASH_CACHE:
        return _SOURCE_HASH_CACHE[func]

    mod = inspect.getmodule(func)
    if not mod or not hasattr(mod, "__file__") or not mod.__file__:
        # Fallback for dynamic/builtin functions
        try:
            res = hashlib.sha1(inspect.getsource(func).encode("utf-8")).hexdigest()
        except (TypeError, OSError):
            mod_name = getattr(func, "__module__", "unknown")
            qual_name = getattr(func, "__qualname__", "unknown")
            res = hashlib.sha1(f"{mod_name}.{qual_name}".encode("utf-8")).hexdigest()
        result = (res, set(), set())
        _SOURCE_HASH_CACHE[func] = result
        return result

    # 0. Salt with full module name and function name (with separator to avoid collisions)
    mod_name = getattr(mod, "__name__", None)
    fn_name = getattr(func, "__name__", None)

    if not mod_name or not fn_name:
        # Fallback to qualname if name is missing (e.g. for some wrapped functions)
        fn_name = fn_name or getattr(func, "__qualname__", None)
        if not mod_name or not fn_name:
            raise RuntimeError(
                f"Could not determine module or function name for hashing: "
                f"module={mod_name}, func={fn_name}. "
                "Ensure @cell functions are defined at the module level."
            )

    deps, external_pkgs = get_module_dependencies(mod, root)
    hasher = hashlib.sha1()
    hasher.update(f"{mod_name}:{fn_name}".encode("utf-8"))

    # 1. Project file hashes
    # Sort paths for deterministic hash
    for p in sorted(deps):
        h = get_project_file_hash(p)
        hasher.update(h.encode("utf-8"))

    # 2. External package versions (already formatted as name==version)
    for pkg_info in sorted(external_pkgs):
        hasher.update(pkg_info.encode("utf-8"))

    # 3. Python interpreter version
    hasher.update(sys.version.encode("utf-8"))

    res = hasher.hexdigest()
    result = (res, deps, external_pkgs)
    _SOURCE_HASH_CACHE[func] = result
    return result


# Cache for function signatures and source hashes
_SIG_CACHE: Dict[Callable[..., Any], inspect.Signature] = {}
# Cache for function signatures and source hashes: func -> (hash_prefix, deps, external_pkgs)
_FUNC_SOURCE_HASH_CACHE: Dict[Callable[..., Any], Tuple[str, Set[Path], Set[str]]] = {}


def compute_cell_name(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    is_partial: bool = False,
) -> tuple[str, dict[str, str], Set[Path], Set[str]]:
    """Compute a unique deterministic name for a cell function and its arguments.
    Returns (unique_name, flattened_args, deps, external_pkgs)."""
    if func not in _SIG_CACHE:
        _SIG_CACHE[func] = inspect.signature(func)
    sig = _SIG_CACHE[func]
    if is_partial:
        bound_args = sig.bind_partial(*args, **kwargs)
    else:
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

    # 1. Source hash (File-based with transitive dependencies)
    if func not in _FUNC_SOURCE_HASH_CACHE:
        mod = inspect.getmodule(func)
        mod_file = getattr(mod, "__file__", None)
        root = _get_project_root(mod_file if mod_file is not None else ".")
        h, deps, external_pkgs = get_total_source_hash(func, root)
        _FUNC_SOURCE_HASH_CACHE[func] = (h[:8], deps, external_pkgs)

    source_hash, deps, external_pkgs = _FUNC_SOURCE_HASH_CACHE[func]

    # 2. Parameter hash
    param_hasher = hashlib.sha1()
    flattened_args = {}
    for key, value in sorted(bound_args.arguments.items()):
        val_str = _get_hash_string(value)
        param_hasher.update(f"{key}={val_str}".encode("utf-8"))
        flattened_args[key] = val_str

    param_hash = param_hasher.hexdigest()[:8]
    suffix = "_partial" if is_partial else ""
    return (
        f"{getattr(func, '__name__', 'unknown')}{suffix}_{param_hash}_{source_hash}",
        flattened_args,
        deps,
        external_pkgs,
    )


@lru_cache(maxsize=None)
def _get_project_root(path: str) -> Path:
    """Find the project root by looking for common markers."""
    p = Path(path).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return p.parent


def _get_hash_string(value: Any) -> str:
    """Recursively generate a deterministic string for hashing."""
    from gdswell.cell import Cell
    from gdswell.future_cell import FutureCell

    t = type(value)

    # 1. Fast path for primitive types
    if t is float:
        return repr(value)
    if t is int or t is str or t is bool:
        return str(value)
    if value is None:
        return "None"

    # 2. Fast path for objects with _hash_string property (CrossSection, LayerSection)
    if hasattr(value, "_hash_string"):
        # We use getattr because it's a cached_property
        return str(value._hash_string)

    # 3. Fast path for Cell and FutureCell
    if t is Cell or t is FutureCell:
        if t is FutureCell:
            return cast(str, object.__getattribute__(value, "_unique_name"))
        return value.name

    if t is functools.partial or (callable(value) and hasattr(value, "__name__")):
        p_args: list[Any] = []
        p_kw: dict[str, Any] = {}
        val = value

        # Unwrap partials
        while isinstance(val, functools.partial):
            p_args = list(val.args) + p_args
            new_kw = val.keywords.copy()
            new_kw.update(p_kw)
            p_kw = new_kw
            val = val.func

        # Flatten function/partial to its cell name
        # We use is_partial=True because we don't know if this partial is "complete" yet.
        # Even if it is complete, hashing it as a partial is safer here.
        name, _, _, _ = compute_cell_name(val, tuple(p_args), p_kw, is_partial=True)
        return name

    elif t is dict:
        return (
            "{"
            + ", ".join(
                f"{_get_hash_string(k)}: {_get_hash_string(v)}" for k, v in sorted(value.items())
            )
            + "}"
        )
    elif t is list or t is tuple:
        items = ", ".join(_get_hash_string(v) for v in value)
        return f"[{items}]" if t is list else f"({items})"
    elif isinstance(value, float):
        return repr(value)
    else:
        # Check for hashability to fail early on unhashable types if they don't have a custom repr
        # This ensures deterministic caching and avoids non-hashable inputs like sets or dicts
        # from being used as cell parameters unless they are specifically handled above.
        try:
            hash(value)
        except TypeError:
            raise TypeError(
                f"Value of type {type(value)} is not hashable and cannot be used "
                f"as a parameter to a @cell decorated function: {value!r}"
            )
        # Fallback to repr for custom objects that provide a deterministic one (like dataclasses)
        return repr(value)
