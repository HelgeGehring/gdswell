# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import os
from pathlib import Path


class Config:
    def __init__(self) -> None:
        # Default cache directory: ./.gdswell_cache (project folder)
        self.default_cache_dir = Path(".gdswell_cache")

        # Environment variable to override the cache directory
        self.cache_dir = Path(os.getenv("GDSWELL_CACHE_DIR", self.default_cache_dir))

        # Whether disk caching is enabled by default
        self.use_disk_cache = os.getenv("GDSWELL_DISK_CACHE", "1").lower() in (
            "1",
            "true",
            "yes",
        )

        # Whether cell generation is asynchronous by default
        self.async_cells = os.getenv("GDSWELL_ASYNC_CELLS", "1").lower() in (
            "1",
            "true",
            "yes",
        )

        # Max workers for parallel cell generation.
        # We use a very large default so there's practically no limit on thread count,
        # unless explicitly overridden by the environment.
        max_workers_env = os.getenv("GDSWELL_MAX_WORKERS")
        self.max_workers = int(max_workers_env) if max_workers_env is not None else 1_000_000

        # Whether to write extra debug information to the cache (like .dep files)
        self.debug_cache = os.getenv("GDSWELL_DEBUG_CACHE", "0").lower() in (
            "1",
            "true",
            "yes",
        )


# Global config instance
config = Config()


def clear_cache() -> None:
    """Delete all files in the cache directory."""
    if config.cache_dir.exists():
        import shutil

        shutil.rmtree(config.cache_dir)
        config.cache_dir.mkdir(parents=True, exist_ok=True)
