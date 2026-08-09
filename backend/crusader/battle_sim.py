"""Live tactical battles — the Total War layer, doc-aligned.

When two hostile armies meet in web mode, a LiveBattle replaces the instant
resolution: hundreds of individual soldiers fight in real time on a field,
commanded by named generals who are full body-graph pawns (body.py):

  * Generals duel in exchanges: every attack declares a routing across their
    G3 conduit graph, the flow solve decides output, and damage lands on
    specific G1 parts.  A : (Pa, Pd, W, t) -> Δ(Pa, Pd, W).
  * Techniques are geometry-typed (arc / cone / line / radial / cleave /
    point from the combat grammar), not radius blasts.
  * Gates, overdrive ruptures and meridian seals are parameter regimes.
  * Soldiers carry compact mini-bodies (head/torso/arms/legs) so wounds
    slow and weaken before they kill; corpses persist on the field.

Deterministic-friendly: all randomness flows through sim.rng.
Results write back into the strategic layer (Army units, war score, routs,
general wounds and deaths) so a duel can literally change history.
"""
from __future__ import annotations

import math

from .war import UNIT_TYPES
from .body import BodyGraph, EDGE_ORDER, PART_ORDER   # noqa: F401 (re-export)

FIELD_W, FIELD_H = 120.0, 70.0
MAX_SOLDIERS = 350          # per side; larger armies are scaled
ATTACK_COOLDOWN = 0.8
TECH_COOLDOWN = 22.0
RALLY_RADIUS = 14.0
RALLY_RATE = 0.004
ROUT_MORALE = 0.25
MAX_BATTLE_SECONDS = 300.0
ENGAGE_RANGE = 9.0          # generals lock into a duel inside this
DUEL_RANGE = 3.4            # striking distance
DUEL_SEEK_AFTER = 6.0       # generals hunt each other after the clash opens
MAX_CORPSES = 260
PROWESS_CAP = 26.0          # legendary pawns exist; the flesh still has limits

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

# soldier mini-body: part index 0 head, 1 torso, 2 arms, 3 legs
_PART_POOL = (0.50, 1.00, 0.70, 0.70)   # pool size as fraction of maxhp

# fx lifetime per kind (seconds)
_FX_LIFE = {"tech": 1.6, "clash": 0.5, "gate": 1.4, "seal": 0.9,
            "rupture": 0.9, "slain": 2.0}


def _fx_life(kind):
    return _FX_LIFE.get(kind, 1.2)


class Soldier:
    __slots__ = ("uid", "side", "type", "x", "y", "hp", "maxhp", "alive",
                 "cool", "retarget", "tx", "ty", "parts", "strike_t",
                 "hurt_t", "face", "moving")

    def __init__(self, uid, side, type_, x, y):
        self.uid = uid
        self.side = side
        self.type = type_
        self.x, self.y = x, y
        spd, rng_, hpm = TAC[type_]
        self.maxhp = self.hp = 9.0 * UNIT_TYPES[type_][1] * hpm
        self.alive = True
        self.cool = 0.0
        self.retarget = 0.0
        self.tx, self.ty = x, y
        self.parts = [1.0, 1.0, 1.0, 1.0]      # head, torso, arms, legs
        self.strike_t = -9.0
        self.hurt_t = -9.0
        self.face = 1 if side == 0 else -1
        self.moving = False


class Fighter:
    """A general on the field: a full body-graph pawn with an action
    state machine the renderer can animate."""

    __slots__ = ("pawn", "side", "x", "y", "face", "body", "action",
                 "action_t", "action_dur", "adata", "recover", "tech_cool",
                 "dueling", "dead_handled", "strafe", "field_techs",
                 "duel_techs", "gates_known", "seal_tech", "sweep_cool",
                 "routing", "cur_tech")

    def __init__(self, pawn, side, x, y, tech_mgr, rng):
        self.pawn = pawn
        self.side = side
        self.x, self.y = x, y
        self.face = 1 if side == 0 else -1
        conduit = pawn.genome.poly_value("conduit_loci") * 10 \
            + pawn.genome.trait_modifier("conduit")
        self.body = BodyGraph(pawn.skills["prowess"], conduit,
                              pawn.traits, rng)
        self.action = "idle"
        self.action_t = 0.0
        self.action_dur = 0.5
        self.adata = {}
        self.recover = 0.0
        self.tech_cool = TECH_COOLDOWN * 0.4
        self.sweep_cool = 2.0
        self.dueling = False
        self.dead_handled = False
        self.strafe = 1.0 if side == 0 else -1.0
        self.routing = ""
        self.cur_tech = ""
        # sort known techniques into duel kit / field kit / regimes
        self.field_techs = []
        self.duel_techs = []
        self.gates_known = 0
        self.seal_tech = None
        for name in pawn.techniques:
            t = tech_mgr.technique_by_name(name) if tech_mgr else None
            if t is None:
                continue
            if name.startswith("Gate of the"):
                self.gates_known += 1
            elif t["source"] == "ability_resource" and \
                    t["routing"].split(" -> ")[1] == "spiritual":
                self.seal_tech = t
            else:
                self.field_techs.append(t)
                self.duel_techs.append(t)

    @property
    def alive(self) -> bool:
        return self.body.alive

    def _set(self, action, dur, **data):
        self.action = action
        self.action_t = 0.0
        self.action_dur = max(0.05, dur)
        self.adata = data


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
        self.events: list[list] = []          # [kind, text]
        self.fx: list[dict] = []
        self.corpses: list[list] = []         # [x, y, side, type_idx]
        self.scale = [1.0, 1.0]
        self.initial = [0, 0]
        self.kills = [0, 0]
        self.morale = [army_a.morale, army_b.morale]
        self.mbonus = [0.0, 0.0]     # decaying morale swing from heroics
        self.soldiers: list[Soldier] = []
        self.generals: list[Fighter] = []
        self._uid = 0
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
            self.soldiers.append(Soldier(self._uid, side, t, x, y))
            self._uid += 1
        # general behind the center
        pop = self.sim.population
        cmd = pop.get(army.commander)
        if cmd is not None:
            self.generals.append(
                Fighter(cmd, side, x0 - facing * 8.0, 0.0,
                        getattr(self.sim, "tech", None), rng))

    def _log(self, text, kind="log"):
        self.events.append([kind, f"[{self.t:5.1f}s] {text}"])
        if len(self.events) > 60:
            del self.events[:20]

    def _fx_add(self, kind, **kw):
        f = {"k": kind, "age": 0.0}
        f.update(kw)
        self.fx.append(f)

    # ---------------- tick ----------------
    def tick(self, dt: float):
        if self.phase == "done":
            return
        self.t += dt
        if self.phase == "deploy" and self.t > 2.0:
            self.phase = "clash"
            self._log("The lines crash together!", "rout")
        rng = self.sim.rng
        self._grid = {}
        cell = 4.0
        cxs, cys, cnt = [0.0, 0.0], [0.0, 0.0], [0, 0]
        for i, s in enumerate(self.soldiers):
            if s.alive:
                key = (int(s.x // cell), int(s.y // cell))
                self._grid.setdefault(key, []).append(i)
                cxs[s.side] += s.x
                cys[s.side] += s.y
                cnt[s.side] += 1
        # army centers of mass (for marching when no enemy is in sight)
        self._center = [
            (cxs[0] / cnt[0], cys[0] / cnt[0]) if cnt[0] else (-30.0, 0.0),
            (cxs[1] / cnt[1], cys[1] / cnt[1]) if cnt[1] else (30.0, 0.0),
        ]

        for s in self.soldiers:
            if not s.alive:
                continue
            self._tick_soldier(s, dt, rng)
        for g in self.generals:
            self._tick_fighter(g, dt, rng)
        # fx decay
        for f in self.fx:
            f["age"] += dt
        self.fx = [f for f in self.fx if f["age"] < _fx_life(f["k"])]
        # heroics morale swing decays
        for side in (0, 1):
            self.mbonus[side] *= max(0.0, 1.0 - 0.03 * dt)
        # morale from casualties + dead generals + heroics
        for side in (0, 1):
            loss = self.kills[side] / max(1, self.initial[side])
            base = self.armies[side].morale
            dead_gen = any(not g.alive and g.side == side
                           for g in self.generals)
            self.morale[side] = max(0.0, min(1.0,
                base * (1.0 - 0.75 * loss)
                - (0.15 if dead_gen else 0.0) + self.mbonus[side]))
        # rout / end checks
        counts = [sum(1 for s in self.soldiers if s.side == 0 and s.alive),
                  sum(1 for s in self.soldiers if s.side == 1 and s.alive)]
        for side in (0, 1):
            frac = counts[side] / max(1, self.initial[side])
            if self.phase == "clash" and self.t > 5.0 and \
                    (self.morale[side] <= ROUT_MORALE or frac <= 0.12):
                self.phase = "rout"
                self._log(f"{self.name_of(side)}'s army breaks and routs!",
                          "rout")
                if self.rout_side is None:
                    self.rout_side = 1 - side
                    self.rout_timer = 9.0
        if self.phase == "rout" and self.rout_side is not None:
            loser = 1 - self.rout_side
            for s in self.soldiers:
                if s.alive and s.side == loser:
                    s.x += (-1 if loser == 0 else 1) * 6.0 * dt
                    s.face = -1 if loser == 0 else 1
                    s.moving = True
            self.rout_timer -= dt
            if self.rout_timer <= 0:
                self._finish(self.rout_side)
        if self.t > MAX_BATTLE_SECONDS and self.phase != "done":
            winner = 0 if self.morale[0] >= self.morale[1] else 1
            self._finish(winner)

    # ---------------- soldiers ----------------
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

    def _hit_soldier(self, s: Soldier, dmg: float, rng, killer_side=None):
        """Damage lands on a mini-body part: arms weaken, legs slow,
        head/torso kill."""
        r = rng.random()
        if r < 0.12:
            part = 0
            dmg *= 1.2
        elif r < 0.52:
            part = 1
        elif r < 0.78:
            part = 2
        else:
            part = 3
        s.parts[part] -= dmg / (s.maxhp * _PART_POOL[part])
        s.hp -= dmg
        s.hurt_t = self.t
        if s.hp <= 0 or s.parts[0] <= 0 or s.parts[1] <= 0:
            if s.alive:
                s.alive = False
                self.corpses.append([round(s.x, 1), round(s.y, 1),
                                     s.side, _TYPE_IDX[s.type]])
                if len(self.corpses) > MAX_CORPSES:
                    del self.corpses[:len(self.corpses) - MAX_CORPSES]
                self.kills[s.side] += 1
                k = self.kills[s.side]
                if k % 50 == 0:
                    self._log(f"{k} of {self.name_of(s.side)}'s men "
                              f"lie dead.", "kill")
            return True
        return False

    def _tick_soldier(self, s, dt, rng):
        spd, reach, _hpm = TAC[s.type]
        spd *= 0.40 + 0.60 * max(0.0, s.parts[3])      # leg wounds slow
        s.cool -= dt
        s.retarget -= dt
        s.moving = False
        if s.retarget <= 0:
            tgt, dist = self._nearest_enemy(s)
            s.retarget = 0.7
            if tgt is not None:
                s.tx, s.ty = tgt.x, tgt.y
            else:
                # march on the enemy host, holding rank (keep own y)
                ecx, _ecy = self._center[1 - s.side]
                s.tx = ecx
                s.ty = s.y
        dx, dy = s.tx - s.x, s.ty - s.y
        dist = math.hypot(dx, dy) or 1.0
        # in reach? attack
        if dist <= reach and s.cool <= 0:
            tgt, td = self._nearest_enemy(s)
            if tgt is not None and td <= reach + 1:
                s.cool = ATTACK_COOLDOWN * rng.uniform(1.0, 1.6)
                s.strike_t = self.t
                s.face = 1 if tgt.x >= s.x else -1
                dmg = UNIT_TYPES[s.type][0] * rng.uniform(0.5, 1.3)
                dmg *= 0.45 + 0.55 * max(0.0, s.parts[2])   # arm wounds
                dmg -= UNIT_TYPES[tgt.type][1] * 0.3
                self._hit_soldier(tgt, max(0.4, dmg), rng, s.side)
                return
        # move
        step = spd * dt
        if dist > step:
            s.x += dx / dist * step
            s.y += dy / dist * step
            s.moving = True
            if abs(dx) > 0.2:
                s.face = 1 if dx > 0 else -1
        # separation so ranks stay readable instead of stacking
        pushed = 0
        for i in self._grid.get((int(s.x // 4.0), int(s.y // 4.0)), ()):
            o = self.soldiers[i]
            if o is not s and o.alive:
                ox, oy = s.x - o.x, s.y - o.y
                d2 = ox * ox + oy * oy
                if 0.0001 < d2 < 1.44:
                    d = math.sqrt(d2)
                    push = 2.4 * (1.2 - d) * dt
                    s.x += ox / d * push
                    s.y += oy / d * push
                    pushed += 1
                    if pushed >= 2:
                        break
        # keep on field
        s.x = max(-FIELD_W / 2, min(FIELD_W / 2, s.x))
        s.y = max(-FIELD_H / 2, min(FIELD_H / 2, s.y))

    # ---------------- generals (fighters) ----------------
    def _tick_fighter(self, g: Fighter, dt, rng):
        pop = self.sim.population
        # body upkeep: bleeding, regen, gate burn — may drop or kill him
        for kind, text in g.body.tick(dt, rng):
            self._log(f"{g.pawn.display_name()} {text}", kind)
        if not g.body.alive:
            if not g.dead_handled:
                g.dead_handled = True
                cause = g.body.cause or "slain in battle"
                self._log(f"{g.pawn.display_name()} is dead — {cause}.",
                          "kill")
                pop.kill(g.pawn, self.sim.date.day, cause)
                self.mbonus[g.side] -= 0.10
                self._fx_add("slain", x=g.x, y=g.y, side=g.side)
            g.action = "down"
            g.dueling = False
            return
        if g.body.down:
            g.action = "down"
            g.dueling = False
            return

        foe = next((o for o in self.generals
                    if o.side != g.side and o.alive and not o.body.down),
                   None)
        d_foe = math.hypot(foe.x - g.x, foe.y - g.y) if foe else 1e9
        g.dueling = foe is not None and d_foe < ENGAGE_RANGE
        g.action_t += dt
        g.recover = max(0.0, g.recover - dt)
        g.tech_cool -= dt
        g.sweep_cool -= dt

        if g.dueling:
            self._duel_step(g, foe, d_foe, dt, rng)
        else:
            self._field_step(g, foe, d_foe, dt, rng)

        # rally aura: a living general steadies his men
        self.mbonus[g.side] = min(0.25, self.mbonus[g.side]
                                  + RALLY_RATE * dt * 6)
        g.x = max(-FIELD_W / 2, min(FIELD_W / 2, g.x))
        g.y = max(-FIELD_H / 2, min(FIELD_H / 2, g.y))

    # ----- out of duel: follow the host, mow the line, field techniques
    def _field_step(self, g, foe, d_foe, dt, rng):
        spd = 4.0 * g.body.move_mult() * (1 + 0.12 * g.body.gate)
        # after the clash opens, generals hunt each other for the duel
        if foe is not None and self.t > DUEL_SEEK_AFTER \
                and self.phase == "clash":
            dx, dy = foe.x - g.x, foe.y - g.y
            d = math.hypot(dx, dy) or 1.0
            g.x += dx / d * spd * 1.5 * dt
            g.y += dy / d * spd * 1.5 * dt
            g.face = 1 if dx > 0 else -1
            if g.action not in ("channel", "strike"):
                g._set("advance", 0.5)
        else:
            # drift toward own army's center of gravity
            own = [s for s in self.soldiers if s.alive and s.side == g.side]
            if own:
                cx = sum(s.x for s in own) / len(own)
                dx = cx - g.x
                g.x += max(-spd, min(spd, dx)) * dt
                g.face = 1 if dx > 0 else -1
            if g.action not in ("channel", "strike"):
                g._set("advance" if own else "idle", 0.6)
        # cut down nearby enemies with sweeping strikes
        if g.sweep_cool <= 0:
            near = [e for e in self._enemies_near_gen(g, 3.0)][:5]
            if near:
                g.sweep_cool = 1.5
                out, ev, routing = g.body.strike(
                    "hand_r",
                    3.0 + min(g.pawn.skills["prowess"], PROWESS_CAP) * 0.4,
                    1.0, rng)
                g.routing = routing
                for kind, text in ev:
                    self._log(f"{g.pawn.display_name()} — {text}", kind)
                g._set("strike", 0.25)
                kills = 0
                for e in near:
                    if self._hit_soldier(e, 2.0 + out * 0.8, rng, g.side):
                        kills += 1
                self._fx_add("clash", x=g.x + g.face * 1.2, y=g.y,
                             side=g.side, pw=out)
                if kills:
                    g.pawn.kills += kills
        # unleash a field technique on the densest enemy cluster
        if g.tech_cool <= 0 and self.phase == "clash" and g.field_techs:
            tech = max(g.field_techs, key=lambda t: t["power"])
            if g.body.reservoir > tech["power"] * 1.2:
                g.tech_cool = TECH_COOLDOWN * rng.uniform(0.8, 1.4)
                g._set("channel", 0.8, tech=tech, mode="field")
                g.cur_tech = tech["name"]
            else:
                g.tech_cool = 6.0
        # resolve channel / recover from strikes
        if g.action == "channel" and g.action_t >= g.action_dur:
            data = g.adata
            g._set("strike", 0.3)
            if data.get("mode") == "field" and data.get("tech"):
                self._unleash(g, data["tech"], rng)
            g.cur_tech = ""
        elif g.action == "strike" and g.action_t >= g.action_dur:
            g._set("idle", 0.3)

    # ----- the duel: exchange-based, body-graph resolved
    def _duel_step(self, g, foe, d, dt, rng):
        spd = 4.2 * g.body.move_mult() * (1 + 0.15 * g.body.gate)
        g.face = 1 if foe.x >= g.x else -1
        # spacing: close to striking range, then circle
        if g.action == "disengage":
            g.x -= g.face * spd * 1.1 * dt
        elif d > DUEL_RANGE:
            dx, dy = foe.x - g.x, foe.y - g.y
            g.x += dx / d * spd * dt
            g.y += dy / d * spd * dt
            if g.action == "idle":
                g._set("advance", 0.4)
        else:
            # strafe around the opponent
            if rng.chance(0.01):
                g.strafe = -g.strafe
            g.y += g.strafe * spd * 0.35 * dt
        # pick a new action
        if g.action in ("idle", "advance", "guard") and g.recover <= 0 \
                and g.action_t >= g.action_dur:
            self._choose_duel_action(g, foe, d, rng)
        # resolve finished actions
        if g.action_t >= g.action_dur:
            if g.action == "windup":
                self._resolve_strike(g, foe, rng)
            elif g.action == "channel":
                self._resolve_duel_tech(g, foe, rng)
            elif g.action == "gate":
                for kind, text in g.body.open_gate(rng):
                    self._log(f"{g.pawn.display_name()} {text}", kind)
                self.mbonus[g.side] += 0.05
                self._fx_add("gate", x=g.x, y=g.y, side=g.side,
                             lvl=g.body.gate)
                g._set("idle", 0.3)
                g.recover = 0.3
            elif g.action in ("strike", "stagger", "disengage"):
                g._set("idle", 0.2)

    def _choose_duel_action(self, g, foe, d, rng):
        p = g.pawn.personality
        cond = g.body.condition()
        w = []
        if d <= DUEL_RANGE + 0.6:
            w.append(("strike", 4.0 + (2.0 if ("brave" in p or
                                               "wrathful" in p) else 0.0)))
        w.append(("guard", 1.0 + (2.2 if foe.action == "windup" else 0.0)
                  + (1.5 if cond < 0.5 else 0.0)))
        if g.duel_techs and g.tech_cool <= 0:
            best = max(g.duel_techs, key=lambda t: t["power"])
            if g.body.reservoir > best["power"] * 1.2:
                w.append(("tech", 2.6))
        if g.seal_tech and g.tech_cool <= 0 \
                and g.body.reservoir > 6:
            w.append(("seal", 2.0))
        if g.gates_known > g.body.gate:
            desperate = cond < 0.75 or foe.body.gate > g.body.gate \
                or cond < foe.body.condition() - 0.05
            w.append(("gate", 3.2 if desperate else 0.9))
        if "craven" in p and cond < 0.45:
            w.append(("flee", 2.0))
        total = sum(x for _, x in w)
        r = rng.random() * total
        for name, x in w:
            r -= x
            if r <= 0:
                break
        if name == "strike":
            drive = 1.0
            if ("wrathful" in p and rng.chance(0.5)) or \
                    (cond < 0.4 and "brave" in p):
                drive = 1.7          # overdrive: τ ≫ C, rupture risk
            g._set("windup", 0.42 / g.body.attack_speed(), drive=drive)
        elif name == "guard":
            g._set("guard", 0.9)
        elif name == "tech":
            tech = max(g.duel_techs, key=lambda t: t["power"])
            g.tech_cool = 10.0 + tech["power"] * 1.5
            g.cur_tech = tech["name"]
            g._set("channel", 0.75, tech=tech, mode="duel")
        elif name == "seal":
            g.tech_cool = 12.0
            g.cur_tech = g.seal_tech["name"]
            g._set("channel", 0.6, tech=g.seal_tech, mode="seal")
        elif name == "gate":
            g._set("gate", 0.55)
        else:
            g._set("disengage", 0.8)

    def _resolve_strike(self, g, foe, rng):
        drive = g.adata.get("drive", 1.0)
        base = 4.5 + min(g.pawn.skills["prowess"], PROWESS_CAP) * 0.45
        out, ev, routing = g.body.strike("hand_r", base, drive, rng)
        g.routing = routing
        for kind, text in ev:
            self._log(f"{g.pawn.display_name()} — {text}", kind)
            if kind == "rupture":
                self._fx_add("rupture", x=g.x, y=g.y, side=g.side)
        g._set("strike", 0.22)
        g.recover = 0.25 + rng.uniform(0.0, 0.35)
        d = math.hypot(foe.x - g.x, foe.y - g.y)
        if d > DUEL_RANGE + 1.2 or out <= 0:
            return
        # defense: dodge from legs+prowess, block if guarding
        dodge = 0.06 + 0.16 * foe.body.move_mult() \
            * min(1.0, foe.pawn.skills["prowess"] / 16)
        if foe.body.down:
            dodge = 0.0
        if rng.chance(dodge):
            self._fx_add("clash", x=(g.x + foe.x) / 2, y=(g.y + foe.y) / 2,
                         side=g.side, pw=out * 0.3)
            return
        guarding = foe.action == "guard"
        dmg = out * 1.7 * (2.0 if foe.body.down else 1.0)
        ev2, part = foe.body.receive_hit(dmg, "arc", "kinetic",
                                         guarding, rng)
        for kind, text in ev2:
            self._log(f"{foe.pawn.display_name()} {text}", kind)
        self._fx_add("clash", x=(g.x + foe.x) / 2, y=(g.y + foe.y) / 2,
                     side=g.side, pw=out)
        if guarding and rng.chance(0.5):
            foe._set("stagger", 0.3)
        elif part in ("head", "torso", "spine") and rng.chance(0.4):
            foe._set("stagger", 0.4)
        self._check_duel_death(g, foe)

    def _resolve_duel_tech(self, g, foe, rng):
        data = g.adata
        tech = data.get("tech")
        g._set("strike", 0.3)
        g.recover = 0.4
        g.cur_tech = ""
        if tech is None:
            return
        if data.get("mode") == "seal":
            # Gentle Fist: damage typed at the opponent's G3 edges
            ev = foe.body.receive_seal(6.0 + tech["power"] * 2.0, rng)
            for kind, text in ev:
                self._log(f"{g.pawn.display_name()} strikes "
                          f"{foe.pawn.display_name()} — {text}!", kind)
            self._fx_add("seal", x=foe.x, y=foe.y, side=g.side)
            self._log(f"{g.pawn.display_name()} uses '{tech['name']}' — "
                      f"{foe.pawn.display_name()}'s conduits gutter!", "tech")
            return
        # routed strike: effector from the technique's carrier
        effector = "eyes" if tech["source"] == "bloodline" else "hand_r"
        out, ev, routing = g.body.strike(
            effector, 5.0 + tech["power"] * 1.6, 1.2, rng)
        g.routing = routing
        for kind, text in ev:
            self._log(f"{g.pawn.display_name()} — {text}", kind)
        geo = tech["routing"].split(" -> ")[3]
        tr = tech["routing"].split(" -> ")[1]
        dmg = 6.0 + tech["power"] * 2.6 + out * 0.8
        self._fx_add("tech", x=g.x, y=g.y, tx=foe.x, ty=foe.y,
                     r=4.0 + tech["power"], geo=geo, tr=tr,
                     side=g.side, pw=out)
        self._log(f"{g.pawn.display_name()} unleashes '{tech['name']}' "
                  f"[{tech['routing']}]!", "tech")
        ev2, part = foe.body.receive_hit(dmg, geo, tr,
                                         foe.action == "guard", rng)
        for kind, text in ev2:
            self._log(f"{foe.pawn.display_name()} {text}", kind)
        # wide geometries splash the foe's nearby soldiers too
        if geo in ("cone", "radial", "cleave", "arc"):
            kills = 0
            for e in self.soldiers:
                if e.alive and e.side != g.side and \
                        math.hypot(e.x - foe.x, e.y - foe.y) < 4.0 + tech["power"]:
                    if self._hit_soldier(e, dmg * 0.5, rng, g.side):
                        kills += 1
            if kills:
                g.pawn.kills += kills
                self.mbonus[foe.side] -= 0.004 * kills
        self._check_duel_death(g, foe)

    def _check_duel_death(self, g, foe):
        if foe.body.alive:
            return
        if not foe.dead_handled:
            foe.dead_handled = True
            cause = foe.body.cause or "slain in a general's duel"
            self._log(f"{g.pawn.display_name()} slays "
                      f"{foe.pawn.display_name()} in single combat!", "duel")
            self.sim.population.kill(foe.pawn, self.sim.date.day, cause)
            g.pawn.kills += 1
            g.pawn.prestige += 12
            self.mbonus[foe.side] -= 0.15
            self.mbonus[g.side] += 0.08
            self._fx_add("slain", x=foe.x, y=foe.y, side=foe.side)

    def _enemies_near_gen(self, g, radius):
        for s in self.soldiers:
            if s.alive and s.side != g.side \
                    and abs(s.x - g.x) < radius and abs(s.y - g.y) < radius:
                yield s

    # ----- field techniques: geometry-typed footprints, not circles
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
        effector = "eyes" if tech["source"] == "bloodline" else "hand_r"
        out, ev, routing = g.body.strike(
            effector, 5.0 + tech["power"] * 1.6, 1.0, rng)
        g.routing = routing
        for kind, text in ev:
            self._log(f"{g.pawn.display_name()} — {text}", kind)
        geo = tech["routing"].split(" -> ")[3]
        tr = tech["routing"].split(" -> ")[1]
        cx, cy = best.x, best.y
        dirx, diry = cx - g.x, cy - g.y
        dd = math.hypot(dirx, diry) or 1.0
        dirx, diry = dirx / dd, diry / dd
        r = 4.5 + tech["power"]
        dmg = 7.0 + tech["power"] * 3.2 + out
        kills = 0
        for e in self.soldiers:
            if not e.alive or e.side == g.side:
                continue
            hit, falloff = self._in_footprint(g, e, geo, cx, cy,
                                              dirx, diry, r)
            if hit:
                if self._hit_soldier(e, dmg * falloff, rng, g.side):
                    kills += 1
        self._fx_add("tech", x=g.x, y=g.y, tx=cx, ty=cy, r=r, geo=geo,
                     tr=tr, side=g.side, pw=out)
        self._log(f"{g.pawn.display_name()} unleashes '{tech['name']}' "
                  f"[{tech['routing']}] — {kills} men fall!", "tech")
        g.pawn.prestige += 5
        g.pawn.kills += kills
        self.mbonus[g.side] += min(0.06, 0.004 * kills)
        self.mbonus[1 - g.side] -= min(0.05, 0.003 * kills)

    def _in_footprint(self, g, e, geo, cx, cy, dirx, diry, r):
        """Is soldier e inside the technique's geometry? -> (hit, falloff)"""
        if geo == "radial":
            d = math.hypot(e.x - cx, e.y - cy)
            return d < r, max(0.4, 1 - d / (r + 0.1) * 0.6)
        if geo == "point":
            d = math.hypot(e.x - cx, e.y - cy)
            return d < 2.2, 1.0
        # ray geometries emanate from the fighter
        rx, ry = e.x - g.x, e.y - g.y
        along = rx * dirx + ry * diry
        perp = abs(rx * -diry + ry * dirx)
        if geo == "cone":
            if along < 0 or along > r * 1.9:
                return False, 0.0
            return perp < along * 0.55 + 0.5, max(0.4, 1 - along / (r * 2.2))
        if geo == "line":
            return (0 < along < r * 2.6 and perp < 1.5), 1.0
        if geo == "cleave":
            return (0 < along < r * 1.6 and perp < 1.0), 1.0
        if geo == "arc":
            d = math.hypot(rx, ry)
            return (d < 5.0 and along > -1.0), max(0.5, 1 - d / 6.0)
        d = math.hypot(e.x - cx, e.y - cy)
        return d < r, 1.0

    # ---------------- resolution ----------------
    def _finish(self, winner_side):
        self.phase = "done"
        loser_side = 1 - winner_side
        pop = self.sim.population
        rng = self.sim.rng
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
        # generals carry their wounds (and gates burn) into history
        for g in self.generals:
            self._persist_fighter(g, loser_side, rng)
        wname = self.name_of(winner_side)
        lname = self.name_of(loser_side)
        self.result = {"winner": wname, "loser": lname,
                       "winner_side": winner_side,
                       "kills": [self.kills[0], self.kills[1]]}
        self._log(f"The battle is over. {wname} holds the field.", "result")
        # strategic consequences
        if self.war and self.war.active:
            self.war.battles += 1
            self.war.add_score(12 if self.armies[winner_side].ruler
                               in self.war.attackers else -12)
        winner_cmd = next((g.pawn for g in self.generals
                           if g.side == winner_side and g.body.alive), None)
        if winner_cmd is not None:
            winner_cmd.prestige += 8
        loser_army = self.armies[loser_side]
        self.sim.war_engine.rout(loser_army)
        self.sim.bus.record(
            self.sim.date,
            f"Battle of {self.province.name}: {wname} defeats {lname} "
            f"after {self.t:.0f}s of fighting "
            f"({self.kills[0] + self.kills[1]} simulated casualties).",
            "war")

    def _persist_fighter(self, g: Fighter, loser_side, rng):
        """Duel wounds cascade into the strategic layer."""
        p = g.pawn
        if not g.body.alive:
            return                      # death already recorded mid-battle
        wounds = g.body.wound_names()
        if wounds:
            for w in wounds:
                if w not in p.wounds:
                    p.wounds.append(w)
            del p.wounds[:-10]
            p.health = max(0.6, p.health - g.body.wound_severity() * 0.6)
            worst = wounds[0]
            if g.body.wound_severity() > 0.8:
                self.sim.bus.record(
                    self.sim.date,
                    f"{p.display_name()} bears a {worst} from the Battle "
                    f"of {self.province.name}.", "war")
        if g.body.gate >= 6:
            p.health = max(0.4, p.health - 0.5)
            self.sim.bus.record(
                self.sim.date,
                f"The gates have scarred {p.display_name()}'s body; "
                f"he will never be whole again.", "war")
        # a downed loser may be finished on the field
        if g.body.down and g.side == loser_side and rng.chance(0.30):
            self.sim.population.kill(
                p, self.sim.date.day,
                f"succumbed to wounds after the Battle of "
                f"{self.province.name}")
            self._log(f"{p.display_name()} succumbs to his wounds.", "kill")

    # ---------------- API ----------------
    def snapshot(self) -> dict:
        units = []
        for s in self.soldiers:
            if not s.alive:
                continue
            if self.t - s.strike_t < 0.35:
                anim = 2
            elif self.t - s.hurt_t < 0.30:
                anim = 3
            elif s.moving:
                anim = 1
            else:
                anim = 0
            units.append([s.uid, s.side, _TYPE_IDX[s.type],
                          round(s.x, 1), round(s.y, 1),
                          round(max(0.0, s.hp / s.maxhp), 2),
                          s.face, anim])
        gens = []
        for g in self.generals:
            entry = {"name": g.pawn.display_name(), "side": g.side,
                     "x": round(g.x, 1), "y": round(g.y, 1),
                     "face": g.face,
                     "alive": g.body.alive, "down": g.body.down,
                     "dueling": g.dueling,
                     "action": g.action,
                     "at": round(min(1.0, g.action_t /
                                     max(0.05, g.action_dur)), 2),
                     "cond": round(g.body.condition(), 2),
                     "routing": g.routing,
                     "tech": g.cur_tech}
            entry.update(g.body.snapshot())
            gens.append(entry)
        duel = None
        pair = [i for i, g in enumerate(self.generals) if g.dueling]
        if len(pair) >= 2:
            duel = {"a": pair[0], "b": pair[1]}
        return {
            "v": 2,
            "id": self.bid,
            "province": self.province.name,
            "t": round(self.t, 1),
            "phase": self.phase,
            "sides": [
                {"name": self.name_of(0), "morale": round(self.morale[0], 2),
                 "count": sum(1 for s in self.soldiers
                              if s.side == 0 and s.alive),
                 "initial": self.initial[0],
                 "kills": self.kills[1]},
                {"name": self.name_of(1), "morale": round(self.morale[1], 2),
                 "count": sum(1 for s in self.soldiers
                              if s.side == 1 and s.alive),
                 "initial": self.initial[1],
                 "kills": self.kills[0]},
            ],
            "generals": gens,
            "duel": duel,
            "units": units,
            "corpses": self.corpses[-240:],
            "fx": [{k: (round(v, 2) if isinstance(v, float) else v)
                    for k, v in f.items()} for f in self.fx],
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
