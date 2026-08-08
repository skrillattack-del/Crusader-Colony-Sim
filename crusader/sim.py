"""Simulation facade: owns all managers, advances the world, saves/loads.

Usage:
    sim = Simulation(seed=42, pawns=1000)
    sim.setup()
    for _ in range(years * 360):
        sim.tick()
"""
from __future__ import annotations

import pickle
import time

from .engine import GameDate, RNG, EventBus, Scheduler
from .worldgen import generate_world, BIOME_OCEAN, BIOME_DEEP_OCEAN
from .population import Population
from .dynasty import DynastyManager
from .religion import ReligionManager
from .diplomacy import DiplomacyManager
from .war import WarEngine
from .economy import EconomyManager
from .tech import TechManager
from .crafting import CraftingManager
from .dialogue import DialogueEngine


class Simulation:
    def __init__(self, seed: int = 867, pawns: int = 1000,
                 map_size: int = 192, n_continents: int = 3,
                 n_faiths: int = 4):
        self.seed = seed
        self.rng = RNG(seed)
        self.date = GameDate(0)
        self.bus = EventBus()
        self.scheduler = Scheduler()
        self.pawn_target = pawns
        self.map_size = map_size
        self.n_continents = n_continents
        self.n_faiths = n_faiths

        self.world = None
        self.population = Population(self)
        self.dynasties = DynastyManager(self)
        self.religion = ReligionManager(self)
        self.diplomacy = DiplomacyManager(self)
        self.war_engine = WarEngine(self)
        self.economy = EconomyManager(self)
        self.tech = TechManager(self)
        self.crafting = CraftingManager(self)
        self.dialogue = DialogueEngine(self)
        self.stats = {"ticks": 0, "births": 0, "deaths": 0, "wars": 0}
        self._setup_done = False

    # ---------------- setup ----------------
    def setup(self):
        if self._setup_done:
            return
        t0 = time.perf_counter()
        self.world = generate_world(self.rng, self.map_size, self.map_size,
                                    n_continents=self.n_continents)
        land_provs = [p.pid for p in self.world.provinces]
        faith_ids = self.religion.found_faiths(self.rng, self.n_faiths,
                                               land_provs)
        self.dynasties.found_world(self.rng, land_provs, faith_ids)
        # seed commoners
        self.population.seed(self.rng, self.pawn_target, self.date.day,
                             land_provs)
        # assign faiths to commoners near holy sites
        for p in self.population.living():
            if p.faith is None:
                prov = self.world.provinces[p.province]
                best, bd = None, 1e18
                for fid, f in self.religion.faiths.items():
                    for site in f.holy_sites:
                        s = self.world.provinces[site]
                        d = (prov.cx - s.cx) ** 2 + (prov.cy - s.cy) ** 2
                        if d < bd:
                            best, bd = fid, d
                p.faith = best if best is not None else faith_ids[0]
        # track vital stats
        self._setup_done = True
        self.gen_seconds = time.perf_counter() - t0

    def _bump(self, key):
        self.stats[key] += 1

    # ---------------- ticks ----------------
    def tick(self):
        """Advance one day."""
        day = self.date.day
        self.stats["ticks"] += 1
        self.population.daily(day)
        self.war_engine.daily()
        self.scheduler.run_due(day)
        if self.date.is_new_month() and day > 0:
            self.population.monthly(day)
            self.economy.monthly()
            self.crafting.monthly()
            self.religion.monthly()
            self.religion.piety_tick()
            self.tech.monthly()
            self.diplomacy.monthly()
        if self.date.is_new_year() and day > 0:
            self.population.yearly(day)
            self.diplomacy.yearly()
        self.date.day += 1

    def run(self, years: float, callback=None, step_days: int = 30):
        days = int(years * 360)
        for i in range(days):
            self.tick()
            if callback and i % step_days == 0:
                callback(self, i, days)

    # ---------------- persistence ----------------
    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> "Simulation":
        with open(path, "rb") as f:
            return pickle.load(f)

    # ---------------- reporting ----------------
    def summary(self) -> dict:
        pop = self.population
        living = list(pop.living())
        rulers = [pop.get(pid) for pid in self.dynasties.rulers]
        rulers = [r for r in rulers if r]
        active_wars = [w for w in self.diplomacy.wars if w.active]
        return {
            "date": str(self.date),
            "living_pawns": len(living),
            "recorded_dead": len(pop.dead_by_pid),
            "births": self.stats["births"],
            "deaths": self.stats["deaths"],
            "provinces": len(self.world.provinces),
            "titles": len(self.dynasties.titles),
            "kingdoms": len(rulers),
            "active_wars": len(active_wars),
            "total_wars": len(self.diplomacy.wars),
            "faiths": {f.name: sum(1 for p in living if p.faith == f.fid)
                       for f in self.religion.faiths.values()},
            "innovations_known_all_realms": sum(len(v) for v in self.tech.known_by.values()),
            "innovation_total": self.tech.count(),
            "techniques_total": self.tech.technique_count(),
            "recipes_total": self.crafting.count(),
            "avg_age": (sum(p.age(self.date.day) for p in living)
                        / max(1, len(living))),
            "rulers": [f"{r.display_name()} ({self.dynasties.top_title(r).name})"
                       if self.dynasties.top_title(r) else r.display_name()
                       for r in rulers],
        }
