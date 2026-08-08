"""Pawn model: identity, body, skills, needs, personality, lifestyle.

Follows the README tuple B/K/M/C/S/R/I/G in a lightweight form:
- B body: health, congenital traits, wounds
- S skills: martial/stewardship/diplomacy/intrigue/learning + labor skills
- C cognition: utility AI in population.py
- R relationships: family + opinion map
- G goals: ambition strings driving utility scores
"""
from __future__ import annotations

from .genetics import Genome
from .names import given_name

PERSONALITY_TRAITS = [
    "brave", "craven", "greedy", "generous", "honest", "deceitful",
    "wrathful", "calm", "zealous", "cynical", "ambitious", "content",
    "lustful", "chaste", "diligent", "lazy", "sadistic", "compassionate",
]

JOBS = ["farmer", "fisher", "woodcutter", "miner", "mason", "smith",
        "weaver", "trader", "soldier", "priest", "scholar", "laborer"]

NOBLE_JOBS = {"soldier", "priest", "scholar"}

LIFESTYLES = ["martial", "stewardship", "diplomacy", "intrigue", "learning"]


class Pawn:
    _next_id = 0

    __slots__ = (
        "pid", "name", "female", "birth_day", "alive", "death_day",
        "genome", "traits", "personality", "skills", "labor",
        "health", "needs", "stress", "ambition",
        "mother", "father", "spouse", "children", "house",
        "province", "job", "faith", "culture",
        "gold", "piety", "prestige", "opinions", "claims",
        "titles", "liege", "is_ruler", "wounds", "cause_of_death",
        "kills", "techniques",
    )

    def __init__(self, rng, province: int, birth_day: int,
                 mother=None, father=None, house=None, faith=None,
                 culture=None, female=None):
        self.pid = Pawn._next_id
        Pawn._next_id += 1
        self.female = rng.chance(0.5) if female is None else female
        self.birth_day = birth_day
        self.alive = True
        self.death_day = -1

        if mother is not None and father is not None:
            self.genome = Genome.conceive(rng, mother.genome, father.genome)
            self.mother, self.father = mother.pid, father.pid
            self.house = house if house is not None else father.house
            self.faith = faith if faith is not None else mother.faith
            self.culture = culture if culture is not None else father.culture
        else:
            self.genome = Genome.random(rng)
            self.mother = self.father = None
            self.house = house
            self.faith = faith
            self.culture = culture

        self.name = given_name(rng, self.female)
        self.traits = self.genome.expressed_traits()
        self.personality = [t for t in PERSONALITY_TRAITS if rng.chance(0.06)]
        if not self.personality:
            self.personality = [rng.choice(PERSONALITY_TRAITS)]

        intl = self.genome.poly_value("intellect_loci") * 10 \
            + self.genome.trait_modifier("intellect")
        prow = self.genome.poly_value("prowess_loci") * 10 \
            + self.genome.trait_modifier("prowess")
        self.skills = {
            "martial": max(0, int(rng.gauss(6 + prow * 0.5 + intl * 0.2, 3))),
            "stewardship": max(0, int(rng.gauss(6 + intl * 0.5, 3))),
            "diplomacy": max(0, int(rng.gauss(6 + intl * 0.3, 3))
                             + int(self.genome.trait_modifier("diplomacy"))),
            "intrigue": max(0, int(rng.gauss(5 + intl * 0.3, 3))),
            "learning": max(0, int(rng.gauss(5 + intl * 0.6, 3))
                            + int(self.genome.trait_modifier("learning"))),
            "prowess": max(0, int(rng.gauss(4 + prow, 3))),
        }
        self.labor = {j: rng.randint(0, 8) for j in JOBS}

        self.health = 3.0 + self.genome.poly_value("health_loci") * 3 \
            + self.genome.trait_modifier("health")
        self.needs = {"food": 0.8, "rest": 0.8, "social": 0.6, "faith": 0.5,
                      "wealth": 0.4}
        self.stress = 0.0
        self.ambition = rng.choice([
            "wealth", "family", "faith", "glory", "knowledge", "power", "peace"])

        self.spouse = None
        self.children = []
        self.province = province
        self.job = "laborer"
        self.gold = rng.uniform(1, 8)
        self.piety = 0.0
        self.prestige = 0.0
        self.opinions = {}       # pid -> -100..100
        self.claims = []         # title ids
        self.titles = []         # title ids held
        self.liege = None
        self.is_ruler = False
        self.wounds = []
        self.cause_of_death = None
        self.kills = 0
        self.techniques = []     # learned combat techniques (tech.py)

    # ---------- derived ----------
    def age(self, day: int) -> float:
        return (day - self.birth_day) / 360.0

    def fertility(self) -> float:
        base = 0.5 + self.genome.poly_value("fertility_loci") * 0.4
        base += self.genome.trait_modifier("fertility")
        if "lustful" in self.personality:
            base += 0.15
        if "chaste" in self.personality:
            base -= 0.2
        return max(0.0, min(1.0, base))

    def attraction_to(self, other: "Pawn") -> float:
        score = 50.0
        score += other.genome.trait_modifier("attraction")
        score += other.skills["diplomacy"]
        if "beautiful" in other.traits:
            score += 15
        if "ugly" in other.traits:
            score -= 15
        return score

    def opinion_of(self, other: "Pawn") -> int:
        op = self.opinions.get(other.pid, 0)
        shared = set(self.personality) & set(other.personality)
        op += 6 * len(shared)
        clash = {("brave", "craven"), ("greedy", "generous"),
                 ("honest", "deceitful"), ("wrathful", "calm"),
                 ("zealous", "cynical"), ("lustful", "chaste"),
                 ("sadistic", "compassionate")}
        for a, b in clash:
            if a in self.personality and b in other.personality:
                op -= 10
        if self.faith != other.faith:
            op -= 10
        return max(-100, min(100, op))

    def display_name(self) -> str:
        return f"{self.name} {self.house}" if self.house else self.name

    def skill_total(self) -> int:
        return sum(self.skills.values())
