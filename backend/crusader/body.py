"""Pawn bodies as graphs — the physical layer of the combat engine.

Implements the documentation's three foundational body graphs for named
fighters (generals, duelists):

  G1 anatomical — parts with integrity; wounds are localized part damage.
                  "Broken Arm" is a first-class component: a ruined sword
                  arm mechanically weakens every technique routed through it.
  G2 kinematic  — mobility derived from part integrity; drives move speed,
                  windup times, and the pose data streamed to the renderer.
  G3 conduit    — reservoir -> trunk -> limb channels -> effectors.
                  A technique never sets damage; it declares a routing and
                  the flow solve decides what actually arrives ("Kirchhoff's
                  laws for ki").

Parameter regimes, not scripts:
  * overdrive  τ ≫ C  -> channel rupture: self-wound, saturation spike
  * gates      sequential limiter release: each raises C and multiplies µ;
               the eighth is effectively µ -> ∞ with integrity bleed
  * seals      damage typed at G3 edges instead of G1 parts (Gentle Fist):
               capacity collapses, techniques gutter out

Pure stdlib; all randomness flows through the caller's rng.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# G1 — anatomical graph
# share: hit-location weight & resilience scale; vital: destruction kills.
# group ties the part into G2 mobility; region ties it into G3 conduits.
# ---------------------------------------------------------------------------
G1_PARTS = {
    "head":      dict(share=0.07, vital=True,  group="head",  label="head"),
    "eyes":      dict(share=0.02, vital=False, group="head",  label="eyes"),
    "torso":     dict(share=0.20, vital=False, group="core",  label="torso"),
    "heart":     dict(share=0.04, vital=True,  group="core",  label="heart"),
    "lungs":     dict(share=0.06, vital=False, group="core",  label="lungs"),
    "spine":     dict(share=0.05, vital=False, group="core",  label="spine"),
    "arm_r":     dict(share=0.08, vital=False, group="arm_r", label="right arm"),
    "forearm_r": dict(share=0.06, vital=False, group="arm_r", label="right forearm"),
    "hand_r":    dict(share=0.04, vital=False, group="arm_r", label="sword hand"),
    "arm_l":     dict(share=0.08, vital=False, group="arm_l", label="left arm"),
    "forearm_l": dict(share=0.06, vital=False, group="arm_l", label="left forearm"),
    "hand_l":    dict(share=0.04, vital=False, group="arm_l", label="off hand"),
    "thigh_r":   dict(share=0.09, vital=False, group="legs",  label="right thigh"),
    "shin_r":    dict(share=0.06, vital=False, group="legs",  label="right shin"),
    "thigh_l":   dict(share=0.09, vital=False, group="legs",  label="left thigh"),
    "shin_l":    dict(share=0.06, vital=False, group="legs",  label="left shin"),
}
PART_ORDER = list(G1_PARTS)
_PART_IDX = {p: i for i, p in enumerate(PART_ORDER)}

# Where each attack geometry tends to land (weighted part lists).
GEO_TARGETS = {
    "arc":    [("arm_r", 2), ("arm_l", 2), ("forearm_r", 2), ("forearm_l", 2),
               ("torso", 3), ("head", 1), ("thigh_r", 1), ("thigh_l", 1)],
    "point":  [("torso", 3), ("heart", 2), ("lungs", 2), ("head", 2),
               ("eyes", 1), ("hand_r", 1)],
    "line":   [("torso", 4), ("lungs", 2), ("heart", 1), ("spine", 2)],
    "cleave": [("torso", 3), ("arm_r", 2), ("arm_l", 2), ("head", 2),
               ("spine", 1), ("thigh_r", 1), ("thigh_l", 1)],
    "cone":   None,   # None -> weighted by anatomical share (engulfing hits)
    "radial": None,
}

# Wound verbs by damage transformation: (light, heavy, destroyed)
_WOUND_VERBS = {
    "kinetic":       ("gashed", "deep-cut", "shattered"),
    "thermal":       ("scorched", "badly burned", "charred"),
    "gravitational": ("crushed", "badly crushed", "pulverized"),
    "spatial":       ("sliced", "carved open", "severed"),
    "spiritual":     ("numbed", "withered", "deadened"),
}

# ---------------------------------------------------------------------------
# G3 — conduit graph (reservoir 'core' -> trunk -> limbs -> effectors)
# ---------------------------------------------------------------------------
EDGE_ORDER = [
    "core-heart", "heart-spine",
    "spine-arm_r", "arm_r-hand_r",
    "spine-arm_l", "arm_l-hand_l",
    "spine-eyes", "spine-legs",
]
_EDGE_IDX = {e: i for i, e in enumerate(EDGE_ORDER)}

G3_PATHS = {
    "hand_r": ["core-heart", "heart-spine", "spine-arm_r", "arm_r-hand_r"],
    "hand_l": ["core-heart", "heart-spine", "spine-arm_l", "arm_l-hand_l"],
    "eyes":   ["core-heart", "heart-spine", "spine-eyes"],
    "legs":   ["core-heart", "heart-spine", "spine-legs"],
}

# The G1 part that houses each channel — ruptures wound it (self-injury).
_RUPTURE_PART = {
    "core-heart": "heart", "heart-spine": "spine",
    "spine-arm_r": "arm_r", "arm_r-hand_r": "forearm_r",
    "spine-arm_l": "arm_l", "arm_l-hand_l": "forearm_l",
    "spine-eyes": "eyes", "spine-legs": "thigh_r",
}

# Regional capacity concentration (docs: ocular / spinal / dermal bloodlines).
_TRAIT_REGION_MULT = {
    "bloodline_vigor": {"spine-eyes": 1.9, "heart-spine": 1.4},
    "possessed":       {"heart-spine": 1.6, "core-heart": 1.3},
    "strong":          {"spine-arm_r": 1.25, "spine-arm_l": 1.25},
    "giant":           {"core-heart": 1.3},
}

GATE_MAX = 8
_GATE_NAMES = ["First", "Second", "Third", "Fourth",
               "Fifth", "Sixth", "Seventh", "Eighth"]


def _sev_word(hp: float) -> int:
    """0 = light, 1 = heavy, 2 = destroyed."""
    if hp <= 0.0:
        return 2
    return 1 if hp < 0.34 else 0


class BodyGraph:
    """Full three-graph body for a named fighter."""

    __slots__ = ("parts", "bleed", "blood", "reservoir", "res_max", "regen",
                 "edges", "gate", "alive", "down", "prowess", "wounds",
                 "cause", "_wounded_at")

    def __init__(self, prowess: float, conduit: float, traits, rng):
        self.parts = {p: 1.0 for p in G1_PARTS}
        self.bleed = 0.0           # blood loss per second
        self.blood = 1.0           # M — material state; 0 => collapse
        self.prowess = min(prowess, 30.0)   # legendary, but still flesh
        # G3: capacity from the conduit stat (genetics' "impossible axis")
        base_c = 1.6 + max(0.0, conduit) * 0.85
        self.edges = {}
        for e in EDGE_ORDER:
            mult = 1.0
            for t in traits:
                mult *= _TRAIT_REGION_MULT.get(t, {}).get(e, 1.0)
            self.edges[e] = {"C": base_c * mult * rng.uniform(0.9, 1.12),
                             "sat": 0.0, "integ": 1.0, "seal": 0.0}
        self.res_max = 22.0 + max(0.0, conduit) * 9.0 + self.prowess * 1.5
        self.reservoir = self.res_max
        self.regen = self.res_max * 0.022
        self.gate = 0
        self.alive = True
        self.down = False
        self.wounds = []           # (name, severity 0..1) for write-back
        self.cause = None
        self._wounded_at = {p: 0 for p in G1_PARTS}   # last severity tier

    # ---------------- derived state (G2 mobility & ceilings) ----------------
    def _group_avg(self, group: str) -> float:
        vals = [max(0.0, self.parts[p]) for p, s in G1_PARTS.items()
                if s["group"] == group]
        return sum(vals) / len(vals)

    def move_mult(self) -> float:
        if self.down or not self.alive:
            return 0.0
        legs = self._group_avg("legs")
        return max(0.15, 0.30 + 0.70 * legs) * (0.6 + 0.4 * self.blood)

    def attack_speed(self, hand: str = "hand_r") -> float:
        chain = self.chain_integrity(hand)
        return max(0.25, 0.35 + 0.65 * chain)

    def guard_mult(self) -> float:
        return 0.4 + 0.4 * self._group_avg("arm_l") + 0.2 * max(
            0.0, self.parts["eyes"])

    def chain_integrity(self, effector: str) -> float:
        """G1 integrity of the limb chain feeding an effector (the doc's
        'output ceiling derived from limb I and C')."""
        chain = {"hand_r": ("arm_r", "forearm_r", "hand_r"),
                 "hand_l": ("arm_l", "forearm_l", "hand_l"),
                 "eyes": ("eyes",),
                 "legs": ("thigh_r", "shin_r", "thigh_l", "shin_l")}[effector]
        return min(max(0.0, self.parts[p]) for p in chain)

    @property
    def mu(self) -> float:
        """Output gain µ — the gate limiter multiplier."""
        m = 1.22 ** self.gate
        if self.gate >= GATE_MAX:
            m *= 1.9        # the eighth gate: µ -> "∞" (as far as flesh allows)
        return m

    def condition(self) -> float:
        """Overall 0..1 for HUD bars: worst of blood and vital integrity."""
        vit = min(self.parts["head"], self.parts["heart"],
                  (self.parts["torso"] + self.parts["spine"]) / 2)
        return max(0.0, min(self.blood, 0.25 + 0.75 * vit))

    # ---------------- upkeep ----------------
    def tick(self, dt: float, rng) -> list:
        """Bleeding, regen, saturation decay, gate upkeep. Returns events
        [(kind, text)] for the battle log."""
        if not self.alive:
            return []
        ev = []
        # bleeding & clotting
        if self.bleed > 0:
            self.blood -= self.bleed * dt
            self.bleed = max(0.0, self.bleed - 0.010 * dt)
        # reservoir regen scales with heart/lungs (G1 feeding G3)
        pump = max(0.1, (self.parts["heart"] + self.parts["lungs"]) / 2)
        self.reservoir = min(self.res_max,
                             self.reservoir + self.regen * pump * dt)
        # saturation decay, seal timers
        for e in self.edges.values():
            e["sat"] = max(0.0, e["sat"] - 0.07 * dt)
            if e["seal"] > 0:
                e["seal"] = max(0.0, e["seal"] - dt)
        # open gates burn the body: integrity bleed across the core
        if self.gate >= 4:
            rate = 0.006 * (self.gate - 3) + (0.035 if self.gate >= GATE_MAX
                                              else 0.0)
            for p in ("torso", "heart", "lungs", "spine"):
                self.parts[p] -= rate * dt
            self.reservoir = max(0.0, self.reservoir - self.gate * 0.35 * dt)
            if self.parts["heart"] <= 0:
                self.alive = False
                self.cause = "burned out by the final gate"
                ev.append(("wound", "is consumed by the gates — "
                                    "his heart gives out!"))
                return ev
        # collapse conditions (blood loss, broken spine)
        if not self.down and (self.blood <= 0.02 or self.parts["spine"] <= 0):
            self.down = True
            ev.append(("wound", "collapses, unable to fight on!"))
        if self.blood <= -0.15:
            self.alive = False
            self.cause = "bled out on the field"
            ev.append(("wound", "bleeds out."))
        return ev

    # ---------------- G3 flow solve (technique routing) ----------------
    def strike(self, effector: str, base_power: float, drive: float,
               rng) -> tuple:
        """Route power from the core to an effector across G3.

        Returns (output, events, routing_note). drive > 1 is deliberate
        overdrive (τ ≫ C): more demanded flow, rupture risk on weak channels.
        """
        if not self.alive or self.down:
            return 0.0, [], ""
        ev = []
        path = G3_PATHS[effector]
        req = base_power * max(0.2, drive)
        gate_c = 1.0 + 0.30 * self.gate      # gates raise C as well as µ
        # per-channel effective capacity
        eff = []
        for name in path:
            e = self.edges[name]
            seal_m = 0.10 if e["seal"] > 0 else 1.0
            eff.append(max(0.05, e["C"] * gate_c * e["integ"] * seal_m
                           * (1.0 - 0.45 * min(1.0, e["sat"]))))
        bottleneck = min(eff)
        flow = min(req, bottleneck * (1.35 if drive > 1.0 else 1.0),
                   self.reservoir * 2.0)
        self.reservoir = max(0.0, self.reservoir - flow * 0.22)
        # saturation rises along the whole routing
        for name in path:
            e = self.edges[name]
            e["sat"] = min(1.5, e["sat"] + flow / (e["C"] * 5.0 + 0.1))
        # overdrive rupture: τ ≫ C on the weakest channel tears it
        ratio = req / (bottleneck + 1e-6)
        if drive > 1.0 and ratio > 1.4:
            name = path[eff.index(bottleneck)]
            e = self.edges[name]
            e["integ"] = max(0.15, e["integ"]
                             - min(0.22, 0.14 * (ratio - 1.4)))
            e["sat"] = min(1.5, e["sat"] + 0.5)
            part = _RUPTURE_PART[name]
            self.parts[part] -= min(0.30, 0.08 * (ratio - 1.4))
            self.bleed += 0.006
            self._note_wound(part, "kinetic", ev, internal=True)
            ev.append(("rupture", f"a conduit ruptures in his "
                                  f"{G1_PARTS[part]['label']} (τ≫C)!"))
        ceiling = 0.30 + 0.70 * self.chain_integrity(effector)
        return self.mu * flow * ceiling, ev, f"core→{effector}"

    # ---------------- taking damage ----------------
    def receive_hit(self, amount: float, geometry: str, transformation: str,
                    guarding: bool, rng) -> tuple:
        """Resolve an incoming hit onto a G1 part. Returns (events, part)."""
        if not self.alive:
            return [], None
        ev = []
        if guarding and rng.chance(0.70):
            amount *= 0.35
            part = rng.choice(("forearm_l", "forearm_r", "hand_l"))
        else:
            part = self._pick_part(geometry, rng)
        spec = G1_PARTS[part]
        resilience = 26.0 + 130.0 * spec["share"]
        self.parts[part] -= amount / resilience
        self.blood -= amount / 240.0
        if _sev_word(self.parts[part]) >= 1:
            self.bleed += amount / 900.0
        self._note_wound(part, transformation, ev)
        if self.parts[part] <= 0 and spec["vital"]:
            self.alive = False
            self.cause = f"his {spec['label']} destroyed"
            ev.append(("kill", f"is struck down — his {spec['label']} "
                               f"is destroyed!"))
        return ev, part

    def _pick_part(self, geometry: str, rng) -> str:
        table = GEO_TARGETS.get(geometry)
        if table is None:
            table = [(p, s["share"] * 100) for p, s in G1_PARTS.items()]
        total = sum(w for _, w in table)
        r = rng.random() * total
        for p, w in table:
            r -= w
            if r <= 0:
                return p
        return table[-1][0]

    def _note_wound(self, part: str, transformation: str, ev: list,
                    internal: bool = False):
        """Record a named wound when a part crosses a severity tier."""
        sev = _sev_word(self.parts[part])
        if sev <= self._wounded_at[part]:
            return
        self._wounded_at[part] = sev
        verbs = _WOUND_VERBS.get(transformation, _WOUND_VERBS["kinetic"])
        label = G1_PARTS[part]["label"]
        name = f"{verbs[min(sev, 2)]} {label}"
        self.wounds.append((name, 0.25 + 0.375 * sev))
        if not internal:
            ev.append(("wound", f"suffers a {name}!"))

    # ---------------- G3-targeted damage (the Gentle Fist school) ----------
    def receive_seal(self, amount: float, rng) -> list:
        """Damage typed at G3 edges instead of G1 parts: seal conduits."""
        ev = []
        open_edges = [e for e in ("spine-arm_r", "arm_r-hand_r",
                                  "spine-arm_l", "arm_l-hand_l",
                                  "heart-spine")
                      if self.edges[e]["seal"] <= 0]
        if not open_edges:
            return ev
        n = 2 if amount > 8 and len(open_edges) > 1 else 1
        for _ in range(n):
            e = rng.choice(open_edges)
            open_edges.remove(e)
            self.edges[e]["seal"] = 5.0 + amount * 0.5
            ev.append(("seal", f"meridian sealed ({e.replace('-', '→')})"))
            if not open_edges:
                break
        return ev

    # ---------------- the gates ----------------
    def open_gate(self, rng) -> list:
        if self.gate >= GATE_MAX:
            return []
        self.gate += 1
        # each release also floods the reservoir back open
        self.reservoir = min(self.res_max * (1 + 0.15 * self.gate),
                             self.reservoir + self.res_max * 0.35)
        name = _GATE_NAMES[self.gate - 1]
        if self.gate >= GATE_MAX:
            return [("gate", f"opens the Gate of the {name} Form — µ→∞. "
                             f"His body begins to burn away!")]
        return [("gate", f"opens the Gate of the {name} Form! "
                         f"(µ ×{self.mu:.2f})")]

    # ---------------- snapshots & write-back ----------------
    def snapshot(self) -> dict:
        return {
            "parts": [round(max(-0.2, self.parts[p]), 2) for p in PART_ORDER],
            "edges": [[round(min(1.5, self.edges[e]["sat"]), 2),
                       1 if self.edges[e]["seal"] > 0 else 0,
                       round(self.edges[e]["integ"], 2)]
                      for e in EDGE_ORDER],
            "blood": round(max(0.0, self.blood), 2),
            "res": round(self.reservoir / self.res_max, 2),
            "gate": self.gate,
            "mu": round(self.mu, 2),
        }

    def wound_names(self, limit: int = 5) -> list[str]:
        worst = sorted(self.wounds, key=lambda w: -w[1])
        return [w[0] for w in worst[:limit]]

    def wound_severity(self) -> float:
        return min(2.0, sum(w[1] for w in self.wounds))
