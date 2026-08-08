"""Warfare: wars with war-score, armies that march on the province graph,
battles with terrain/commander modifiers, and full siege simulation
(approach -> bombardment -> breach -> assault or starvation).
"""
from __future__ import annotations

import math

# unit stats: (damage, toughness, morale, siege)
UNIT_TYPES = {
    "levy":       (1.0, 1.0, 1.0, 0.0),
    "spearmen":   (1.6, 1.8, 1.3, 0.0),
    "archers":    (2.0, 0.8, 1.1, 0.0),
    "light_cav":  (2.2, 1.2, 1.4, 0.0),
    "knights":    (3.5, 3.0, 1.8, 0.0),
    "pikemen":    (1.8, 2.4, 1.3, 0.0),
    "siege_train": (0.5, 0.5, 0.8, 3.0),
}

TERRAIN_DEFENSE = {"hills": 1.25, "mountain": 1.6, "forest": 1.15,
                   "marsh": 1.2, "river": 1.3}


class Army:
    _next_id = 0

    def __init__(self, ruler_pid, province, units=None, commander=None):
        self.aid = Army._next_id
        Army._next_id += 1
        self.ruler = ruler_pid
        self.province = province
        self.units = units or {"levy": 300}
        self.commander = commander
        self.morale = 1.0
        self.path: list[int] = []
        self.move_progress = 0.0
        self.siege_target = None
        self.in_battle = False

    @property
    def size(self) -> int:
        return sum(self.units.values())

    def strength(self) -> float:
        return sum(UNIT_TYPES.get(u, UNIT_TYPES["levy"])[0] * n
                   for u, n in self.units.items()) * self.morale

    def toughness(self) -> float:
        return sum(UNIT_TYPES.get(u, UNIT_TYPES["levy"])[1] * n
                   for u, n in self.units.items())

    def siege_power(self) -> float:
        return sum(UNIT_TYPES.get(u, UNIT_TYPES["levy"])[3] * n
                   for u, n in self.units.items())

    def take_losses(self, rng, frac: float):
        for u in list(self.units):
            lost = int(self.units[u] * frac * rng.uniform(0.7, 1.3))
            self.units[u] = max(0, self.units[u] - lost)
            if self.units[u] == 0:
                del self.units[u]


class Siege:
    """Phases: approach -> bombard -> breached -> assault; starvation timer."""

    def __init__(self, army: Army, province):
        self.army = army
        self.province = province
        self.progress = 0.0          # 0..fort_level*100
        self.max_progress = province.fort_level * 100
        self.breached = False
        self.starve_days = 0
        self.garrison = 80 * province.fort_level
        self.phase = "approach"

    def tick(self, rng, days: float) -> bool:
        """Returns True when the holding falls."""
        p = self.province
        if self.phase == "approach":
            self.phase = "bombard"
        # starvation & disease attrition on attackers
        self.starve_days += days
        if self.starve_days > 120:
            self.army.take_losses(rng, 0.004 * days)
        # garrison starvation
        if self.starve_days > 300:
            self.garrison -= self.garrison * 0.002 * days
            if self.garrison < 5:
                self.phase = "starved_out"
                return True
        # siege weapons grind the walls
        rate = (2.0 + self.army.siege_power() * 0.05) * days
        # defenders repair
        rate -= p.fort_level * 0.8 * days
        self.progress = min(self.max_progress,
                            max(0.0, self.progress + rate))
        if self.progress >= self.max_progress * 0.6 and not self.breached:
            if rng.chance(0.02 * days + self.army.siege_power() * 0.0002):
                self.breached = True
                self.phase = "breached"
        if self.breached:
            # assault resolution
            atk = self.army.strength()
            dfn = self.garrison * UNIT_TYPES["spearmen"][1] \
                * TERRAIN_DEFENSE.get(p.biome, 1.0)
            if atk > dfn * 1.5:
                self.army.take_losses(rng, 0.06)
                self.phase = "stormed"
                return True
            else:
                self.army.take_losses(rng, 0.02 * days)
                self.garrison -= self.garrison * 0.01 * days
                if self.garrison < 10:
                    self.phase = "stormed"
                    return True
        if self.progress >= self.max_progress:
            self.phase = "surrendered"
            return True
        return False


class War:
    def __init__(self, sim, attacker, defender, title, cb):
        self.sim = sim
        self.attackers = [attacker.pid]
        self.defenders = [defender.pid]
        self.title = title
        self.cb = cb
        self.score = 0.0             # -100..100, positive = attacker winning
        self.active = True
        self.start_day = sim.date.day
        self.outcome = None          # attacker | defender | white
        self.battles = 0
        self.occupied: set[int] = set()

    def involves(self, pid):
        return pid in self.attackers or pid in self.defenders

    def hostile(self, a, b):
        return (a in self.attackers and b in self.defenders) or \
               (b in self.attackers and a in self.defenders)

    def side(self, pid):
        if pid in self.attackers:
            return "attackers"
        if pid in self.defenders:
            return "defenders"
        return None

    def add_score(self, v):
        self.score = max(-100.0, min(100.0, self.score + v))

    def daily(self, days):
        # ticking warscore toward the side holding the contested land
        if self.title is not None:
            held = sum(1 for p in self.title.provinces if p in self.occupied)
            frac = held / max(1, len(self.title.provinces))
            self.add_score((frac - 0.25) * 0.05 * days)
        if self.score >= 100:
            self.end("attacker")
        elif self.score <= -100:
            self.end("defender")
        elif self.sim.date.day - self.start_day > 8 * 360 \
                and abs(self.score) < 20:
            self.end("white")

    def end(self, outcome):
        self.active = False
        self.outcome = outcome
        # release occupations
        for pid in self.occupied:
            prov = self.sim.world.provinces[pid]
            prov.controller = None
        self.occupied.clear()


class WarEngine:
    """Owns armies and resolves movement, battles, sieges on the map."""

    def __init__(self, sim):
        self.sim = sim
        self.armies: list[Army] = []
        self.sieges: list[Siege] = []

    # ---- raising & moving ----
    def raise_army(self, ruler) -> Army:
        dyn = self.sim.dynasties
        title = dyn.top_title(ruler)
        if title is None:
            return None
        levies = 150 * len(title.provinces)
        units = {"levy": levies,
                 "spearmen": int(levies * 0.15),
                 "archers": int(levies * 0.12),
                 "light_cav": int(levies * 0.05)}
        if ruler.prestige > 400:
            units["knights"] = max(1, int(ruler.skills["prowess"]))
        if self.sim.tech.knows(ruler, "siege_engineering"):
            units["siege_train"] = 5
        army = Army(ruler.pid, title.provinces[0], units, commander=ruler.pid)
        self.armies.append(army)
        return army

    def on_war_declared(self, war: War):
        pop = self.sim.population
        for pid in war.attackers + war.defenders:
            ruler = pop.get(pid)
            if ruler is None:
                continue
            army = self.raise_army(ruler)
            if army is None:
                continue
            # attackers march on the contested title; defenders rally home
            if war.title is not None and pid in war.attackers:
                target = war.title.provinces[0]
                self.order_move(army, target)
                army.siege_target = target

    def order_move(self, army: Army, target_prov: int):
        path = self.sim.world.province_path(army.province, target_prov)
        if path:
            army.path = path[1:]

    # ---- daily ----
    def daily(self):
        rng = self.sim.rng
        wm = self.sim.world
        pop = self.sim.population
        # movement
        for army in self.armies:
            if army.in_battle or not army.path:
                continue
            army.move_progress += 1.0
            if army.move_progress >= 4:      # ~4 days per province
                army.move_progress = 0.0
                nxt = army.path.pop(0)
                army.province = nxt
                if not army.path and army.siege_target == nxt:
                    self.start_siege(army, wm.provinces[nxt])
        # battles: hostile armies in same province
        by_prov = {}
        for a in self.armies:
            by_prov.setdefault(a.province, []).append(a)
        for pid, group in by_prov.items():
            if len(group) < 2:
                continue
            hostiles = [(a, b) for i, a in enumerate(group) for b in group[i + 1:]
                        if self.sim.diplomacy.at_war(a.ruler, b.ruler)]
            for a, b in hostiles:
                self.resolve_battle(a, b, wm.provinces[pid])
        # sieges
        for s in list(self.sieges):
            if s.army not in self.armies or s.army.size <= 0:
                self.sieges.remove(s)
                continue
            if s.tick(rng, 1.0):
                self.capture_holding(s)
        # cleanup destroyed armies
        self.armies = [a for a in self.armies if a.size > 20]

    def resolve_battle(self, a: Army, b: Army, province):
        rng = self.sim.rng
        pop = self.sim.population
        war = self.sim.diplomacy.war_between(a.ruler, b.ruler)
        a.in_battle = b.in_battle = True
        ca = pop.get(a.commander)
        cb_ = pop.get(b.commander)
        adv_a = (ca.skills["martial"] if ca else 5) * 0.03
        adv_b = (cb_.skills["martial"] if cb_ else 5) * 0.03
        terr = TERRAIN_DEFENSE.get(province.biome, 1.0)
        if province.river:
            terr *= TERRAIN_DEFENSE["river"]
        days = 0
        while a.size > 20 and b.size > 20 and days < 12:
            days += 1
            dmg_a = a.strength() * (1 + adv_a) / max(1.0, b.toughness() * terr)
            dmg_b = b.strength() * (1 + adv_b) * terr / max(1.0, a.toughness())
            a.take_losses(rng, min(0.25, dmg_b / max(1, a.size) * 0.05))
            b.take_losses(rng, min(0.25, dmg_a / max(1, b.size) * 0.05))
            a.morale -= dmg_b * 0.0004
            b.morale -= dmg_a * 0.0004
            if a.morale <= 0.2 or b.morale <= 0.2:
                break
        # resolve
        if a.size >= b.size:
            winner, loser = a, b
        else:
            winner, loser = b, a
        loser.take_losses(rng, 0.15)   # pursuit
        loser.morale = 0.5
        winner.morale = min(1.0, winner.morale + 0.2)
        # rout: loser flees to a friendly neighboring province
        self.rout(loser)
        a.in_battle = b.in_battle = False
        if war:
            war.battles += 1
            war.add_score(12 if winner.ruler in war.attackers else -12)
        # knights/pawns die in battle
        for army, frac in ((a, 0.01), (b, 0.03)):
            cmd = pop.get(army.commander)
            if cmd and rng.chance(frac):
                pop.kill(cmd, self.sim.date.day, "slain in battle")
        wn = pop.get(winner.ruler)
        ln = pop.get(loser.ruler)
        if war and war.battles <= 6 and wn and ln:
            self.sim.bus.record(
                self.sim.date,
                f"Battle of {province.name}: {wn.display_name()} defeats "
                f"{ln.display_name()} "
                f"({a.size + b.size} men took the field).", "war")

    def rout(self, army: Army):
        prov = self.sim.world.provinces[army.province]
        friends = []
        for nb in prov.neighbors:
            ruler = self.sim.dynasties.ruler_of_province(nb)
            if ruler is None or not self.sim.diplomacy.war_between(
                    army.ruler, ruler.pid):
                friends.append(nb)
        if friends:
            army.province = self.sim.rng.choice(friends)
        army.path = []
        army.siege_target = None

    def start_siege(self, army: Army, province):
        for s in self.sieges:
            if s.province is province:
                return
        self.sieges.append(Siege(army, province))
        self.sim.bus.record(
            self.sim.date,
            f"The siege of {province.name} begins "
            f"(fort level {province.fort_level}).", "war")

    def capture_holding(self, siege: Siege):
        self.sieges.remove(siege)
        prov = siege.province
        prov.controller = siege.army.ruler
        war = None
        for w in self.sim.diplomacy.wars:
            if w.active and w.involves(siege.army.ruler):
                war = w
                break
        if war:
            war.occupied.add(prov.pid)
            war.add_score(8 if siege.army.ruler in war.attackers else -8)
            # march on the next holding of the contested title
            if war.title is not None:
                remaining = [p for p in war.title.provinces
                             if p not in war.occupied]
                if remaining:
                    self.order_move(siege.army, remaining[0])
                    siege.army.siege_target = remaining[0]
        self.sim.bus.record(
            self.sim.date,
            f"{prov.name} falls ({siege.phase.replace('_', ' ')}) after "
            f"{siege.starve_days:.0f} days of siege.", "war")
