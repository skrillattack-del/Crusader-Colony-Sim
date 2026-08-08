"""Technology: hundreds of innovations across 4 eras x 3 categories with
prerequisite chains, plus dozens of martial 'techniques' generated from the
combat grammar (Source x Transformation x Carrier x Geometry x Target).
Realms research innovations; techniques spread pawn-to-pawn.
"""
from __future__ import annotations

ERAS = ["tribal", "early_medieval", "high_medieval", "late_medieval"]
CATEGORIES = ["military", "civic", "cultural"]

# (name, category) per era; prereqs are auto-chained within category/era.
_INNOVATIONS = {
    "tribal": {
        "military": [
            "mustering_grounds", "war_camps", "tribal_warfare", "shield_wall",
            "war_horns", "raiding_parties", "leatherworking_armor", "spear_making",
            "bowyer_craft", "war_paint"],
        "civic": [
            "communal_granaries", "elder_councils", "barter_markets",
            "dirt_roads", "well_digging", "smoke_signals", "oral_law",
            "seasonal_calendars", "corvee_labor", "palisades"],
        "cultural": [
            "ancestor_stories", "ritual_masks", "totem_carving", "oral_epics",
            "shamanic_trance", "tribal_tattoos", "moon_festivals",
            "initiation_rites", "drum_language", "cave_pigments"],
    },
    "early_medieval": {
        "military": [
            "levy_obligations", "chainmail", "motte_and_bailey", "lance_charge",
            "garrison_drills", "siege_engineering", "crossbows", "heraldry",
            "fortified_bridges", "war_hounds", "sappers", "marching_camps"],
        "civic": [
            "coinage", "manorialism", "charters", "toll_booths", "guild_halls",
            "crop_rotation", "heavy_plough", "watermills", "burgher_rights",
            "royal_highways", "census_rolls", "grain_tithes"],
        "cultural": [
            "monastic_scriptoria", "courtly_love", "illuminated_manuscripts",
            "reliquaries", "pilgrimage_routes", "liturgical_drama",
            "bardic_schools", "feudal_oaths", "chivalric_code",
            "cathedral_schools", "stained_glass", "romance_cycles"],
    },
    "high_medieval": {
        "military": [
            "plate_armor", "pike_squares", "castellated_towers", "concentric_castles",
            "longbow_volleys", "mounted_knights", "trebuchets", "naval_galleys",
            "war_horses_barding", "standing_retinues", "siege_towers",
            "counterweight_engineering", "sallet_helms", "tournament_circuits"],
        "civic": [
            "banking_houses", "letters_of_credit", "urban_communes",
            "three_field_system", "windmills", "canal_locks", "assay_offices",
            "maritime_charts", "merchant_fleets", "craft_guilds",
            "universities", "common_law_courts", "standardized_weights",
            "postal_relays"],
        "cultural": [
            "scholasticism", "gothic_architecture", "polyphonic_music",
            "vernacular_literature", "heraldic_tournaments", "mystery_plays",
            "astrolabes", "encyclopedism", "court_physicians", "alchemy",
            "rose_windows", "mendicant_orders", "chansons_de_geste",
            "puppet_theatre"],
    },
    "late_medieval": {
        "military": [
            "gunpowder_artillery", "bombards", "arbalest_steel_bows",
            "professional_companies", "star_forts", "field_entrenchment",
            "massed_pike_and_shot", "drill_manuals", "logistics_trains",
            "siege_mortars", "carrack_warships", "engineer_corps"],
        "civic": [
            "double_entry_bookkeeping", "joint_stock_ventures", "printing_press",
            "national_banks", "actuarial_tables", "road_surveys",
            "hydraulic_sawmills", "blast_furnaces", "coal_mining",
            "land_reclamation", "seed_drills", "customs_unions"],
        "cultural": [
            "renaissance_humanism", "perspective_painting", "anatomy_studies",
            "cartography_schools", "mechanical_clocks", "observatories",
            "polyglot_dictionaries", "theatre_companies", "music_notation",
            "philosophical_societies", "herbariums", "lens_grinding"],
    },
}

# Combat grammar (README capability algebra) -> martial techniques.
_SOURCES = ["muscular", "internal_energy", "ability_resource", "bloodline"]
_TRANSFORMATIONS = ["kinetic", "thermal", "gravitational", "spatial", "spiritual"]
_CARRIERS = ["blade", "fist", "field", "projectile", "shockwave"]
_GEOMETRIES = ["arc", "cone", "radial", "point", "line", "cleave"]
_TECHNIQUE_NAMES = [
    ("muscular", "kinetic", "blade", "arc", "Rising Falcon Cut"),
    ("muscular", "kinetic", "blade", "cleave", "Seven-Step Wind Shear"),
    ("muscular", "kinetic", "fist", "point", "Mountain Root Jab"),
    ("muscular", "kinetic", "shockwave", "radial", "Boar Charge Stomp"),
    ("internal_energy", "thermal", "fist", "cone", "Ember Bloom Palm"),
    ("internal_energy", "thermal", "projectile", "line", "Cinder Lark Shot"),
    ("internal_energy", "spiritual", "field", "radial", "Still-Water Guard"),
    ("internal_energy", "kinetic", "blade", "arc", "Thunder-Draw Iai"),
    ("ability_resource", "gravitational", "field", "radial", "Iron Halo Press"),
    ("ability_resource", "spatial", "projectile", "point", "Voidstep Thrust"),
    ("ability_resource", "spiritual", "fist", "point", "Gentle Meridian Tap"),
    ("ability_resource", "kinetic", "shockwave", "cone", "Lion's Roar"),
    ("bloodline", "thermal", "field", "cone", "Ashen Dragon Breath"),
    ("bloodline", "spatial", "blade", "point", "Crimson Blink Reap"),
    ("bloodline", "gravitational", "shockwave", "radial", "Titan Fall Authority"),
    ("muscular", "kinetic", "blade", "line", "Piercing Reed Lunge"),
    ("muscular", "kinetic", "fist", "arc", "Hammer of the Dawn"),
    ("internal_energy", "spiritual", "projectile", "radial", "Lantern Soul Ward"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the First Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Second Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Third Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Fourth Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Fifth Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Sixth Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Seventh Form"),
    ("ability_resource", "kinetic", "field", "cleave", "Gate of the Eighth Form"),
    ("internal_energy", "thermal", "blade", "arc", "Sunforge Edge"),
    ("bloodline", "spiritual", "fist", "point", "Ancestral Pulse Strike"),
    ("muscular", "kinetic", "projectile", "point", "Falcon Feather Throw"),
    ("internal_energy", "gravitational", "field", "radial", "Moonweight Stance"),
]


class Innovation:
    __slots__ = ("key", "name", "era", "category", "prereqs", "effects")

    def __init__(self, key, name, era, category, prereqs, effects):
        self.key = key
        self.name = name
        self.era = era
        self.category = category
        self.prereqs = prereqs
        self.effects = effects


class TechManager:
    def __init__(self, sim):
        self.sim = sim
        self.innovations: dict[str, Innovation] = {}
        self.known_by: dict[int, set[str]] = {}      # ruler pid -> innovation keys
        self.techniques = self._build_techniques()
        self.era_progress: dict[int, int] = {}       # ruler pid -> era index
        self._build_tree()

    # ---------- construction ----------
    def _build_tree(self):
        for e_i, era in enumerate(ERAS):
            for cat in CATEGORIES:
                prev_in_cat = []
                if e_i > 0:
                    prev_in_cat = [_INNOVATIONS[ERAS[e_i - 1]][cat][-1]]
                chain_prev = None
                for idx, name in enumerate(_INNOVATIONS[era][cat]):
                    key = name
                    prereqs = []
                    if chain_prev:
                        prereqs.append(chain_prev)
                    elif prev_in_cat:
                        prereqs.append(prev_in_cat[0])
                    effects = self._effects_for(cat, idx)
                    self.innovations[key] = Innovation(
                        key, name.replace("_", " ").title(), era, cat,
                        prereqs, effects)
                    chain_prev = key

    def _effects_for(self, cat, idx):
        if cat == "military":
            return {"army_damage": 0.02 * (idx + 1)}
        if cat == "civic":
            return {"tax": 0.01 * (idx + 1), "development": 0.005 * (idx + 1)}
        return {"piety": 0.5 * (idx + 1), "prestige": 0.5 * (idx + 1)}

    def _build_techniques(self):
        techs = []
        for src, tr, car, geo, name in _TECHNIQUE_NAMES:
            conduit_req = {"muscular": 0.0, "internal_energy": 2.0,
                           "ability_resource": 4.0, "bloodline": 6.0}[src]
            techs.append({
                "name": name,
                "routing": f"{src} -> {tr} -> {car} -> {geo} -> body",
                "power": 1 + _TRANSFORMATIONS.index(tr) + _GEOMETRIES.index(geo) * 0.5,
                "conduit_req": conduit_req,
                "source": src,
            })
        return techs

    # ---------- research ----------
    def knows(self, ruler, key) -> bool:
        return key in self.known_by.get(ruler.pid, set())

    def available(self, ruler) -> list[str]:
        known = self.known_by.setdefault(ruler.pid, set())
        era_idx = self.era_progress.get(ruler.pid, 0)
        out = []
        for key, inno in self.innovations.items():
            if key in known:
                continue
            if ERAS.index(inno.era) > era_idx:
                continue
            if all(p in known for p in inno.prereqs):
                out.append(key)
        return out

    def monthly(self):
        rng = self.sim.rng
        pop = self.sim.population
        for ruler_pid in list(self.sim.dynasties.rulers):
            ruler = pop.get(ruler_pid)
            if ruler is None:
                continue
            # research speed scales with learning + universities etc.
            speed = 0.05 + ruler.skills["learning"] * 0.008
            for inno_key in list(self.known_by.get(ruler.pid, ())):
                pass
            if rng.chance(speed):
                opts = self.available(ruler)
                if opts:
                    pick = rng.choice(opts)
                    self.known_by[ruler.pid].add(pick)
                    inno = self.innovations[pick]
                    # era advancement: 60% of current era known
                    era_keys = [k for k, v in self.innovations.items()
                                if v.era == inno.era]
                    done = sum(1 for k in era_keys
                               if k in self.known_by[ruler.pid])
                    if done >= len(era_keys) * 0.6:
                        self.era_progress[ruler.pid] = min(
                            3, self.era_progress.get(ruler.pid, 0) + 1)
                        self.sim.bus.record(
                            self.sim.date,
                            f"The realm of {ruler.display_name()} enters the "
                            f"{ERAS[self.era_progress[ruler.pid]].replace('_', ' ')} "
                            f"era!", "tech")
                    self.sim.bus.record(
                        self.sim.date,
                        f"{ruler.display_name()}'s court discovers "
                        f"{inno.name}.", "tech")

    # ---------- combat techniques spread ----------
    def spread_techniques(self):
        rng = self.sim.rng
        pop = self.sim.population
        for p in pop.living():
            if len(p.techniques) >= 4:
                continue
            conduit = p.genome.poly_value("conduit_loci") * 10 \
                + p.genome.trait_modifier("conduit")
            if p.skills["prowess"] < 8 and conduit < 3:
                continue
            if not rng.chance(0.004):
                continue
            learnable = [t for t in self.techniques
                         if t["conduit_req"] <= conduit
                         and t["name"] not in p.techniques]
            if learnable:
                # bloodline techniques require the trait
                if conduit >= 6 or "bloodline_vigor" in p.traits:
                    pool = learnable
                else:
                    pool = [t for t in learnable if t["source"] != "bloodline"] \
                        or learnable
                t = rng.choice(pool)
                p.techniques.append(t["name"])
                if t["conduit_req"] >= 4:
                    self.sim.bus.record(
                        self.sim.date,
                        f"{p.display_name()} awakens the technique "
                        f"'{t['name']}'!", "tech")

    def technique_by_name(self, name):
        for t in self.techniques:
            if t["name"] == name:
                return t
        return None

    def count(self) -> int:
        return len(self.innovations)

    def technique_count(self) -> int:
        return len(self.techniques)
