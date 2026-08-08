"""Genetic simulation: heritable traits as diploid allele pairs (dominant /
recessive), polygenic stat loci, mutation, and inbreeding coefficients.

Each pawn carries a Genome. Children inherit one allele per locus per parent.
"""
from __future__ import annotations

# Heritable congenital traits, CK3-flavored.
# (name, dominance 0..1, effect tags, base frequency, good/bad)
TRAIT_LOCI = {
    "strong":        {"dom": 0.6, "freq": 0.06, "quality": +2, "tags": {"prowess": +3, "health": +0.5}},
    "hale":          {"dom": 0.5, "freq": 0.10, "quality": +1, "tags": {"health": +1.0, "fertility": +0.05}},
    "genius":        {"dom": 0.4, "freq": 0.02, "quality": +3, "tags": {"intellect": +5, "learning": +5}},
    "quick":         {"dom": 0.45, "freq": 0.08, "quality": +1, "tags": {"intellect": +3}},
    "beautiful":     {"dom": 0.55, "freq": 0.07, "quality": +2, "tags": {"attraction": +25, "diplomacy": +2}},
    "giant":         {"dom": 0.7, "freq": 0.01, "quality": +2, "tags": {"prowess": +4, "health": -0.3}},
    "bloodline_vigor": {"dom": 0.65, "freq": 0.015, "quality": +3, "tags": {"prowess": +2, "conduit": +4}},
    "frail":         {"dom": 0.3, "freq": 0.08, "quality": -1, "tags": {"health": -1.2}},
    "dull":          {"dom": 0.25, "freq": 0.06, "quality": -1, "tags": {"intellect": -4}},
    "ugly":          {"dom": 0.35, "freq": 0.07, "quality": -1, "tags": {"attraction": -20, "diplomacy": -1}},
    "clubfooted":    {"dom": 0.3, "freq": 0.03, "quality": -1, "tags": {"prowess": -3}},
    "lunatic":       {"dom": 0.2, "freq": 0.02, "quality": -2, "tags": {"intellect": -2, "stress": +1}},
    "possessed":     {"dom": 0.2, "freq": 0.01, "quality": -2, "tags": {"learning": -2, "conduit": +3}},
    "infertile":     {"dom": 0.25, "freq": 0.02, "quality": -2, "tags": {"fertility": -0.5}},
}

# Polygenic stat loci: each stat is the sum of N diallelic loci (0,1,2 effect).
POLYGENIC = {
    "prowess_loci": 6,
    "intellect_loci": 6,
    "health_loci": 6,
    "fertility_loci": 4,
    "conduit_loci": 4,   # G3 conduit capacity (the 'impossible things' axis)
}

MUTATION_RATE = 0.003


class Genome:
    __slots__ = ("alleles", "poly")

    def __init__(self, alleles=None, poly=None):
        self.alleles = alleles or {}   # trait -> [a1, a2] in {0,1}
        self.poly = poly or {}         # stat -> list of loci counts

    @staticmethod
    def random(rng) -> "Genome":
        g = Genome()
        for trait, spec in TRAIT_LOCI.items():
            f = spec["freq"]
            g.alleles[trait] = [1 if rng.chance(f) else 0,
                                1 if rng.chance(f) else 0]
        for stat, n in POLYGENIC.items():
            g.poly[stat] = [rng.random() for _ in range(n)]
        return g

    @staticmethod
    def conceive(rng, mother: "Genome", father: "Genome") -> "Genome":
        child = Genome()
        for trait in TRAIT_LOCI:
            m = rng.choice(mother.alleles[trait])
            f = rng.choice(father.alleles[trait])
            if rng.chance(MUTATION_RATE):
                m = 1 - m
            if rng.chance(MUTATION_RATE):
                f = 1 - f
            child.alleles[trait] = [m, f]
        for stat, n in POLYGENIC.items():
            child.poly[stat] = [
                (rng.choice(mother.poly[stat]) + rng.choice(father.poly[stat])) / 2
                for _ in range(n)
            ]
        return child

    def expresses(self, trait: str) -> bool:
        a1, a2 = self.alleles.get(trait, (0, 0))
        dom = TRAIT_LOCI[trait]["dom"]
        if a1 and a2:
            return True
        if a1 or a2:
            return dom >= 0.5
        return False

    def expressed_traits(self) -> list[str]:
        return [t for t in TRAIT_LOCI if self.expresses(t)]

    def carriers(self) -> list[str]:
        return [t for t in TRAIT_LOCI
                if not self.expresses(t) and any(self.alleles[t])]

    def poly_value(self, stat: str) -> float:
        """0..1 polygenic value for a stat."""
        loci = self.poly.get(stat)
        return sum(loci) / len(loci) if loci else 0.5

    def trait_modifier(self, tag: str) -> float:
        total = 0.0
        for t in self.expressed_traits():
            total += TRAIT_LOCI[t]["tags"].get(tag, 0.0)
        return total


def inbreeding_coefficient(ancestors_a: set, ancestors_b: set) -> float:
    """Simplified: 0.25 * fraction of shared recent ancestors (depth-limited)."""
    if not ancestors_a or not ancestors_b:
        return 0.0
    shared = len(ancestors_a & ancestors_b)
    union = len(ancestors_a | ancestors_b)
    return 0.25 * (shared / union) if union else 0.0


def inbreeding_effects(rng, coef: float, genome: Genome) -> list[str]:
    """High inbreeding raises chance of recessive disorders expressing."""
    effects = []
    if coef > 0.05:
        for trait, spec in TRAIT_LOCI.items():
            if spec["quality"] < 0 and not genome.expresses(trait):
                if any(genome.alleles[trait]) and rng.chance(coef * 0.5):
                    genome.alleles[trait] = [1, 1]
                    effects.append(trait)
    return effects
