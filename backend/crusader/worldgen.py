"""Procedural continent generation: fBm value-noise heightmap, temperature,
moisture, biomes, rivers, and province carving. Pure stdlib.

Produces a WorldMap with ~hundreds of provinces over a huge tile grid.
"""
from __future__ import annotations

import math
from collections import deque

BIOME_OCEAN = "ocean"
BIOME_DEEP_OCEAN = "deep_ocean"
BIOME_BEACH = "beach"
BIOME_PLAINS = "plains"
BIOME_FOREST = "forest"
BIOME_TAIGA = "taiga"
BIOME_DESERT = "desert"
BIOME_STEPPE = "steppe"
BIOME_JUNGLE = "jungle"
BIOME_HILLS = "hills"
BIOME_MOUNTAIN = "mountain"
BIOME_SNOW = "snow"
BIOME_MARSH = "marsh"
BIOME_RIVER = "river"  # overlay flag, not a biome

SEA_LEVEL = 0.42
MOUNTAIN_LEVEL = 0.78
HILLS_LEVEL = 0.62

BIOME_COLORS = {
    BIOME_DEEP_OCEAN: "#1b3a5c", BIOME_OCEAN: "#2b5d8a", BIOME_BEACH: "#d8c690",
    BIOME_PLAINS: "#7fae4e", BIOME_FOREST: "#3d7a3a", BIOME_TAIGA: "#2f5e4a",
    BIOME_DESERT: "#e0c069", BIOME_STEPPE: "#b0a94f", BIOME_JUNGLE: "#2e7d4f",
    BIOME_HILLS: "#8a8a52", BIOME_MOUNTAIN: "#8d8579", BIOME_SNOW: "#e8eef0",
    BIOME_MARSH: "#5e7a5a", BIOME_RIVER: "#3d7fc1",
}

# movement cost per biome (pathfinding)
MOVE_COST = {
    BIOME_OCEAN: 99, BIOME_DEEP_OCEAN: 99, BIOME_MOUNTAIN: 6.0,
    BIOME_HILLS: 2.2, BIOME_FOREST: 2.0, BIOME_TAIGA: 2.0, BIOME_JUNGLE: 2.5,
    BIOME_MARSH: 3.0, BIOME_SNOW: 2.5, BIOME_DESERT: 1.8, BIOME_STEPPE: 1.3,
    BIOME_PLAINS: 1.0, BIOME_BEACH: 1.2,
}


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class ValueNoise:
    """Deterministic 2D value noise on a permutation lattice."""

    def __init__(self, rng, period: int = 256):
        vals = list(range(period))
        rng.shuffle(vals)
        self.perm = vals * 2
        self.rng_vals = [rng.random() for _ in range(period * 2)]

    def _lat(self, xi: int, yi: int) -> float:
        h = self.perm[(self.perm[xi % 256] + yi) % 256]
        return self.rng_vals[h]

    def at(self, x: float, y: float) -> float:
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        u, v = _smoothstep(xf), _smoothstep(yf)
        a = self._lat(xi, yi)
        b = self._lat(xi + 1, yi)
        c = self._lat(xi, yi + 1)
        d = self._lat(xi + 1, yi + 1)
        return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v

    def fbm(self, x: float, y: float, octaves: int = 5, gain: float = 0.5,
            lacunarity: float = 2.0) -> float:
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self.at(x * freq, y * freq)
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm


class Province:
    __slots__ = ("pid", "name", "tiles", "cx", "cy", "biome", "neighbors",
                 "holding", "owner_title", "controller", "fort_level",
                 "is_coastal", "river", "development")

    def __init__(self, pid, name):
        self.pid = pid
        self.name = name
        self.tiles: list[tuple[int, int]] = []
        self.cx = 0.0
        self.cy = 0.0
        self.biome = BIOME_PLAINS
        self.neighbors: set[int] = set()
        self.holding = "castle"     # castle | city | temple | none
        self.owner_title = None     # title id
        self.controller = None      # realm controlling it in war
        self.fort_level = 1
        self.is_coastal = False
        self.river = False
        self.development = 5

    def finalize(self):
        if self.tiles:
            self.cx = sum(t[0] for t in self.tiles) / len(self.tiles)
            self.cy = sum(t[1] for t in self.tiles) / len(self.tiles)


class WorldMap:
    """Tile grid + provinces + A* pathfinding."""

    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height
        self.height = [0.0] * (width * height)
        self.biome = [BIOME_OCEAN] * (width * height)
        self.river = [False] * (width * height)
        self.province_id = [-1] * (width * height)
        self.provinces: list[Province] = []

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def land(self, x: int, y: int) -> bool:
        return self.height[self.idx(x, y)] >= SEA_LEVEL

    # ---- pathfinding over provinces ----
    def province_path(self, start: int, goal: int) -> list[int] | None:
        """A* between province ids using euclidean heuristic."""
        if start == goal:
            return [start]
        import heapq
        provs = self.provinces
        gx, gy = provs[goal].cx, provs[goal].cy
        open_heap = [(0.0, start)]
        g = {start: 0.0}
        came = {start: -1}
        closed = set()
        while open_heap:
            _, cur = heapq.heappop(open_heap)
            if cur == goal:
                path = [cur]
                while came[cur] != -1:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            if cur in closed:
                continue
            closed.add(cur)
            for nb in provs[cur].neighbors:
                if nb in closed:
                    continue
                d = math.dist((provs[cur].cx, provs[cur].cy),
                              (provs[nb].cx, provs[nb].cy))
                ng = g[cur] + d * (1.0 + 0.15 * provs[nb].fort_level * 0)
                if ng < g.get(nb, 1e18):
                    g[nb] = ng
                    came[nb] = cur
                    h = math.dist((provs[nb].cx, provs[nb].cy), (gx, gy))
                    heapq.heappush(open_heap, (ng + h, nb))
        return None


def generate_world(rng, width: int = 192, height: int = 192,
                   province_chunk: int = 12, n_continents: int = 3) -> WorldMap:
    """Full procedural pipeline -> WorldMap."""
    from .names import place_name
    wm = WorldMap(width, height)
    noise = ValueNoise(rng)
    noise2 = ValueNoise(rng)

    # continent masks: a few radial blobs to force oceans between landmasses
    centers = [(rng.uniform(0.15, 0.85) * width, rng.uniform(0.2, 0.8) * height)
               for _ in range(n_continents)]
    max_r = min(width, height) * 0.42

    scale = 3.2 / min(width, height)
    for y in range(height):
        for x in range(width):
            i = y * width + x
            n = noise.fbm(x * scale, y * scale, octaves=5)
            # distance falloff to nearest continent center
            d = min(math.hypot(x - cx, y - cy) for cx, cy in centers) / max_r
            fall = max(0.0, 1.0 - d * d)
            wm.height[i] = n * 0.65 + fall * 0.55 - 0.18

    # temperature: latitude + altitude; moisture: second noise + ocean proximity
    for y in range(height):
        lat = abs(y / height - 0.5) * 2.0  # 0 equator .. 1 pole
        for x in range(width):
            i = y * width + x
            h = wm.height[i]
            if h < SEA_LEVEL - 0.18:
                wm.biome[i] = BIOME_DEEP_OCEAN
                continue
            if h < SEA_LEVEL:
                wm.biome[i] = BIOME_OCEAN
                continue
            temp = (1.0 - lat) * 0.8 + noise2.at(x * 0.05, y * 0.05) * 0.2 \
                - max(0.0, h - SEA_LEVEL) * 0.9
            moist = noise.fbm(x * scale * 2.3 + 50, y * scale * 2.3 + 50, 4)
            if h >= MOUNTAIN_LEVEL:
                wm.biome[i] = BIOME_SNOW if temp < 0.35 else BIOME_MOUNTAIN
            elif h >= HILLS_LEVEL:
                wm.biome[i] = BIOME_HILLS
            elif temp < 0.18:
                wm.biome[i] = BIOME_SNOW
            elif temp < 0.32:
                wm.biome[i] = BIOME_TAIGA
            elif temp > 0.72 and moist < 0.35:
                wm.biome[i] = BIOME_DESERT
            elif moist > 0.66 and temp > 0.6:
                wm.biome[i] = BIOME_JUNGLE
            elif moist > 0.58:
                wm.biome[i] = BIOME_FOREST
            elif moist < 0.28:
                wm.biome[i] = BIOME_STEPPE
            else:
                wm.biome[i] = BIOME_PLAINS

    # beaches + coastal flags
    # beaches: any non-mountain land tile adjacent to sea becomes beach
    for y in range(height):
        for x in range(width):
            if not wm.land(x, y):
                continue
            i = y * width + x
            if wm.biome[i] in (BIOME_MOUNTAIN, BIOME_SNOW):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if wm.in_bounds(nx, ny) and not wm.land(nx, ny):
                    wm.biome[i] = BIOME_BEACH
                    break

    # rivers: flow downhill from high land to sea
    n_rivers = max(8, width * height // 2500)
    for _ in range(n_rivers):
        x = rng.randrange(width)
        y = rng.randrange(height)
        if wm.height[wm.idx(x, y)] < HILLS_LEVEL:
            continue
        for _step in range(width * 2):
            i = wm.idx(x, y)
            if not wm.land(x, y):
                break
            wm.river[i] = True
            best = None
            best_h = wm.height[i]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if wm.in_bounds(nx, ny):
                    h = wm.height[wm.idx(nx, ny)]
                    if h < best_h:
                        best_h, best = h, (nx, ny)
            if best is None:
                break
            x, y = best

    # ---- carve provinces: flood-fill chunks over land ----
    prov_grid_w = math.ceil(width / province_chunk)
    prov_grid_h = math.ceil(height / province_chunk)
    provs: list[Province] = []
    taken_names: set[str] = set()
    for pgy in range(prov_grid_h):
        for pgx in range(prov_grid_w):
            name = place_name(rng)
            while name in taken_names:
                name = place_name(rng)
            taken_names.add(name)
            p = Province(len(provs), name)
            tiles = []
            for ty in range(pgy * province_chunk, min((pgy + 1) * province_chunk, height)):
                for tx in range(pgx * province_chunk, min((pgx + 1) * province_chunk, width)):
                    i = ty * width + tx
                    if wm.land(tx, ty):
                        tiles.append((tx, ty))
                        wm.province_id[i] = p.pid
            if not tiles:
                continue
            p.tiles = tiles
            p.finalize()
            # dominant biome
            from collections import Counter
            p.biome = Counter(wm.biome[ty * width + tx] for tx, ty in tiles).most_common(1)[0][0]
            p.river = any(wm.river[ty * width + tx] for tx, ty in tiles)
            p.is_coastal = any(not wm.land(tx + dx, ty + dy)
                               for tx, ty in tiles
                               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                               if wm.in_bounds(tx + dx, ty + dy))
            p.holding = rng.weighted([("castle", 0.45), ("city", 0.25),
                                      ("temple", 0.15), ("none", 0.15)])
            p.fort_level = 1 + (1 if p.holding == "castle" else 0) \
                + (1 if p.biome in (BIOME_HILLS, BIOME_MOUNTAIN) else 0)
            provs.append(p)
    wm.provinces = provs

    # province adjacency from tile adjacency
    for p in provs:
        for tx, ty in p.tiles:
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = tx + dx, ty + dy
                if wm.in_bounds(nx, ny):
                    j = wm.province_id[ny * width + nx]
                    if j != -1 and j != p.pid:
                        p.neighbors.add(j)
                        provs[j].neighbors.add(p.pid)

    # merge isolated single-province islands: link to nearest by distance
    for p in provs:
        if not p.neighbors:
            best, bd = None, 1e18
            for q in provs:
                if q is p:
                    continue
                d = math.dist((p.cx, p.cy), (q.cx, q.cy))
                if d < bd:
                    best, bd = q, d
            if best:
                p.neighbors.add(best.pid)
                best.neighbors.add(p.pid)
    return wm
