"""Live tactical battles — the Total War layer.

When two hostile armies meet in web mode, a LiveBattle replaces the instant
resolution: hundreds of individual soldiers fight in real time on a field,
commanded by named generals with rally auras who can duel and unleash
combat-grammar techniques as area blasts.

Deterministic-friendly: all randomness flows through sim.rng.
Results write back into the strategic layer (Army units, war score, routs,
general deaths) so a duel can still change history.
"""
from __future__ import annotations

import math

from .war import UNIT_TYPES

FIELD_W, FIELD_H = 120.0, 70.0
MAX_SOLDIERS = 350          # per side; larger armies are scaled
ATTACK_COOLDOWN = 0.8
TECH_COOLDOWN = 26.0
RALLY_RADIUS = 14.0
RALLY_RATE = 0.004
ROUT_MORALE = 0.25
MAX_BATTLE_SECONDS = 300.0

# type: (dmg, tough, morale, siege) from UNIT_TYPES; tactical adds:
TAC = {                       # speed, range, hp mult
    "levy":        (3.2, 1.6, 1.0),
    "spearmen":    (3.0, 1.8, 1.4),
    "archers":     (3.2, 14.0, 0.8),
    "light_cav":   (5.2, 2.2, 1.2),
    "knights":     (4.6, 2.4, 2.2),
    "pikemen":     (2.8, 1.8, 1.6),
    "siege_train": (1.6, 1.6, 1.0),
}
_TYPE_IDX = {t: i for i, t in enumerate(TAC)}
_IDX_TYPE = {i: t for t, i in _TYPE_IDX.items()}


class Soldier:
    __slots__ = ("side", "type", "x", "y", "hp", "maxhp", "alive",
                 "cool", "retarget", "tx", "ty")

    def __init__(self, side, type_, x, y):
        self.side = side
        self.type = type_
        self.x, self.y = x, y
        spd, rng, hpm = TAC[type_]
        self.maxhp = self.hp = 6.0 * UNIT_TYPES[type_][1] * hpm
        self.alive = True
        self.cool = 0.0
        self.retarget = 0.0
        self.tx, self.ty = x, y


class General:
    __slots__ = ("pawn", "side", "x", "y", "hp", "maxhp", "alive",
                 "tech_cool", "dueling")

    def __init__(self, pawn, side, x, y):
        self.pawn = pawn
        self.side = side
        self.x, self.y = x, y
        self.maxhp = self.hp = 30.0 + pawn.skills["prowess"] * 2 \
            + pawn.genome.poly_value("conduit_loci") * 20
        self.alive = True
        self.tech_cool = TECH_COOLDOWN * 0.5
        self.dueling = False

    def best_technique(self, tech_mgr):
        best, bp = None, -1.0
        for name in self.pawn.techniques:
            t = tech_mgr.technique_by_name(name)
            if t and t["power"] > bp:
                best, bp = t, t["power"]
        return best


class LiveBattle:
    _next_id = 0

    def __init__(self, sim, army_a, army_b, province, war):
        self.bid = LiveBattle._next_id
        LiveBattle._next_id += 1
        self.sim = sim
        self.armies = (army_a, army_b)
        self.province = province
        self.war = war
        self.t = 0.0
        self.phase = "deploy"        # deploy | clash | rout | done
        self.result = None
        self.events: list[str] = []
        self.fx: list[dict] = []
        self.scale = [1.0, 1.0]
        self.initial = [0, 0]
        self.kills = [0, 0]
        self.morale = [army_a.morale, army_b.morale]
        self.soldiers: list[Soldier] = []
        self.generals: list[General] = []
        self._spawn(0, army_a, x0=-38, facing=1)
        self._spawn(1, army_b, x0=38, facing=-1)
        self.initial = [sum(1 for s in self.soldiers if s.side == 0),
                        sum(1 for s in self.soldiers if s.side == 1)]
        self.rout_side = None
        self.rout_timer = 0.0
        self.done_age = 0.0
        # cache names now: generals can die mid-battle (and change history)
        pop = self.sim.population
        self._names = []
        for army in self.armies:
            r = pop.get(army.ruler)
            self._names.append(r.display_name() if r else "an unknown host")
        self._log(f"{self._names[0]} and {self._names[1]} meet on the "
                  f"field of {province.name} — "
                  f"{self.armies[0].size} vs {self.armies[1].size} men.")

    # ---------------- setup ----------------
    def name_of(self, side) -> str:
        return self._names[side]

    def _spawn(self, side, army, x0, facing):
        scale = min(1.0, MAX_SOLDIERS / max(1, army.size))
        self.scale[side] = scale
        ranks = []
        for t, n in army.units.items():
            count = max(1, round(n * scale)) if t in TAC else 0
            ranks.extend([t] * count)
        rng = self.sim.rng
        rng.shuffle(ranks)
        per_row = 26
        for i, t in enumerate(ranks):
            row, col = divmod(i, per_row)
            # infantry front, archers back, cavalry on the flanks
            if t in ("archers",):
                depth = 4 + (row % 2)
            elif t in ("light_cav", "knights"):
                depth = row % 2
            else:
                depth = row % 3
            x = x0 + facing * depth * 3.0 + rng.uniform(-0.8, 0.8)
            y = (col - per_row / 2) * 2.4 + rng.uniform(-0.8, 0.8) \
                + (row // 3) * 1.2
            if t in ("light_cav", "knights"):
                y = (-FIELD_H / 2 + 4 if col % 2 == 0 else FIELD_H / 2 - 4) \
                    + rng.uniform(-2, 2)
            self.soldiers.append(Soldier(side, t, x, y))
        # general behind the center
        pop = self.sim.population
        cmd = pop.get(army.commander)
        if cmd is not None:
            self.generals.append(
                General(cmd, side, x0 - facing * 8.0, 0.0))

    def _log(self, text):
        self.events.append(f"[{self.t:5.1f}s] {text}")
        if len(self.events) > 60:
            del self.events[:20]

    # ---------------- tick ----------------
    def tick(self, dt: float):
        if self.phase == "done":
            return
        self.t += dt
        if self.phase == "deploy" and self.t > 2.0:
            self.phase = "clash"
        rng = self.sim.rng
        self._grid = {}
        cell = 4.0
        for i, s in enumerate(self.soldiers):
            if s.alive:
                key = (int(s.x // cell), int(s.y // cell))
                self._grid.setdefault(key, []).append(i)

        for s in self.soldiers:
            if not s.alive:
                continue
            self._tick_soldier(s, dt, rng)
        for g in self.generals:
            if g.alive:
                self._tick_general(g, dt, rng)
        # fx decay
        for f in self.fx:
            f["age"] += dt
        self.fx = [f for f in self.fx if f["age"] < 1.6]
        # morale from casualties
        for side in (0, 1):
            loss = self.kills[side] / max(1, self.initial[side])
            base = self.armies[side].morale
            self.morale[side] = max(0.0, base * (1.0 - 0.9 * loss)
                                    - (0.15 if any(not g.alive and g.side == side
                                                   for g in self.generals) else 0))
        # rout / end checks
        counts = [sum(1 for s in self.soldiers if s.side == 0 and s.alive),
                  sum(1 for s in self.soldiers if s.side == 1 and s.alive)]
        for side in (0, 1):
            frac = counts[side] / max(1, self.initial[side])
            if self.phase == "clash" and self.t > 5.0 and \
                    (self.morale[side] <= ROUT_MORALE or frac <= 0.12):
                self.phase = "rout"
                self._log(f"{self.name_of(side)}'s army breaks and routs!")
                if self.rout_side is None:
                    self.rout_side = 1 - side
                    self.rout_timer = 6.0
        if self.phase == "rout" and self.rout_side is not None:
            loser = 1 - self.rout_side
            for s in self.soldiers:
                if s.alive and s.side == loser:
                    s.x += (-1 if loser == 0 else 1) * 6.0 * dt
            self.rout_timer -= dt
            if self.rout_timer <= 0:
                self._finish(self.rout_side)
        if self.t > MAX_BATTLE_SECONDS and self.phase != "done":
            winner = 0 if self.morale[0] >= self.morale[1] else 1
            self._finish(winner)

    def _enemies_near(self, s, radius):
        cell = 4.0
        cx, cy = int(s.x // cell), int(s.y // cell)
        r = int(radius // cell) + 1
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for i in self._grid.get((cx + dx, cy + dy), ()):
                    e = self.soldiers[i]
                    if e.side != s.side and e.alive:
                        yield e

    def _nearest_enemy(self, s):
        best, bd = None, 1e18
        for e in self._enemies_near(s, 12.0):
            d = (e.x - s.x) ** 2 + (e.y - s.y) ** 2
            if d < bd:
                best, bd = e, d
        return best, math.sqrt(bd)

    def _tick_soldier(self, s, dt, rng):
        spd, reach, _hpm = TAC[s.type]
        s.cool -= dt
        s.retarget -= dt
        if s.retarget <= 0:
            tgt, dist = self._nearest_enemy(s)
            s.retarget = 0.7
            if tgt is not None:
                s.tx, s.ty = tgt.x, tgt.y
            else:
                # march toward enemy side / general
                s.tx = -s.x * 0.5
                s.ty = s.y * 0.6
        dx, dy = s.tx - s.x, s.ty - s.y
        dist = math.hypot(dx, dy) or 1.0
        # in reach? attack
        if dist <= reach and s.cool <= 0:
            tgt, _ = self._nearest_enemy(s)
            if tgt is not None and abs(tgt.x - s.x) <= reach + 1:
                s.cool = ATTACK_COOLDOWN * rng.uniform(0.8, 1.3)
                dmg = UNIT_TYPES[s.type][0] * rng.uniform(0.6, 1.5)
                dmg -= UNIT_TYPES[tgt.type][1] * 0.3
                tgt.hp -= max(0.4, dmg)
                if tgt.hp <= 0 and tgt.alive:
                    tgt.alive = False
                    self.kills[tgt.side] += 1
                    k = self.kills[tgt.side]
                    if k % 50 == 0:
                        self._log(f"{k} of {self.name_of(tgt.side)}'s men "
                                  f"lie dead.")
                return
        # move
        step = spd * dt
        if dist > step:
            s.x += dx / dist * step
            s.y += dy / dist * step
        # keep on field
        s.x = max(-FIELD_W / 2, min(FIELD_W / 2, s.x))
        s.y = max(-FIELD_H / 2, min(FIELD_H / 2, s.y))

    def _tick_general(self, g, dt, rng):
        pop = self.sim.population
        foe = next((o for o in self.generals
                    if o.side != g.side and o.alive), None)
        d_foe = math.hypot(foe.x - g.x, foe.y - g.y) if foe else 1e9
        # duel when generals meet
        if foe is not None and d_foe < 6.0:
            if not g.dueling:
                g.dueling = True
                if g.side == 0:  # log the duel once
                    self._log(f"GENERAL DUEL: {g.pawn.display_name()} faces "
                              f"{foe.pawn.display_name()}!")
            dmg = (g.pawn.skills["prowess"] + 4) * rng.uniform(0.3, 1.0) * dt
            foe.hp -= dmg
            if foe.hp <= 0 and foe.alive:
                foe.alive = False
                self._log(f"{g.pawn.display_name()} slays "
                          f"{foe.pawn.display_name()} in single combat!")
                pop.kill(foe.pawn, self.sim.date.day,
                         "slain in a general's duel")
                g.pawn.kills += 1
                self.morale[foe.side] -= 0.15
            return
        g.dueling = False
        # drift toward the battle center of gravity
        cx = sum(s.x for s in self.soldiers if s.alive and s.side == g.side)
        n = max(1, sum(1 for s in self.soldiers if s.alive and s.side == g.side))
        tx = cx / n
        dx = tx - g.x
        g.x += max(-3.0, min(3.0, dx)) * 0.5 * dt * 4
        # rally aura: nearby troops steady the army's morale
        if self.morale[g.side] < 1.0:
            self.morale[g.side] = min(1.0, self.morale[g.side]
                                      + RALLY_RATE * dt * 10)
        # technique blast
        g.tech_cool -= dt
        if g.tech_cool <= 0 and self.phase == "clash":
            tech = g.best_technique(self.sim.tech)
            if tech is not None:
                g.tech_cool = TECH_COOLDOWN * rng.uniform(0.8, 1.4)
                self._unleash(g, tech, rng)
            else:
                g.tech_cool = 8.0

    def _enemies_near_gen(self, g, radius):
        for s in self.soldiers:
            if s.alive and s.side == g.side \
                    and abs(s.x - g.x) < radius and abs(s.y - g.y) < radius:
                yield s

    def _unleash(self, g, tech, rng):
        # aim at the densest enemy cluster
        best, bn = None, 0
        for s in self.soldiers:
            if not s.alive or s.side == g.side:
                continue
            n = sum(1 for e in self._enemies_near(s, 6.0))
            if n > bn:
                best, bn = s, n
        if best is None:
            return
        radius = 5.0 + tech["power"]
        cx, cy = best.x, best.y
        kills = 0
        for e in self.soldiers:
            if e.alive and e.side != g.side \
                    and math.hypot(e.x - cx, e.y - cy) < radius:
                e.hp -= 8.0 + tech["power"] * 4
                if e.hp <= 0:
                    e.alive = False
                    self.kills[e.side] += 1
                    kills += 1
        self.fx.append({"x": cx, "y": cy, "r": radius, "age": 0.0,
                        "side": g.side})
        self._log(f"{g.pawn.display_name()} unleashes "
                  f"'{tech['name']}' — {kills} men fall!")
        g.pawn.prestige += 5

    # ---------------- resolution ----------------
    def _finish(self, winner_side):
        self.phase = "done"
        loser_side = 1 - winner_side
        pop = self.sim.population
        # write survivors back into the strategic armies
        for side, army in enumerate(self.armies):
            scale = self.scale[side]
            survivors = {}
            for s in self.soldiers:
                if s.alive and s.side == side:
                    survivors[s.type] = survivors.get(s.type, 0) + 1
            army.units = {t: max(0, round(n / scale))
                          for t, n in survivors.items() if n > 0}
            army.morale = max(0.3, self.morale[side])
            army.in_battle = False
        wname = self.name_of(winner_side)
        lname = self.name_of(loser_side)
        self.result = {"winner": wname, "loser": lname,
                       "winner_side": winner_side,
                       "kills": [self.kills[0], self.kills[1]]}
        self._log(f"The battle is over. {wname} holds the field.")
        # strategic consequences
        if self.war and self.war.active:
            self.war.battles += 1
            self.war.add_score(12 if self.armies[winner_side].ruler
                               in self.war.attackers else -12)
        loser_army = self.armies[loser_side]
        self.sim.war_engine.rout(loser_army)
        self.sim.bus.record(
            self.sim.date,
            f"Battle of {self.province.name}: {wname} defeats {lname} "
            f"after {self.t:.0f}s of fighting "
            f"({self.kills[0] + self.kills[1]} simulated casualties).",
            "war")

    # ---------------- API ----------------
    def snapshot(self) -> dict:
        units = []
        for s in self.soldiers:
            if s.alive:
                units.append([s.side, _TYPE_IDX[s.type],
                              round(s.x, 1), round(s.y, 1),
                              round(s.hp / s.maxhp, 2)])
        gens = []
        for g in self.generals:
            gens.append({"name": g.pawn.display_name(), "side": g.side,
                         "x": round(g.x, 1), "y": round(g.y, 1),
                         "hp": round(g.hp / g.maxhp, 2),
                         "alive": g.alive, "dueling": g.dueling})
        return {
            "id": self.bid,
            "province": self.province.name,
            "t": round(self.t, 1),
            "phase": self.phase,
            "sides": [
                {"name": self.name_of(0), "morale": round(self.morale[0], 2),
                 "count": sum(1 for s in self.soldiers
                              if s.side == 0 and s.alive),
                 "initial": self.initial[0]},
                {"name": self.name_of(1), "morale": round(self.morale[1], 2),
                 "count": sum(1 for s in self.soldiers
                              if s.side == 1 and s.alive),
                 "initial": self.initial[1]},
            ],
            "generals": gens,
            "units": units,
            "fx": [{"x": f["x"], "y": f["y"], "r": f["r"],
                    "age": round(f["age"], 2), "side": f["side"]}
                   for f in self.fx],
            "events": self.events[-14:],
            "result": self.result,
        }

    def brief(self) -> dict:
        return {"id": self.bid, "province": self.province.name,
                "t": round(self.t, 1), "phase": self.phase,
                "a": self.name_of(0), "b": self.name_of(1),
                "result": self.result}


class BattleManager:
    """Owns all live battles; ticked in real time by the web server."""

    def __init__(self, sim):
        self.sim = sim
        self.battles: dict[int, LiveBattle] = {}
        self._by_army: dict[int, int] = {}

    def has(self, army) -> bool:
        return army.aid in self._by_army

    def spawn(self, army_a, army_b, province, war) -> LiveBattle:
        army_a.in_battle = army_b.in_battle = True
        b = LiveBattle(self.sim, army_a, army_b, province, war)
        self.battles[b.bid] = b
        self._by_army[army_a.aid] = b.bid
        self._by_army[army_b.aid] = b.bid
        return b

    def tick(self, dt: float):
        for b in list(self.battles.values()):
            b.tick(dt)
            if b.phase == "done":
                self._by_army.pop(b.armies[0].aid, None)
                self._by_army.pop(b.armies[1].aid, None)
                b.done_age += dt
        # keep finished battles around briefly for spectators
        for bid, b in list(self.battles.items()):
            if b.phase == "done" and b.done_age > 90:
                del self.battles[bid]

    def active(self) -> list[dict]:
        return [b.brief() for b in self.battles.values()]

    def get(self, bid: int) -> LiveBattle | None:
        return self.battles.get(bid)
