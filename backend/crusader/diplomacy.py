"""Diplomacy: inter-ruler opinions, alliances, casus belli, war declaration,
peace terms, succession crises.
"""
from __future__ import annotations

from .war import War


class DiplomacyManager:
    def __init__(self, sim):
        self.sim = sim
        self.alliances: set[frozenset] = set()     # frozenset({pidA, pidB})
        self.wars: list[War] = []
        self.truces: dict[frozenset, int] = {}     # pair -> truce end day

    # ---------- opinions ----------
    def ruler_opinion(self, a, b) -> int:
        op = a.opinion_of(b)
        op += self.sim.religion.opinion_between(a, b)
        pair = frozenset((a.pid, b.pid))
        if pair in self.alliances:
            op += 40
        if self.at_war(a.pid, b.pid):
            op -= 60
        if a.liege == b.pid or b.liege == a.pid:
            op += 10
        if pair in self.truces and self.truces[pair] > self.sim.date.day:
            op += 15
        # border friction
        ta = self.sim.dynasties.top_title(a)
        tb = self.sim.dynasties.top_title(b)
        if ta and tb and set(ta.provinces) & set(tb.provinces):
            op -= 25
        return max(-100, min(100, op))

    def at_war(self, pid_a, pid_b) -> bool:
        for w in self.wars:
            if w.active and w.involves(pid_a) and w.involves(pid_b) \
                    and w.hostile(pid_a, pid_b):
                return True
        return False

    def war_between(self, pid_a, pid_b) -> War | None:
        for w in self.wars:
            if w.active and w.hostile(pid_a, pid_b):
                return w
        return None

    # ---------- events ----------
    def on_marriage(self, a, b):
        """Ruler marriages create alliances between their houses' rulers."""
        if a.is_ruler and b.is_ruler and a.pid != b.pid:
            self.alliances.add(frozenset((a.pid, b.pid)))
        else:
            # alliance between rulers of the two houses
            ra = self.sim.dynasties.ruler_of_province(a.province)
            rb = self.sim.dynasties.ruler_of_province(b.province)
            if ra and rb and ra.pid != rb.pid:
                self.alliances.add(frozenset((ra.pid, rb.pid)))
                self.sim.bus.record(
                    self.sim.date,
                    f"Marriage alliance forged between {ra.display_name()} "
                    f"and {rb.display_name()}.", "diplomacy")

    def on_succession(self, old_ruler, titles):
        """Claimants may immediately press claims; neighbors may pounce."""
        rng = self.sim.rng
        day = self.sim.date.day
        pop = self.sim.population
        for title in titles:
            heir = pop.get(title.holder)
            if heir is None:
                continue
            for claimant_pid in list({c for k in pop.living() for c in [k.pid]
                                      if title.tid in k.claims}):
                claimant = pop.get(claimant_pid)
                if claimant is None or claimant.pid == heir.pid:
                    continue
                strength = claimant.skills["martial"] + claimant.prestige * 0.01
                if "ambitious" in claimant.personality:
                    strength += 10
                if strength > 12 and rng.chance(0.15):
                    self.declare_war(claimant, heir, title,
                                     cb="pressed_claim")

    # ---------- monthly AI ----------
    def monthly(self):
        rng = self.sim.rng
        day = self.sim.date.day
        rulers = [pop_r for pop_r in (self.sim.population.get(pid)
                                      for pid in self.sim.dynasties.rulers)
                  if pop_r is not None]
        rng.shuffle(rulers)
        for r in rulers:
            # consider war against a neighbor with a valid CB
            cb_target, cb_title, cb_kind = self.find_cb(r)
            if cb_target is None:
                continue
            op = self.ruler_opinion(r, cb_target)
            aggressiveness = 0.15
            if "ambitious" in r.personality:
                aggressiveness += 0.25
            if "brave" in r.personality:
                aggressiveness += 0.1
            if "wrathful" in r.personality and op < -30:
                aggressiveness += 0.2
            if op > 20:
                continue
            if self.truces.get(frozenset((r.pid, cb_target.pid)), 0) > day:
                continue
            if rng.chance(aggressiveness * 0.12):
                self.declare_war(r, cb_target, cb_title, cb=cb_kind)

        # tick wars
        for w in list(self.wars):
            if w.active:
                w.daily(30)  # monthly granularity
                if not w.active:
                    self._settle_peace(w)

    def find_cb(self, ruler):
        """Return (defender, title, cb_kind) or (None, None, None)."""
        pop = self.sim.population
        dyn = self.sim.dynasties
        rel = self.sim.religion
        # pressed claim
        for tid in ruler.claims:
            title = dyn.titles.get(tid)
            if title:
                holder = pop.get(title.holder)
                if holder and holder.pid != ruler.pid:
                    top = dyn.ruler_of_province(title.provinces[0])
                    if top and top.pid != ruler.pid:
                        return top, title, "pressed_claim"
        # de jure / conquest / holy war against neighbors
        my_title = dyn.top_title(ruler)
        if my_title is None:
            return None, None, None
        my_provs = set(my_title.provinces)
        targets = {}
        for pid in my_provs:
            for nb in self.sim.world.provinces[pid].neighbors:
                owner_tid = self.sim.world.provinces[nb].owner_title
                if owner_tid is None or owner_tid == my_title.tid:
                    continue
                other_top = dyn.ruler_of_province(nb)
                if other_top is None or other_top.pid == ruler.pid:
                    continue
                targets.setdefault(other_top.pid, []).append(nb)
        best = None
        for pid, provs in targets.items():
            other = pop.get(pid)
            if other is None:
                continue
            host = rel.hostility(ruler.faith, other.faith)
            title = dyn.titles.get(
                self.sim.world.provinces[provs[0]].owner_title)
            kind = "holy_war" if host >= 0.8 else (
                "de_jure" if title and title.de_jure_liege == my_title.tid
                else "conquest")
            score = len(provs) + (3 if kind == "holy_war" else 0)
            if best is None or score > best[0]:
                best = (score, other, title, kind)
        if best is None:
            return None, None, None
        return best[1], best[2], best[3]

    def declare_war(self, attacker, defender, title, cb="conquest"):
        if self.war_between(attacker.pid, defender.pid):
            return None
        w = War(self.sim, attacker, defender, title, cb)
        # allies join
        for pair in self.alliances:
            if attacker.pid in pair:
                ally_pid = (pair - {attacker.pid}).pop()
                ally = self.sim.population.get(ally_pid)
                if ally and not self.at_war(ally_pid, defender.pid):
                    w.attackers.append(ally.pid)
            if defender.pid in pair:
                ally_pid = (pair - {defender.pid}).pop()
                ally = self.sim.population.get(ally_pid)
                if ally and not self.at_war(ally_pid, attacker.pid):
                    w.defenders.append(ally.pid)
        self.wars.append(w)
        tname = title.full_name if title else "the realm"
        self.sim.bus.record(
            self.sim.date,
            f"WAR: {attacker.display_name()} declares {cb.replace('_', ' ')} "
            f"on {defender.display_name()} for {tname}!", "war")
        self.sim.war_engine.on_war_declared(w)
        return w

    def _settle_peace(self, w: War):
        day = self.sim.date.day
        self.truces[frozenset((w.attackers[0], w.defenders[0]))] = day + 5 * 360
        outcome = w.outcome
        dyn = self.sim.dynasties
        pop = self.sim.population
        att = pop.get(w.attackers[0])
        dfn = pop.get(w.defenders[0])
        if att is None or dfn is None:
            return
        if outcome == "attacker" and w.title is not None:
            title = dyn.titles.get(w.title.tid)
            if title:
                old_holder = pop.get(title.holder)
                dyn._grant_title(title, att, day, old=old_holder)
                att.claims = [c for c in att.claims if c != title.tid]
                self.sim.bus.record(
                    self.sim.date,
                    f"{att.display_name()} wins the war and seizes the "
                    f"{title.full_name}.", "war")
        elif outcome == "defender":
            att.gold = max(0, att.gold - 50)
            dfn.prestige += 150
            self.sim.bus.record(
                self.sim.date,
                f"{dfn.display_name()} repels the invaders. "
                f"{att.display_name()} pays reparations.", "war")
        else:
            self.sim.bus.record(
                self.sim.date,
                f"The war between {att.display_name()} and "
                f"{dfn.display_name()} ends in white peace.", "war")

    def yearly(self):
        self.wars = [w for w in self.wars if w.active][-50:] \
            + [w for w in self.wars if not w.active][-30:]
