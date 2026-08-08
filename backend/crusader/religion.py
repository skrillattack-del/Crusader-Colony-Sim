"""Religion: faiths with tenets & doctrines, piety, fervor, conversion,
head-of-faith, and holy-war hostility.
"""
from __future__ import annotations

from .names import faith_name

TENETS = [
    "armed_pilgrimages", "ancestor_worship", "pacifism", "human_sacrifice",
    "monasticism", "divine_marriage", "ritual_cannibalism", "astrology",
    "reincarnation", "esotericism", "warrior_cult", "charity",
]

DOCTRINE_SPECS = {
    "clerical_marriage": ["allowed", "forbidden"],
    "gender_view": ["male_dominated", "equal", "female_dominated"],
    "same_faith_opinion": [10, 20, 30],
    "pluralism": ["righteous", "pluralistic", "fundamentalist"],
    "head_of_faith": ["none", "temporal", "spiritual"],
    "marriage": ["monogamy", "polygamy", "consorts"],
}


class Faith:
    __slots__ = ("fid", "name", "tenets", "doctrines", "fervor",
                 "head", "holy_sites", "hostility")

    def __init__(self, fid, name, tenets, doctrines, holy_sites):
        self.fid = fid
        self.name = name
        self.tenets = tenets
        self.doctrines = doctrines
        self.fervor = 0.5
        self.head = None
        self.holy_sites = holy_sites
        self.hostility = {}   # other fid -> 0..1


class ReligionManager:
    def __init__(self, sim):
        self.sim = sim
        self.faiths: dict[int, Faith] = {}

    def found_faiths(self, rng, n: int, provinces) -> list[int]:
        for fid in range(n):
            tenets = rng.sample(TENETS, 3)
            doctrines = {k: rng.choice(v) for k, v in DOCTRINE_SPECS.items()}
            sites = rng.sample(provinces, min(3, len(provinces)))
            self.faiths[fid] = Faith(fid, faith_name(rng), tenets, doctrines, sites)
        # hostility matrix
        for a in self.faiths.values():
            for b in self.faiths.values():
                if a.fid == b.fid:
                    continue
                if a.doctrines["pluralism"] == "pluralistic" \
                        or b.doctrines["pluralism"] == "pluralistic":
                    a.hostility[b.fid] = 0.2
                elif a.doctrines["pluralism"] == "fundamentalist" \
                        or b.doctrines["pluralism"] == "fundamentalist":
                    a.hostility[b.fid] = 0.9
                else:
                    a.hostility[b.fid] = 0.5
        return list(self.faiths)

    def hostility(self, fid_a, fid_b) -> float:
        if fid_a == fid_b:
            return 0.0
        fa = self.faiths.get(fid_a)
        return fa.hostility.get(fid_b, 0.5) if fa else 0.5

    def opinion_between(self, a, b) -> int:
        if a.faith == b.faith:
            f = self.faiths.get(a.faith)
            return f.doctrines["same_faith_opinion"] if f else 10
        return int(-30 * self.hostility(a.faith, b.faith))

    # ---------- monthly ----------
    def monthly(self):
        rng = self.sim.rng
        pop = self.sim.population
        # fervor drifts toward size-based equilibrium
        counts = {fid: 0 for fid in self.faiths}
        total = 0
        for p in pop.living():
            if p.faith in counts:
                counts[p.faith] += 1
                total += 1
        for fid, f in self.faiths.items():
            share = counts[fid] / total if total else 0
            target = 0.3 + 0.6 * min(1.0, share * 3)
            f.fervor += (target - f.fervor) * 0.05

        # conversion: low-fervor faiths bleed members to local majority
        for p in pop.living():
            if rng.chance(0.0008):
                neighbors = [pop.get(i) for i in
                             list(pop.by_province.get(p.province, ()))[:12]]
                neighbors = [q for q in neighbors if q and q.faith != p.faith]
                if neighbors:
                    f = self.faiths.get(p.faith)
                    pressure = 1.0 - (f.fervor if f else 0.5)
                    if "cynical" in p.personality:
                        pressure += 0.2
                    if "zealous" in p.personality:
                        pressure -= 0.4
                    if rng.chance(max(0.02, pressure * 0.3)):
                        old = p.faith
                        p.faith = rng.choice(neighbors).faith
                        if p.is_ruler:
                            old_name = self.faiths.get(old)
                            self.sim.bus.record(
                                self.sim.date,
                                f"{p.display_name()} converts from "
                                f"{old_name.name if old_name else '?'} to "
                                f"{self.faiths[p.faith].name}!", "religion")

    def piety_tick(self):
        for p in self.sim.population.living():
            if p.job == "priest":
                p.piety += 1.0
