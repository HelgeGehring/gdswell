# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.straight import straight
from gdswell.routing import route_manhattan


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)


DEFAULT_XS = gw.CrossSection((gw.LayerSection("core", MyLayers.WG, 0.5),))

# Let's instead use a custom straight/bend function that we can track.
call_counts = {"straight": 0, "bend": 0}


def my_straight(xs, length):
    call_counts["straight"] += 1
    return straight(xs, length)


def my_bend(xs, radius, angle):
    call_counts["bend"] += 1
    return bend_circular(xs, radius, angle)


def test_routing_caching_optimization():
    call_counts["straight"] = 0
    call_counts["bend"] = 0

    p1 = gw.Port("p1", (0, 0), 0, DEFAULT_XS)
    p2 = gw.Port("p2", (100, 50), 180, DEFAULT_XS)
    radius = 10.0

    with gw.Layout() as layout:
        c = layout.create_cell()

        print("\nFirst routing call (cache miss)...")
        route_manhattan(
            c, p1, p2, radius, cross_section=DEFAULT_XS, bend=my_bend, straight=my_straight
        )

        count1_s = call_counts["straight"]
        count1_b = call_counts["bend"]
        print(f"  Calls: straight={count1_s}, bend={count1_b}")
        assert count1_s > 0
        assert count1_b > 0

        print("\nSecond routing call (should be a top-level cache hit in chain_components)...")
        route_manhattan(
            c, p1, p2, radius, cross_section=DEFAULT_XS, bend=my_bend, straight=my_straight
        )

        assert call_counts["straight"] == count1_s
        assert call_counts["bend"] == count1_b

        print(
            "\nThird routing call"
            "(different absolute position, same relative - should be a CACHE HIT now!)..."
        )
        # Shift both ports by 500, 500. Relative dx, dy remains (100, 50).
        p1_shifted = gw.Port("p1_s", (500, 500), 0, DEFAULT_XS)
        p2_shifted = gw.Port("p2_s", (600, 550), 180, DEFAULT_XS)

        route_manhattan(
            c,
            p1_shifted,
            p2_shifted,
            radius,
            cross_section=DEFAULT_XS,
            bend=my_bend,
            straight=my_straight,
        )

        # If relative caching works, the call counts for the underlying my_straight/my_bend
        # should NOT have increased because they are called by chain_components(comps),
        # and 'comps' for the relative route should be identical.
        assert call_counts["straight"] == count1_s, (
            f"Expected cache hit for shifted route, "
            f"but got {call_counts['straight'] - count1_s} more straight calls"
        )
        assert call_counts["bend"] == count1_b, (
            f"Expected cache hit for shifted route, "
            f"but got {call_counts['bend'] - count1_b} more bend calls"
        )


if __name__ == "__main__":
    test_routing_caching_optimization()
    print("\nCaching optimization verified!")
