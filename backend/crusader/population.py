"""Population manager: daily needs, utility-AI activity selection,
matchmaking, births, education, aging and death for up to thousands of pawns.
"""
from __future__ import annotations

from .engine import DAYS_PER_YEAR, DAYS_PER_MONTH
from .genetics import inbreeding_coefficient, inbreeding_effects
from .pawn import Pawn, JOBS, NOBLE_JOBS

ADULT_AGE = 16
MAX_CHILD_AGE = 16
MARRY_MIN, MARRY_MAX = 16, 45
BASE_LIFE_EXPECTANCY = 55


class Population:
    def __init__(self, sim):
        self.sim = sim
        self.pawns: dict[int, Pawn] = {}
        self.dead: list[Pawn] = []
        self.dead_by_pid: dict[int, Pawn] = {}
        self.by_province: dict[int, set[int]] = {}

    # ---------- creation ----------
    def spawn(self, rng, province, day, **kw) -> Pawn:
        p = Pawn(rng, province, day, **kw)
        self.pawns[p.pid] = p
        self.by_province.setdefault(province, set()).add(p.pid)
        return p

    def seed(self, rng, n: int, day: int, provinces: list[int]):
        for _ in range(n):
            prov = rng.choice(provinces)
            p = self.spawn(rng, prov, day - rng.randint(0, 50) * DAYS_PER_YEAR)
            p.job = rng.choice(JOBS)

    def get(self, pid) -> Pawn | None:
        return self.pawns.get(pid)

    def living(self):
        return self.pawns.values()

    def move(self, p: Pawn, province: int):
        self.by_province.get(p.province, set()).discard(p.pid)
        p.province = province
        self.by_province.setdefault(province, set()).add(p.pid)

    # ---------- daily tick ----------
    def daily(self, day: int):
        rng = self.sim.rng
        for p in list(self.pawns.values()):
            # needs decay
            p.needs["food"] = max(0.0, p.needs["food"] - 0.03)
            p.needs["rest"] = max(0.0, p.needs["rest"] - 0.045)
            p.needs["social"] = max(0.0, p.needs["social"] - 0.02)
            if p.needs["food"] <= 0.01:
                p.health -= 0.05
                p.stress += 0.02
            if p.needs["rest"] <= 0.01:
                p.stress += 0.03
            if p.health <= 0:
                self.kill(p, day, "wasted away")
                continue
            self.act(rng, p, day)
            # natural death check, health-extended lifespan
            age = p.age(day)
            life = BASE_LIFE_EXPECTANCY + p.genome.poly_value("health_loci") * 20 \
                + p.genome.trait_modifier("health") * 6
            if age > life - 10:
                risk = 0.0004 * max(0.0, (age - (life - 10))) ** 2
                if rng.chance(risk):
                    self.kill(p, day, "old age")

    def act(self, rng, p: Pawn, day: int):
        """Utility AI: pick the activity with the best score this day."""
        age = p.age(day)
        scores = {}
        n = p.needs
        scores["eat"] = (1 - n["food"]) * 3.0
        scores["sleep"] = (1 - n["rest"]) * 2.5
        scores["socialize"] = (1 - n["social"]) * 1.2 \
            + (0.4 if "lustful" in p.personality else 0)
        scores["pray"] = (1 - n["faith"]) * (1.5 if "zealous" in p.personality else 0.6)
        ambition_bonus = {
            "wealth": ("work", 0.8), "glory": ("train", 0.8),
            "faith": ("pray", 0.8), "knowledge": ("study", 0.8),
            "power": ("scheme", 0.8), "family": ("socialize", 0.5),
            "peace": ("sleep", 0.3),
        }
        scores["work"] = 0.9 + (0.5 if "diligent" in p.personality else 0) \
            - (0.5 if "lazy" in p.personality else 0)
        scores["train"] = 0.3 + p.skills["martial"] * 0.03 if age >= 12 else 0
        scores["study"] = 0.3 + p.skills["learning"] * 0.03 if age >= 6 else 0
        scores["scheme"] = 0.2 + p.skills["intrigue"] * 0.02 if age >= 16 else 0
        act, bonus = ambition_bonus[p.ambition]
        scores[act] = scores.get(act, 0) + bonus
        best = max(scores, key=scores.get)

        if best == "eat":
            p.needs["food"] = min(1.0, n["food"] + 0.65)
            p.health = min(p.health + 0.02, 3.0 +
                           p.genome.poly_value("health_loci") * 3 +
                           p.genome.trait_modifier("health"))
        elif best == "sleep":
            p.needs["rest"] = min(1.0, n["rest"] + 0.6)
        elif best == "socialize":
            p.needs["social"] = min(1.0, n["social"] + 0.4)
            self.socialize(rng, p)
        elif best == "pray":
            p.needs["faith"] = min(1.0, n["faith"] + 0.4)
            p.piety += 0.5 * (2 if "zealous" in p.personality else 1)
        elif best == "work":
            self.work(rng, p)
        elif best == "train":
            p.skills["martial"] += 0.01
            p.skills["prowess"] += 0.02
        elif best == "study":
            p.skills["learning"] += 0.02
        elif best == "scheme":
            p.skills["intrigue"] += 0.01
            if rng.chance(0.0005) and "ambitious" in p.personality:
                self.sim.bus.record(self.sim.date,
                                    f"{p.display_name()} plots in the shadows.",
                                    "intrigue")

    def socialize(self, rng, p: Pawn):
        mates = self.by_province.get(p.province)
        if not mates or len(mates) < 2:
            return
        other_pid = rng.choice(tuple(mates - {p.pid}))
        other = self.pawns.get(other_pid)
        if other is None:
            return
        drift = 1 if p.opinion_of(other) > -20 else -2
        p.opinions[other.pid] = max(-100, min(100,
                                              p.opinions.get(other.pid, 0) + drift))

    def work(self, rng, p: Pawn):
        p.gold += 0.05 + p.labor.get(p.job, 0) * 0.01
        p.labor[p.job] = min(20, p.labor.get(p.job, 0) + 0.005)
        p.needs["wealth"] = min(1.0, p.needs["wealth"] + 0.05)
        self.sim.economy.pawn_produce(p)

    def kill(self, p: Pawn, day: int, cause: str):
        p.alive = False
        p.death_day = day
        p.cause_of_death = cause
        self.by_province.get(p.province, set()).discard(p.pid)
        del self.pawns[p.pid]
        self.dead.append(p)
        self.dead_by_pid[p.pid] = p  # kept forever for ancestry/genetics
        self.sim.stats["deaths"] += 1
        if len(self.dead) > 2000:
            del self.dead[:1000]
        self.sim.bus.emit("death", pawn=p, day=day, cause=cause)
        if p.is_ruler:
            self.sim.dynasties.on_ruler_death(p)
        if cause != "old age":
            self.sim.bus.record(self.sim.date,
                                f"{p.display_name()} died: {cause}.", "death")

    # ---------- monthly tick ----------
    def monthly(self, day: int):
        rng = self.sim.rng
        self.matchmaking(rng, day)
        self.conceptions(rng, day)
        self.assign_jobs(rng)

    def matchmaking(self, rng, day: int):
        adults = [p for p in self.pawns.values()
                  if p.spouse is None
                  and MARRY_MIN <= p.age(day) <= MARRY_MAX]
        rng.shuffle(adults)
        for p in adults:
            if p.spouse is not None:
                continue
            candidates = [q for q in adults
                          if q is not p and q.spouse is None
                          and q.female != p.female
                          and q.province == p.province
                          and abs(q.age(day) - p.age(day)) < 15
                          and q.pid not in {p.mother, p.father}
                          and p.pid not in {q.mother, q.father}]
            if not candidates:
                continue
            best = max(candidates, key=lambda q: p.attraction_to(q))
            if p.attraction_to(best) + best.attraction_to(p) > 95 and rng.chance(0.25):
                self.marry(p, best, day)

    def marry(self, a: Pawn, b: Pawn, day: int):
        a.spouse, b.spouse = b.pid, a.pid
        a.opinions[b.pid] = b.opinions[a.pid] = 60
        if a.is_ruler or b.is_ruler:
            self.sim.bus.record(self.sim.date,
                                f"{a.display_name()} married {b.display_name()}.",
                                "dynasty")
            self.sim.diplomacy.on_marriage(a, b)

    def conceptions(self, rng, day: int):
        for p in list(self.pawns.values()):
            if p.female or p.spouse is None or p.pid > p.spouse:
                continue  # handle each couple once via the male partner
            wife = self.pawns.get(p.spouse)
            if wife is None or wife.province != p.province:
                continue
            age = wife.age(day)
            if not (16 <= age <= 45):
                continue
            fert = p.fertility() * wife.fertility()
            monthly_p = 0.055 * fert * (1.2 if age < 30 else 0.8)
            if rng.chance(monthly_p):
                self.conceive(rng, p, wife, day)

    def conceive(self, rng, father: Pawn, mother: Pawn, day: int):
        anc_f = self.sim.dynasties.ancestor_ids(father, depth=4)
        anc_m = self.sim.dynasties.ancestor_ids(mother, depth=4)
        coef = inbreeding_coefficient(anc_f, anc_m)
        child = self.spawn(rng, mother.province, day,
                           mother=mother, father=father)
        child.house = father.house if father.house else mother.house
        if coef > 0:
            effects = inbreeding_effects(rng, coef, child.genome)
            child.traits = child.genome.expressed_traits()
            if effects and (father.is_ruler or mother.is_ruler):
                self.sim.bus.record(self.sim.date,
                                    f"A child of {father.display_name()} shows "
                                    f"signs of inbreeding ({', '.join(effects)}).",
                                    "dynasty")
        father.children.append(child.pid)
        mother.children.append(child.pid)
        self.sim.stats["births"] += 1
        # infant mortality
        if rng.chance(0.08):
            self.kill(child, day, "died in infancy")

    def assign_jobs(self, rng):
        for p in self.pawns.values():
            if p.job == "laborer" and rng.chance(0.05) and p.age(self.sim.date.day) >= 14:
                best = max(JOBS, key=lambda j: p.labor.get(j, 0) + rng.uniform(0, 2))
                p.job = best

    # ---------- yearly ----------
    def yearly(self, day: int):
        rng = self.sim.rng
        for p in self.pawns.values():
            age = p.age(day)
            if age < ADULT_AGE:
                # education: childhood skill growth guided by guardian skills
                for s in p.skills:
                    p.skills[s] += rng.uniform(0, 0.4)
            # stress relief
            p.stress = max(0.0, p.stress - 0.3)
            if p.stress > 0.8 and rng.chance(0.2):
                p.health -= 0.5
        # technique learning (knowledge spreading through the world)
        self.sim.tech.spread_techniques()
