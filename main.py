"""Crusader Colony Sim — entry point.

Examples:
    python main.py --mode headless --pawns 1000 --years 20
    python main.py --mode gui --pawns 1000
    python main.py --mode 3d
    python main.py --mode headless --years 50 --save world.pkl
    python main.py --mode gui --load world.pkl
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from crusader.sim import Simulation


def headless(sim: Simulation, years: float, save: str | None,
             export: str | None):
    t0 = time.perf_counter()
    last = [t0]

    def progress(s, i, total):
        now = time.perf_counter()
        if now - last[0] >= 2.0:
            last[0] = now
            pop = len(s.population.pawns)
            wars = sum(1 for w in s.diplomacy.wars if w.active)
            print(f"  {s.date}  pawns={pop}  wars={wars}  "
                  f"ticks/s={s.stats['ticks'] / max(0.01, now - t0):.0f}")

    print(f"Generating world (seed={sim.seed}, map={sim.map_size}^2, "
          f"continents={sim.n_continents})...")
    sim.setup()
    print(f"World ready in {sim.gen_seconds:.1f}s: "
          f"{len(sim.world.provinces)} provinces, "
          f"{len(sim.population.pawns)} pawns, "
          f"{len(sim.dynasties.titles)} titles.")
    print(f"Simulating {years} years...")
    try:
        sim.run(years, callback=progress)
    except Exception:
        # crash dump: preserve the exact world state for debugging
        dump = "crash_dump.pkl"
        try:
            sim.save(dump)
            print(f"\nCRASH at {sim.date} — world state saved to {dump}")
        except Exception:
            print(f"\nCRASH at {sim.date} — could not save dump")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    dt = time.perf_counter() - t0
    summ = sim.summary()
    print("\n===== WORLD SUMMARY =====")
    for k, v in summ.items():
        if k == "rulers":
            print(f"  rulers:")
            for r in v:
                print(f"    - {r}")
        else:
            print(f"  {k}: {v}")
    print(f"\nPerformance: {sim.stats['ticks']} ticks in {dt:.1f}s "
          f"({sim.stats['ticks'] / dt:.0f} days/s)")
    print("\n===== CHRONICLE (last 25) =====")
    for line in sim.bus.chronicle[-25:]:
        print(" ", line)
    print("\n===== SAMPLE DIALOGUE (offline/LLM) =====")
    import random
    pop = list(sim.population.living())
    if len(pop) >= 2:
        a, b = sim.rng.sample(pop, 2)
        for line in sim.dialogue.converse(a, b, turns=4):
            print(" ", line)
    if save:
        sim.save(save)
        print(f"\nSaved to {save}")
    if export:
        with open(export, "w", encoding="utf-8") as f:
            json.dump(summ, f, indent=2, default=str)
        print(f"Summary exported to {export}")


def main():
    ap = argparse.ArgumentParser(description="Crusader Colony Sim")
    ap.add_argument("--mode", choices=["gui", "headless", "3d", "web"],
                    default="gui")
    ap.add_argument("--host", type=str, default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(__import__("os").environ.get("PORT", 8080)))
    ap.add_argument("--pawns", type=int, default=1000)
    ap.add_argument("--years", type=float, default=20)
    ap.add_argument("--seed", type=int, default=867)
    ap.add_argument("--map-size", type=int, default=192)
    ap.add_argument("--continents", type=int, default=3)
    ap.add_argument("--faiths", type=int, default=4)
    ap.add_argument("--days-per-frame", type=int, default=3)
    ap.add_argument("--speed", type=float,
                    default=float(__import__("os").environ.get("DAYS_PER_SEC", 15)),
                    help="web mode: simulated days per second")
    ap.add_argument("--save", type=str, default=None)
    ap.add_argument("--export", type=str, default=None)
    ap.add_argument("--load", type=str, default=None)
    args = ap.parse_args()

    if args.load:
        sim = Simulation.load(args.load)
        print(f"Loaded {args.load} at {sim.date}")
    else:
        sim = Simulation(seed=args.seed, pawns=args.pawns,
                         map_size=args.map_size, n_continents=args.continents,
                         n_faiths=args.faiths)
        sim.setup()

    if args.mode == "headless":
        headless(sim, args.years, args.save, args.export)
    elif args.mode == "web":
        from crusader.webserver import serve
        serve(sim, host=args.host, port=args.port, days_per_sec=args.speed)
    elif args.mode == "gui":
        from crusader.render2d import MapViewer
        MapViewer(sim, days_per_frame=args.days_per_frame).run()
    elif args.mode == "3d":
        from crusader.render3d import Scene3D
        Scene3D(sim).run()


if __name__ == "__main__":
    main()
