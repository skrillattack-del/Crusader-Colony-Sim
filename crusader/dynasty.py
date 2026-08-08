"""Dynasties, houses, titles and full CK3-style inheritance.

Succession laws implemented:
  - confederate partition (new titles created for junior heirs)
  - partition, high partition
  - primogeniture, ultimogeniture, house seniority
  - feudal elective (opinion-weighted vote)
Gender laws: male_only, male_preference, equal, female_preference.
Skipped heirs receive claims; succession crises produce wars via diplomacy.
"""
from __future__ import annotations

TIER_COUNTY, TIER_DUCHY, TIER_KINGDOM, TIER_EMPIRE = 1, 2, 3, 4
TIER_NAMES = {1: "County", 2: "Duchy", 3: "Kingdom", 4: "Empire"}

GENDER_LAWS = ["male_only", "male_preference", "equal", "female_preference"]
SUCCESSION_LAWS = ["confederate_partition", "partition", "high_partition",
                   "primogeniture", "ultimogeniture", "seniority", "elective"]


class Title:
    _next_id = 0
    __slots__ = ("tid", "name", "tier", "provinces", "holder", "prev_holders",
                 "succession", "gender_law", "de_jure_liege")

    def __init__(self, name, tier, provinces):
        self.tid = Title._next_id
        Title._next_id += 1
        self.name = name
        self.tier = tier
        self.provinces = list(provinces)
        self.holder = None
        self.prev_holders = []
        self.succession = "confederate_partition" if tier < TIER_KINGDOM else "partition"
        self.gender_law = "male_preference"
        self.de_jure_liege = None

    @property
    def full_name(self):
        return f"{TIER_NAMES[self.tier]} of {self.name}"


class DynastyManager:
    def __init__(self, sim):
        self.sim = sim
        self.titles: dict[int, Title] = {}
        self.rulers: set[int] = set()   # pids of top rulers

    # ---------- setup ----------
    def found_world(self, rng, provinces, faith_ids):
        """Create kingdoms across the map and assign rulers + vassal counts."""
        from .names import house_name, realm_name
        wm = self.sim.world
        provs = list(provinces)
        rng.shuffle(provs)
        # kingdoms: clusters of ~10-14 provinces
        kingdoms = []
        chunk = max(6, len(provs) // 8)
        for i in range(0, len(provs), chunk):
            kingdoms.append(provs[i:i + chunk])
        for cluster in kingdoms:
            if not cluster:
                continue
            ktitle = Title(realm_name(rng, wm.provinces[cluster[0]].name),
                           TIER_KINGDOM, cluster)
            self.titles[ktitle.tid] = ktitle
            king = self.sim.population.spawn(
                rng, cluster[0], self.sim.date.day - rng.randint(25, 55) * 360,
                house=house_name(rng), faith=rng.choice(faith_ids))
            king.is_ruler = True
            king.job = "soldier"
            king.gold = rng.uniform(80, 300)
            king.prestige = rng.uniform(200, 800)
            # queen consort
            consort = self.sim.population.spawn(
                rng, cluster[0], self.sim.date.day - rng.randint(20, 45) * 360,
                house=house_name(rng), faith=king.faith, female=True)
            self.sim.population.marry(king, consort, self.sim.date.day)
            ktitle.holder = king.pid
            king.titles.append(ktitle.tid)
            self.rulers.add(king.pid)
            # county titles to vassals
            for pid in cluster[1:]:
                ctitle = Title(wm.provinces[pid].name, TIER_COUNTY, [pid])
                ctitle.de_jure_liege = ktitle.tid
                self.titles[ctitle.tid] = ctitle
                count = self.sim.population.spawn(
                    rng, pid, self.sim.date.day - rng.randint(20, 60) * 360,
                    house=house_name(rng), faith=king.faith)
                count.is_ruler = True
                count.liege = king.pid
                count.gold = rng.uniform(20, 80)
                ctitle.holder = count.pid
                count.titles.append(ctitle.tid)
            wm.provinces[cluster[0]].owner_title = ktitle.tid
            for pid in cluster:
                wm.provinces[pid].owner_title = ktitle.tid
            self.sim.bus.record(
                self.sim.date,
                f"The {ktitle.full_name} rises under "
                f"{'Queen' if king.female else 'King'} {king.display_name()}.",
                "dynasty")
        return kingdoms

    # ---------- ancestry ----------
    def ancestor_ids(self, pawn, depth=4) -> set[int]:
        out = set()
        frontier = [pawn]
        pop = self.sim.population
        for _ in range(depth):
            nxt = []
            for p in frontier:
                for par in (p.mother, p.father):
                    if par is not None and par not in out:
                        out.add(par)
                        q = pop.get(par) or pop.dead_by_pid.get(par)
                        if q is not None:
                            nxt.append(q)
            frontier = nxt
        return out

    def children_of(self, pawn, day) -> list:
        return [c for c in (self.sim.population.get(i) for i in pawn.children)
                if c is not None and c.alive]

    # ---------- succession ----------
    def _gender_ok(self, heir, title: Title) -> bool:
        law = title.gender_law
        if law == "male_only":
            return not heir.female
        if law == "female_only":
            return heir.female
        return True

    def _eligible_children(self, ruler, title: Title, day) -> list:
        kids = self.children_of(ruler, day)
        law = title.gender_law
        if law == "male_preference":
            kids.sort(key=lambda k: k.female)          # sons first
        elif law == "female_preference":
            kids.sort(key=lambda k: not k.female)
        kids.sort(key=lambda k: k.birth_day)           # stable age order
        return [k for k in kids if self._gender_ok(k, title)]

    def heirs_by_law(self, ruler, title: Title, day) -> list:
        """Ordered heir list under the title's succession law."""
        kids = self._eligible_children(ruler, title, day)
        law = title.succession
        if law in ("primogeniture",):
            return kids[:1]
        if law == "ultimogeniture":
            return kids[-1:] if kids else []
        if law == "seniority":
            house_members = [p for p in self.sim.population.living()
                             if p.house == ruler.house
                             and self._gender_ok(p, title)]
            house_members.sort(key=lambda p: p.birth_day)
            return house_members[:1]
        if law == "elective":
            return kids  # resolved by election at death
        return kids  # partition family: all children share

    def on_ruler_death(self, ruler):
        day = self.sim.date.day
        held = [self.titles[t] for t in list(ruler.titles) if t in self.titles]
        held.sort(key=lambda t: -t.tier)
        ruler.titles.clear()
        was_top = ruler.pid in self.rulers
        self.rulers.discard(ruler.pid)

        for title in held:
            title.prev_holders.append(ruler.pid)
            if title.succession == "elective":
                heir = self._elect(title, ruler, day)
            else:
                heirs = self.heirs_by_law(ruler, title, day)
                heir = heirs[0] if heirs else None
            if heir is None:
                # extinction of line: title passes to liege or a local noble
                heir = self._find_new_dynast(title)
            self._grant_title(title, heir, day, old=ruler)
            # skipped heirs gain claims
            for kid in self._eligible_children(ruler, title, day):
                if kid.pid != heir.pid:
                    kid.claims.append(title.tid)

        # partition: distribute secondary titles among junior heirs
        if held and held[0].succession in ("partition", "confederate_partition",
                                           "high_partition"):
            self._partition(ruler, held, day)

        # new top ruler?
        for t in list(ruler.titles):
            pass
        for title in held:
            heir_p = self.sim.population.get(title.holder)
            if heir_p and title.tier >= TIER_KINGDOM and was_top:
                self.rulers.add(heir_p.pid)

        # succession crisis: strong claimants may press by war
        self.sim.diplomacy.on_succession(ruler, held)
        main = held[0] if held else None
        if main:
            heir_p = self.sim.population.get(main.holder)
            if heir_p:
                self.sim.bus.record(
                    self.sim.date,
                    f"{ruler.display_name()} is dead. {heir_p.display_name()} "
                    f"inherits the {main.full_name}.", "dynasty")

    def _partition(self, ruler, held, day):
        primary = held[0]
        primary_heir = self.sim.population.get(primary.holder)
        kids = self._eligible_children(ruler, primary, day)
        if primary_heir is None or len(kids) < 2:
            return
        junior = [k for k in kids if k.pid != primary_heir.pid]
        idx = 0
        for title in held[1:]:
            if title.succession.startswith(("partition", "confederate")):
                target = junior[idx % len(junior)]
                if title.holder != target.pid:
                    self._grant_title(title, target, day, old=ruler, quiet=True)
                    idx += 1
        # confederate partition: create a new kingdom for the second heir
        if primary.succession == "confederate_partition" and len(junior) >= 1 \
                and primary.tier == TIER_KINGDOM:
            own = [t for t in self.titles.values()
                   if t.holder in {k.pid for k in junior} and t.tier == TIER_COUNTY]
            if len(own) >= 3:
                from .names import realm_name
                seat = own[0].name
                new_k = Title(realm_name(self.sim.rng, seat), TIER_KINGDOM,
                              [p for t in own for p in t.provinces])
                new_k.succession = "partition"
                self.titles[new_k.tid] = new_k
                self._grant_title(new_k, junior[0], day, old=ruler)
                self.sim.bus.record(
                    self.sim.date,
                    f"Confederate partition creates the {new_k.full_name} "
                    f"for {junior[0].display_name()}.", "dynasty")

    def _elect(self, title, ruler, day):
        pop = self.sim.population
        candidates = self._eligible_children(ruler, title, day)
        vassals = [p for p in pop.living()
                   if p.liege == ruler.pid and p.alive]
        if not candidates and vassals:
            candidates = vassals[:3]
        if not candidates:
            return None
        electors = vassals[:7] if vassals else candidates
        votes = {c.pid: 0.0 for c in candidates}
        for e in electors:
            best = max(candidates, key=lambda c: e.opinion_of(c)
                       + (30 if c.house == e.house else 0)
                       + c.skills["diplomacy"])
            votes[best.pid] += 1 + e.prestige * 0.001
        winner = max(candidates, key=lambda c: votes[c.pid])
        self.sim.bus.record(
            self.sim.date,
            f"The electors choose {winner.display_name()} "
            f"as holder of the {title.full_name}.", "dynasty")
        return winner

    def _find_new_dynast(self, title):
        pop = self.sim.population
        local = [p for p in pop.living()
                 if p.province in title.provinces
                 and p.age(self.sim.date.day) >= 16]
        if not local:
            return None
        heir = max(local, key=lambda p: p.prestige + p.skills["stewardship"])
        if heir.house is None:
            from .names import house_name
            heir.house = house_name(self.sim.rng)
            self.sim.bus.record(
                self.sim.date,
                f"{heir.display_name()} founds a new house to claim the "
                f"{title.full_name}.", "dynasty")
        return heir

    def _grant_title(self, title: Title, heir, day, old=None, quiet=False):
        if heir is None:
            return
        title.holder = heir.pid
        if title.tid not in heir.titles:
            heir.titles.append(title.tid)
        heir.is_ruler = True
        heir.prestige += 100 * title.tier
        if old is not None and heir.liege is None and old.liege is not None \
                and title.tier < TIER_KINGDOM:
            heir.liege = old.liege
        for pid in title.provinces:
            self.sim.world.provinces[pid].owner_title = title.tid

    # ---------- helpers for other systems ----------
    def ruler_of_province(self, province_id):
        tid = self.sim.world.provinces[province_id].owner_title
        if tid is None or tid not in self.titles:
            return None
        holder = self.sim.population.get(self.titles[tid].holder)
        if holder is None:
            return None
        # climb to top liege
        seen = set()
        while holder.liege is not None and holder.liege not in seen:
            seen.add(holder.pid)
            nxt = self.sim.population.get(holder.liege)
            if nxt is None:
                break
            holder = nxt
        return holder

    def top_title(self, pawn) -> Title | None:
        held = [self.titles[t] for t in pawn.titles if t in self.titles]
        return max(held, key=lambda t: t.tier) if held else None

    def vassals_of(self, ruler):
        return [p for p in self.sim.population.living() if p.liege == ruler.pid]
