"""Enormous crafting tree: raw -> processed -> components -> equipment.
A directed acyclic recipe graph worked by smiths/masons/weavers in workshops.
"""
from __future__ import annotations

# recipe: output -> (inputs {good: qty}, job, workstation, output_qty)
RECIPES: dict[str, tuple[dict, str, str, float]] = {
    # --- raw processing ---
    "plank":          ({"wood": 2}, "woodcutter", "sawpit", 2),
    "charcoal":       ({"wood": 3}, "woodcutter", "kiln", 2),
    "iron_ingot":     ({"iron": 2, "charcoal": 1}, "smith", "forge", 1),
    "steel_ingot":    ({"iron_ingot": 2, "charcoal": 2}, "smith", "forge", 1),
    "stone_block":    ({"stone": 2}, "mason", "masonry", 2),
    "salt_block":     ({"salt": 2}, "laborer", "saltern", 1),
    "flour":          ({"grain": 2}, "farmer", "mill", 2),
    "bread":          ({"flour": 1, "salt_block": 0.1}, "farmer", "bakery", 2),
    "ale":            ({"grain": 2}, "farmer", "brewery", 2),
    "wine_bottle":    ({"wine": 1}, "farmer", "winery", 1),
    "leather":        ({"horses": 0.2}, "laborer", "tannery", 1),
    "thread":         ({"cloth": 0.5}, "weaver", "loom", 2),
    "fine_cloth":     ({"thread": 3}, "weaver", "loom", 1),
    "dye":            ({"spices": 0.5}, "weaver", "dyeworks", 1),
    "gold_ingot":     ({"gold_ore": 2, "charcoal": 1}, "smith", "forge", 1),
    "cut_gem":        ({"gems": 1}, "smith", "jeweler", 1),
    "salted_fish":    ({"fish": 2, "salt_block": 0.2}, "fisher", "smokehouse", 2),
    "spice_powder":   ({"spices": 1}, "laborer", "mortar", 1),
    # --- components ---
    "blade":          ({"steel_ingot": 1}, "smith", "forge", 1),
    "axe_head":       ({"iron_ingot": 1}, "smith", "forge", 1),
    "shaft":          ({"plank": 1}, "woodcutter", "carpentry", 2),
    "bowstave":       ({"plank": 1}, "woodcutter", "carpentry", 1),
    "bowstring":      ({"thread": 1}, "weaver", "loom", 1),
    "arrowhead":      ({"iron_ingot": 0.2}, "smith", "forge", 5),
    "shield_blank":   ({"plank": 2}, "woodcutter", "carpentry", 1),
    "mail_rings":     ({"iron_ingot": 1}, "smith", "forge", 1),
    "plate_segment":  ({"steel_ingot": 2}, "smith", "forge", 1),
    "hilt":           ({"plank": 0.5, "leather": 0.5}, "smith", "forge", 1),
    "saddle_tree":    ({"plank": 2}, "woodcutter", "carpentry", 1),
    "wagon_wheel":    ({"plank": 3, "iron_ingot": 0.5}, "woodcutter", "carpentry", 1),
    "brick":          ({"stone": 1, "charcoal": 0.5}, "mason", "kiln", 3),
    "mortar_mix":     ({"stone": 1, "salt_block": 0.1}, "mason", "masonry", 2),
    "glass":          ({"salt_block": 1, "charcoal": 1}, "mason", "glassworks", 1),
    "parchment":      ({"leather": 1}, "scholar", "scriptorium", 2),
    "ink":            ({"charcoal": 0.5, "wine_bottle": 0.1}, "scholar", "scriptorium", 1),
    "rope":           ({"thread": 2}, "weaver", "ropewalk", 2),
    "nails":          ({"iron_ingot": 0.3}, "smith", "forge", 10),
    "lock_mechanism": ({"iron_ingot": 0.5, "nails": 2}, "smith", "forge", 1),
    "cog":            ({"plank": 1, "nails": 2}, "woodcutter", "carpentry", 2),
    "bellows":        ({"leather": 1, "plank": 1}, "smith", "forge", 1),
    # --- equipment ---
    "spear":          ({"shaft": 1, "axe_head": 0.5}, "smith", "forge", 1),
    "sword":          ({"blade": 1, "hilt": 1}, "smith", "forge", 1),
    "greatsword":     ({"blade": 2, "hilt": 1, "leather": 0.5}, "smith", "forge", 1),
    "axe":            ({"axe_head": 1, "shaft": 1}, "smith", "forge", 1),
    "war_hammer":     ({"iron_ingot": 1.5, "shaft": 1}, "smith", "forge", 1),
    "dagger":         ({"iron_ingot": 0.5, "hilt": 1}, "smith", "forge", 1),
    "pike":           ({"shaft": 2, "iron_ingot": 0.5}, "smith", "forge", 1),
    "bow":            ({"bowstave": 1, "bowstring": 1}, "woodcutter", "carpentry", 1),
    "crossbow":       ({"bowstave": 1, "lock_mechanism": 1, "rope": 0.5}, "smith", "forge", 1),
    "arrows":         ({"arrowhead": 5, "shaft": 1}, "woodcutter", "carpentry", 5),
    "shield":         ({"shield_blank": 1, "leather": 0.5, "nails": 2}, "woodcutter", "carpentry", 1),
    "kite_shield":    ({"shield_blank": 1, "iron_ingot": 0.5, "leather": 1}, "smith", "forge", 1),
    "chainmail":      ({"mail_rings": 3, "leather": 1}, "smith", "forge", 1),
    "plate_armor":    ({"plate_segment": 4, "leather": 2, "nails": 4}, "smith", "forge", 1),
    "helmet":         ({"iron_ingot": 1, "leather": 0.5}, "smith", "forge", 1),
    "gauntlets":      ({"plate_segment": 1, "leather": 0.5}, "smith", "forge", 1),
    "riding_saddle":  ({"saddle_tree": 1, "leather": 2}, "woodcutter", "carpentry", 1),
    "war_barding":    ({"mail_rings": 2, "plate_segment": 2}, "smith", "forge", 1),
    # --- civic / luxury ---
    "wagon":          ({"wagon_wheel": 4, "plank": 6, "nails": 6}, "woodcutter", "carpentry", 1),
    "millstone":      ({"stone_block": 2}, "mason", "masonry", 1),
    "house_frame":    ({"plank": 8, "nails": 10}, "mason", "masonry", 1),
    "keep_wall":      ({"stone_block": 10, "mortar_mix": 4}, "mason", "masonry", 1),
    "cathedral_arch": ({"stone_block": 15, "glass": 4, "mortar_mix": 5}, "mason", "masonry", 1),
    "bridge_span":    ({"stone_block": 8, "plank": 4}, "mason", "masonry", 1),
    "book":           ({"parchment": 4, "ink": 1, "leather": 0.5}, "scholar", "scriptorium", 1),
    "tome_of_lore":   ({"book": 3, "cut_gem": 0.2}, "scholar", "scriptorium", 1),
    "tapestry":       ({"fine_cloth": 3, "dye": 2}, "weaver", "loom", 1),
    "noble_garb":     ({"fine_cloth": 2, "dye": 1, "gold_ingot": 0.1}, "weaver", "loom", 1),
    "crown":          ({"gold_ingot": 2, "cut_gem": 2}, "smith", "jeweler", 1),
    "holy_relic":     ({"gold_ingot": 1, "cut_gem": 1, "glass": 1}, "priest", "shrine", 1),
    "chalice":        ({"gold_ingot": 1}, "smith", "jeweler", 1),
    "spiced_feast":   ({"bread": 2, "salted_fish": 1, "wine_bottle": 1, "spice_powder": 0.5}, "farmer", "kitchen", 1),
    "medicine":       ({"spice_powder": 1, "ale": 0.5}, "scholar", "apothecary", 1),
    "compass":        ({"iron_ingot": 0.3, "glass": 0.5, "plank": 0.3}, "scholar", "workshop", 1),
    "clockwork":      ({"cog": 6, "steel_ingot": 1}, "smith", "workshop", 1),
    "astrolabe":      ({"steel_ingot": 0.5, "glass": 0.5}, "scholar", "workshop", 1),
    # --- siege & naval ---
    "battering_ram":  ({"plank": 10, "iron_ingot": 2, "rope": 4}, "mason", "siege_yard", 1),
    "siege_tower":    ({"plank": 20, "wagon_wheel": 4, "nails": 20}, "mason", "siege_yard", 1),
    "trebuchet":      ({"plank": 15, "stone_block": 4, "rope": 6}, "mason", "siege_yard", 1),
    "bombard":        ({"steel_ingot": 6, "charcoal": 4}, "smith", "siege_yard", 1),
    "galley_hull":    ({"plank": 25, "nails": 30, "rope": 8}, "woodcutter", "shipyard", 1),
    "longship":       ({"galley_hull": 1, "fine_cloth": 2}, "woodcutter", "shipyard", 1),
    "carrack":        ({"galley_hull": 2, "cog": 8, "fine_cloth": 6}, "woodcutter", "shipyard", 1),
}


class CraftingManager:
    def __init__(self, sim):
        self.sim = sim
        self.recipes = RECIPES
        self._validate_dag()

    def _validate_dag(self):
        """Ensure the recipe graph is acyclic."""
        color = {}
        def visit(node, stack):
            if color.get(node) == 1:
                raise ValueError(f"cycle at {node}: {stack}")
            if color.get(node) == 2:
                return
            color[node] = 1
            if node in self.recipes:
                for inp in self.recipes[node][0]:
                    visit(inp, stack + [node])
            color[node] = 2
        for out in self.recipes:
            visit(out, [])

    def depth_of(self, good: str, _seen=None) -> int:
        _seen = _seen or set()
        if good not in self.recipes or good in _seen:
            return 0
        _seen = _seen | {good}
        return 1 + max((self.depth_of(g, _seen)
                        for g in self.recipes[good][0]), default=0)

    def deepest_chains(self, n=8):
        return sorted(self.recipes, key=self.depth_of, reverse=True)[:n]

    def count(self) -> int:
        return len(self.recipes)

    # ---- monthly production in provinces with workshops ----
    def monthly(self):
        pop = self.sim.population
        eco = self.sim.economy
        for prov in self.sim.world.provinces:
            stock = eco.prov_stock(prov.pid)
            workers = [pop.get(i) for i in
                       list(pop.by_province.get(prov.pid, ()))[:40]]
            for w in workers:
                if w is None or w.job not in ("smith", "mason", "weaver",
                                              "woodcutter", "scholar"):
                    continue
                # pick the deepest recipe this worker can fully supply
                best = None
                for out, (inputs, job, _ws, qty) in self.recipes.items():
                    if job != w.job:
                        continue
                    if all(stock.get(g, 0) >= q for g, q in inputs.items()):
                        if best is None or self.depth_of(out) > self.depth_of(best[0]):
                            best = (out, inputs, qty)
                if best:
                    out, inputs, qty = best
                    # intermediate goods live in a virtual stock namespace
                    for g, q in inputs.items():
                        if g in stock:
                            stock[g] -= q
                    if out in stock:
                        stock[out] += qty
                    else:
                        # virtual intermediate: track in stock anyway
                        stock[out] = stock.get(out, 0) + qty
                    w.gold += eco.prices.get(out, eco.prices.get("tools", 4)) * 0.02
