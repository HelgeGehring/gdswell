# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import threading
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CellStats:
    """Statistics for a single cell-generating function."""

    name: str
    calls: int = 0
    hits_memory: int = 0
    hits_disk: int = 0
    build_times: List[float] = field(default_factory=list)

    @property
    def hits_total(self) -> int:
        return self.hits_memory + self.hits_disk

    @property
    def avg_build_time(self) -> float:
        if not self.build_times:
            return 0.0
        return sum(self.build_times) / len(self.build_times)

    @property
    def min_build_time(self) -> float:
        if not self.build_times:
            return 0.0
        return min(self.build_times)

    @property
    def max_build_time(self) -> float:
        if not self.build_times:
            return 0.0
        return max(self.build_times)

    @property
    def compiles(self) -> int:
        return len(self.build_times)

    @property
    def total_time(self) -> float:
        return sum(self.build_times)


# Global registry for statistics
_stats_registry: Dict[str, CellStats] = {}
_stats_lock = threading.Lock()


def get_stats() -> Dict[str, CellStats]:
    """Return a copy of the current statistics."""
    return _stats_registry.copy()


def reset_stats() -> None:
    """Clear all statistics."""
    with _stats_lock:
        _stats_registry.clear()


def print_stats() -> None:
    """Print a formatted summary of the statistics."""
    if not _stats_registry:
        print("No cell statistics recorded.")
        return

    # Column widths (content only)
    w = {
        "func": 40,
        "calls": 5,
        "memh": 5,
        "memp": 6,
        "diskh": 5,
        "diskp": 6,
        "comp": 5,
        "build": 35,
        "total": 12,
    }

    # Box-drawing characters with padding (+2 for each col)
    def _border(left: str, mid: str, right: str) -> str:
        parts = [
            "─" * (w["func"] + 2),
            "─" * (w["calls"] + 2),
            "─" * (w["memh"] + 2),
            "─" * (w["memp"] + 2),
            "─" * (w["diskh"] + 2),
            "─" * (w["diskp"] + 2),
            "─" * (w["comp"] + 2),
            "─" * (w["build"] + 2),
            "─" * (w["total"] + 2),
        ]
        return left + mid.join(parts) + right

    def _row(cols: List[str]) -> str:
        return "│ " + " │ ".join(cols) + " │"

    header_box = _border("┌", "┬", "┐")
    separator_box = _border("├", "┼", "┤")
    footer_box = _border("└", "┴", "┘")

    print("\n" + header_box)
    header_cols = [
        f"{'Cell Function':<{w['func']}}",
        f"{'Calls':>{w['calls']}}",
        f"{'MemH':>{w['memh']}}",
        f"{'Mem%':>{w['memp']}}",
        f"{'DiskH':>{w['diskh']}}",
        f"{'Disk%':>{w['diskp']}}",
        f"{'Comp.':>{w['comp']}}",
        f"{'Build (min/avg/max)':^{w['build']}}",
        f"{'Total Time':>{w['total']}}",
    ]
    print(_row(header_cols))
    print(separator_box)

    for name, s in sorted(_stats_registry.items()):
        mem_rate = (s.hits_memory / s.calls * 100) if s.calls > 0 else 0
        disk_rate = (s.hits_disk / s.calls * 100) if s.calls > 0 else 0

        if s.build_times:
            times = (
                f"{s.min_build_time * 1000:7.2f}/"
                f"{s.avg_build_time * 1000:7.2f}/"
                f"{s.max_build_time * 1000:7.2f} ms"
            )
        else:
            times = "-"

        row_cols = [
            f"{name:<{w['func']}}",
            f"{s.calls:>{w['calls']}}",
            f"{s.hits_memory:>{w['memh']}}",
            f"{mem_rate:>5.1f}%",
            f"{s.hits_disk:>{w['diskh']}}",
            f"{disk_rate:>5.1f}%",
            f"{s.compiles:>{w['comp']}}",
            f"{times:^{w['build']}}",
            f"{s.total_time * 1000:9.2f} ms",
        ]
        print(_row(row_cols))

    # Calculate Totals
    total_calls = sum(s.calls for s in _stats_registry.values())
    total_memh = sum(s.hits_memory for s in _stats_registry.values())
    total_diskh = sum(s.hits_disk for s in _stats_registry.values())
    total_comp = sum(s.compiles for s in _stats_registry.values())
    total_mem_rate = (total_memh / total_calls * 100) if total_calls > 0 else 0
    total_disk_rate = (total_diskh / total_calls * 100) if total_calls > 0 else 0

    print(separator_box)
    total_cols = [
        f"{'TOTAL':<{w['func']}}",
        f"{total_calls:>{w['calls']}}",
        f"{total_memh:>{w['memh']}}",
        f"{total_mem_rate:>5.1f}%",
        f"{total_diskh:>{w['diskh']}}",
        f"{total_disk_rate:>5.1f}%",
        f"{total_comp:>{w['comp']}}",
        f"{'-':^{w['build']}}",
        "",
    ]
    print(_row(total_cols))
    print(footer_box + "\n")


def _record_call(func_name: str) -> None:
    with _stats_lock:
        if func_name not in _stats_registry:
            _stats_registry[func_name] = CellStats(name=func_name)
        _stats_registry[func_name].calls += 1


def _record_hit_memory(func_name: str) -> None:
    with _stats_lock:
        if func_name in _stats_registry:
            _stats_registry[func_name].hits_memory += 1


def _record_hit_disk(func_name: str) -> None:
    with _stats_lock:
        if func_name in _stats_registry:
            _stats_registry[func_name].hits_disk += 1


def _record_build_time(func_name: str, duration: float) -> None:
    with _stats_lock:
        if func_name in _stats_registry:
            _stats_registry[func_name].build_times.append(duration)
