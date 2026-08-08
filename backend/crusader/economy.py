"""Elaborate economy: goods, province production & stockpiles, supply/demand
pricing, taxes, trade between neighboring provinces, buildings, development.
"""
from __future__ import annotations

GOODS = ["grain", "fish", "wood", "stone", "iron", "salt", "wine", "cloth",
         "tools", "weapons", "horses", "spices", "gold_ore", "gems"]

BASE_PRICE = {"grain": 1.0, "fish": 1.2, "wood": 0.8, "stone": 0.9,
              "iron": 2.5, "salt": 1.8, "wine": 3.0, "cloth": 2.2,
              "tools": 4.0, "weapons": 6.0, "horses": 12.0,
              "spices": 8.0, "gold_ore": 10.0, "gems": 15.0}

# what each biome yields per worker-day
BIOME_YIELDS = {
    "plains": {"grain": 1.4, "horses": 0.05},
    "forest": {"wood": 1.2, "grain": 0.3},
    "taiga": {"wood": 1.0, "fish": 0.2},
    "hills": {"stone": 0.8, "iron": 0.25, "grain": 0.4},
    "mountain": {"iron": 0.5, "gems": 0.03, "stone": 0.6},
    "desert": {"spices": 0.2, "salt": 0.4},
    "steppe": {"horses": 0.2, "grain": 0.5},
    "jungle": {"spices": 0.35, "wood": 0.8},
    "marsh": {"salt": 0.3, "fish": 0.4, "grain": 0.3},
    "beach": {"fish": 1.2, "salt": 0.3},
    "snow": {"fish": 0.3, "wood": 0.4},
}

JOB_GOOD = {"farmer": "grain", "fisher": "fish", "woodcutter": "wood",
            "miner": "iron", "mason": "stone", "weaver": "cloth",
            "smith": "tools", "trader": None}

BUILDINGS = {
    "farm":      {"cost": 40, "good": "grain", "bonus": 0.6, "terr": ["plains", "steppe"]},
    "fishery":   {"cost": 30, "good": "fish", "bonus": 0.6, "terr": ["beach"]},
    "lumber_camp": {"cost": 30, "good": "wood", "bonus": 0.6, "terr": ["forest", "taiga", "jungle"]},
    "quarry":    {"cost": 45, "good": "stone", "bonus": 0.6, "terr": ["hills", "mountain"]},
    "mine":      {"cost": 60, "good": "iron", "bonus": 0.7, "terr": ["hills", "mountain"]},
    "vineyard":  {"cost": 50, "good": "wine", "bonus": 0.5, "terr": ["hills", "plains"]},
    "market":    {"cost": 70, "good": None, "bonus": 0.15, "terr": []},  # trade income
    "walls":     {"cost": 90, "good": None, "bonus": 0.0, "terr": []},   # +1 fort
}


class EconomyManager:
    def __init__(self, sim):
        self.sim = sim
        self.stock: dict[int, dict[str, float]] = {}    # province -> good -> qty
        self.buildings: dict[int, list[str]] = {}       # province -> buildings
        self.prices: dict[str, float] = dict(BASE_PRICE)
        self._supply = {g: 100.0 for g in GOODS}
        self._demand = {g: 100.0 for g in GOODS}

    def prov_stock(self, pid) -> dict[str, float]:
        return self.stock.setdefault(pid, {g: 0.0 for g in GOODS})

    # ---- called from Population.work ----
    def pawn_produce(self, pawn):
        prov = self.sim.world.provinces[pawn.province]
        yields = BIOME_YIELDS.get(prov.biome, {})
        stock = self.prov_stock(pawn.province)
        good = JOB_GOOD.get(pawn.job)
        skill = 0.5 + pawn.labor.get(pawn.job, 0) * 0.05
        if good is None:  # trader moves goods, earns gold
            pawn.gold += 0.05
            return
        amount = yields.get(good, 0.2) * skill
        for b in self.buildings.get(pawn.province, ()):
            spec = BUILDINGS[b]
            if spec["good"] == good:
                amount *= 1 + spec["bonus"]
        stock[good] += amount
        self._supply[good] += amount

    # ---- monthly ----
    def monthly(self):
        rng = self.sim.rng
        pop = self.sim.population
        wm = self.sim.world
        # consumption: every pawn eats
        for pid, members in pop.by_province.items():
            if not members:
                continue
            stock = self.prov_stock(pid)
            need = len(members) * 0.9
            eat = min(stock["grain"] + stock["fish"], need)
            ratio = eat / need if need else 1.0
            # starvation
            if ratio < 0.5 and rng.chance(0.1):
                victims = [pop.get(i) for i in list(members)[:3]]
                for v in victims:
                    if v and rng.chance(0.05):
                        pop.kill(v, self.sim.date.day, "starved")
            grain_eat = min(stock["grain"], eat)
            stock["grain"] -= grain_eat
            stock["fish"] -= min(stock["fish"], eat - grain_eat)
            self._demand["grain"] += need
        # decay aggregates so prices track recent flows
        for g in GOODS:
            self._supply[g] = self._supply[g] * 0.9 + 10
            self._demand[g] = self._demand[g] * 0.9 + 10
            target = BASE_PRICE[g] * (self._demand[g] / max(1.0, self._supply[g]))
            self.prices[g] += (target - self.prices[g]) * 0.2
        # trade: neighbors equalize stock, generating gold for traders
        for prov in wm.provinces:
            if not prov.neighbors:
                continue
            stock = self.prov_stock(prov.pid)
            nb = rng.choice(tuple(prov.neighbors))
            nstock = self.prov_stock(nb)
            for g in ("grain", "wood", "iron", "wine", "spices", "salt"):
                diff = (stock[g] - nstock[g]) * 0.1
                if abs(diff) > 0.5:
                    stock[g] -= diff
                    nstock[g] += diff
        # ruler taxes & building construction
        dyn = self.sim.dynasties
        for ruler_pid in list(dyn.rulers):
            ruler = pop.get(ruler_pid)
            if ruler is None:
                continue
            title = dyn.top_title(ruler)
            if title is None:
                continue
            income = 0.0
            for pid in title.provinces:
                prov = wm.provinces[pid]
                stock = self.prov_stock(pid)
                value = sum(stock[g] * self.prices[g] for g in GOODS)
                tax = value * 0.02
                income += tax
                if "market" in self.buildings.get(pid, ()):
                    income += value * 0.01
            vassals = dyn.vassals_of(ruler)
            income += sum(v.gold * 0.05 for v in vassals)
            ruler.gold += income
            # AI rulers invest in buildings
            if ruler.gold > 120 and rng.chance(0.3):
                self.build_for(ruler, title)
        # development growth
        for prov in wm.provinces:
            if self.buildings.get(prov.pid):
                prov.development = min(100, prov.development + 0.02)

    def build_for(self, ruler, title):
        rng = self.sim.rng
        wm = self.sim.world
        options = []
        for pid in title.provinces:
            prov = wm.provinces[pid]
            have = set(self.buildings.get(pid, ()))
            for b, spec in BUILDINGS.items():
                if b in have:
                    continue
                if spec["terr"] and prov.biome not in spec["terr"]:
                    continue
                if b == "walls" and prov.holding != "castle":
                    continue
                options.append((pid, b, spec))
        if not options:
            return
        pid, b, spec = rng.choice(options)
        if ruler.gold < spec["cost"]:
            return
        ruler.gold -= spec["cost"]
        self.buildings.setdefault(pid, []).append(b)
        if b == "walls":
            wm.provinces[pid].fort_level += 1
        self.sim.bus.record(
            self.sim.date,
            f"{ruler.display_name()} builds a {b.replace('_', ' ')} "
            f"in {wm.provinces[pid].name}.", "economy")

    def realm_gdp(self, ruler) -> float:
        title = self.sim.dynasties.top_title(ruler)
        if title is None:
            return 0.0
        total = 0.0
        for pid in title.provinces:
            stock = self.stock.get(pid)
            if stock:
                total += sum(stock[g] * self.prices[g] for g in GOODS)
        return total
