"""Procedural naming: people, houses, realms, provinces, faiths."""
from __future__ import annotations

MALE_GIVEN = [
    "Aldric", "Baldwin", "Cedric", "Dunstan", "Edmund", "Fulk", "Godfrey",
    "Harald", "Ivo", "Leofric", "Milo", "Osric", "Roland", "Sigurd", "Theobald",
    "Ulric", "Wystan", "Anselm", "Berengar", "Conrad", "Drogo", "Enguerrand",
    "Gawain", "Hubert", "Jocelin", "Lambert", "Raimund", "Tancred", "Waleran",
    "Aubry", "Gerhard", "Reynold", "Ottokar", "Vratislav", "Casimir", "Boleslaw",
]

FEMALE_GIVEN = [
    "Adela", "Beatrice", "Cecily", "Eleanor", "Gisela", "Hildegard", "Isolde",
    "Joan", "Matilda", "Petronilla", "Rosalind", "Sibylla", "Yolande", "Agnes",
    "Blanche", "Constance", "Elfreda", "Godiva", "Heloise", "Margery", "Odile",
    "Philippa", "Richeza", "Theodora", "Wulfhild", "Aelith", "Brunhild",
    "Katarina", "Ludmila", "Rogneda", "Swanhild", "Miroslava", "Euphemia",
]

HOUSE_PREFIX = ["Ashen", "Black", "Bright", "Cold", "Dun", "Elder", "Fair",
                "Grim", "High", "Iron", "Kings", "Long", "Marsh", "Oak",
                "Red", "Stone", "Storm", "Thorn", "White", "Wolf"]
HOUSE_SUFFIX = ["borne", "fell", "ford", "gard", "hart", "helm", "hold",
                "mark", "mont", "ridge", "shaw", "stead", "vale", "ward",
                "wood", "worth"]

PLACE_PREFIX = ["Ald", "Bran", "Car", "Dor", "Esk", "Fen", "Gar", "Hol",
                "Ing", "Kel", "Lor", "Mor", "Nor", "Ost", "Rav", "Sel",
                "Tor", "Ul", "Wen", "Yar"]
PLACE_SUFFIX = ["burg", "by", "chester", "dale", "firth", "grad", "ham",
                "holm", "keep", "mouth", "stead", "thorpe", "wick", "haven"]

FAITH_ROOT = ["Sol", "Lun", "Ter", "Aur", "Ves", "Ign", "Aeq", "Nym",
              "Ord", "Vey", "Zal", "Mor"]
FAITH_STYLE = ["anism", "ism", "ar Faith", "ite Path", "ic Creed", "an Way"]

REALM_ADJ = ["Holy", "Free", "Grand", "Northern", "Southern", "Eastern",
             "Western", "United", "Ancient", "New"]


def given_name(rng, female: bool) -> str:
    return rng.choice(FEMALE_GIVEN if female else MALE_GIVEN)


def house_name(rng) -> str:
    return rng.choice(HOUSE_PREFIX) + rng.choice(HOUSE_SUFFIX)


def place_name(rng) -> str:
    return rng.choice(PLACE_PREFIX) + rng.choice(PLACE_SUFFIX)


def faith_name(rng) -> str:
    return rng.choice(FAITH_ROOT) + rng.choice(FAITH_STYLE)


def realm_name(rng, seat: str) -> str:
    if rng.chance(0.5):
        return f"{rng.choice(REALM_ADJ)} {seat}"
    return seat
