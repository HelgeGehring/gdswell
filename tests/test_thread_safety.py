# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import threading
import time

import gdswell as gw


def test_layout_thread_safety() -> None:
    layout = gw.Layout("shared_layout")

    success: list[bool] = []

    def worker(i: int) -> None:
        try:
            with layout:
                assert gw.ACTIVE_LAYOUT.get() is layout
                time.sleep(0.02)
                assert gw.ACTIVE_LAYOUT.get() is layout
            assert gw.ACTIVE_LAYOUT.get() is None
            success.append(True)
        except Exception as e:
            print(f"Worker {i} failed: {e}")
            raise

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(success) == 10
    print("test_layout_thread_safety passed")


def test_layout_reentrancy() -> None:
    layout = gw.Layout("reentrant_layout")

    with layout:
        assert gw.ACTIVE_LAYOUT.get() is layout
        with layout:
            assert gw.ACTIVE_LAYOUT.get() is layout
        assert gw.ACTIVE_LAYOUT.get() is layout
    assert gw.ACTIVE_LAYOUT.get() is None
    print("test_layout_reentrancy passed")


def test_default_layout_thread_safety() -> None:
    gw.Layout._default_layout = None  # Reset

    layouts = []

    def worker() -> None:
        # sleep slightly to enforce race condition if lock was missing
        time.sleep(0.01)
        layouts.append(gw.Layout.get_default())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(layouts) == 10
    first = layouts[0]
    for layout in layouts:
        assert layout is first
    print("test_default_layout_thread_safety passed")


if __name__ == "__main__":
    test_layout_thread_safety()
    test_layout_reentrancy()
    test_default_layout_thread_safety()
    print("All tests passed!")
