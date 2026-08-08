"""Production web server: stdlib-only HTTP + JSON API around the live sim.

The simulation ticks on a background thread; the browser polls compact JSON
(map as palette + base64 tile indices) and renders on a <canvas>.

Endpoints:
    GET  /                     single-page frontend
    GET  /api/state            world summary
    GET  /api/map?mode=biome|realm|faith|economy
    GET  /api/overlays         armies, sieges, capitals
    GET  /api/chronicle?since=N
    GET  /api/dialogue         sample NPC conversation
    GET  /api/province?id=N    province detail
    POST /api/control          {"action": "pause"|"resume"|"speed", "value": N}
"""
from __future__ import annotations

import base64
import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .worldgen import BIOME_COLORS

FAITH_PALETTE = ["#c0392b", "#2980b9", "#27ae60", "#f39c12", "#8e44ad",
                 "#16a085", "#d35400"]
REALM_PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6",
                 "#1abc9c", "#e67e22", "#95a5a6", "#fd79a8", "#00cec9",
                 "#6c5ce7", "#d63031"]
WEB_DIR = Path(__file__).parent / "web"


class SimRunner:
    """Background ticking thread with a lock guarding all sim access."""

    def __init__(self, sim, days_per_sec: float = 15.0):
        self.sim = sim
        self.lock = threading.Lock()
        self.paused = False
        self.days_per_sec = days_per_sec
        self._stop = False

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        acc = 0.0
        last = time.perf_counter()
        while not self._stop:
            now = time.perf_counter()
            acc += (now - last) * self.days_per_sec
            last = now
            n = int(acc)
            acc -= n
            if self.paused or self.days_per_sec <= 0:
                time.sleep(0.05)
                continue
            if n > 0:
                with self.lock:
                    for _ in range(min(n, 40)):
                        self.sim.tick()
            else:
                time.sleep(0.01)


# ---------------- map coloring (province-cached) ----------------

def province_colors(sim, mode: str) -> list[str]:
    w = sim.world
    n = len(w.provinces)
    if mode == "realm":
        return [REALM_PALETTE[p.owner_title % len(REALM_PALETTE)]
                if p.owner_title is not None else "#3d3d3d"
                for p in w.provinces]
    if mode == "faith":
        out = []
        pop = sim.population
        for p in w.provinces:
            members = pop.by_province.get(p.pid, ())
            faiths = Counter(pop.pawns[m].faith for m in members
                             if m in pop.pawns)
            if faiths:
                f = faiths.most_common(1)[0][0] or 0
                out.append(FAITH_PALETTE[f % len(FAITH_PALETTE)])
            else:
                out.append("#3d3d3d")
        return out
    if mode == "economy":
        eco = sim.economy
        out = []
        for p in w.provinces:
            stock = eco.stock.get(p.pid)
            if not stock:
                out.append("#3d3d3d")
                continue
            val = sum(stock[g] * eco.prices.get(g, 4.0) for g in stock)
            heat = min(255, int(val * 8))
            out.append(f"#{heat:02x}{min(255, heat + 60):02x}30")
        return out
    return ["#000000"] * n  # biome mode is per-tile, unused here


def map_payload(sim, mode: str) -> dict:
    w = sim.world
    prov_col = province_colors(sim, mode) if mode != "biome" else None
    palette: list[str] = []
    pindex: dict[str, int] = {}
    data = bytearray(w.w * w.h)
    river_c = BIOME_COLORS["river"]
    for y in range(w.h):
        for x in range(w.w):
            i = y * w.w + x
            if mode == "biome":
                c = BIOME_COLORS[w.biome[i]]
                if w.river[i] and w.biome[i] not in ("ocean", "deep_ocean"):
                    c = river_c
            else:
                pid = w.province_id[i]
                c = BIOME_COLORS[w.biome[i]] if pid == -1 else prov_col[pid]
            j = pindex.get(c)
            if j is None:
                j = len(palette)
                palette.append(c)
                pindex[c] = j
            data[i] = j
    return {"w": w.w, "h": w.h, "palette": palette,
            "tiles": base64.b64encode(bytes(data)).decode("ascii")}


def overlays_payload(sim) -> dict:
    pop = sim.population
    armies = []
    for a in sim.war_engine.armies:
        p = sim.world.provinces[a.province]
        side = "attacker" if any(
            w.active and a.ruler in w.attackers
            for w in sim.diplomacy.wars) else "defender"
        armies.append({"x": p.cx, "y": p.cy, "size": a.size, "side": side})
    sieges = []
    for s in sim.war_engine.sieges:
        sieges.append({"x": s.province.cx, "y": s.province.cy,
                       "pct": round(s.progress / max(1, s.max_progress), 2),
                       "name": s.province.name})
    capitals = []
    for t in sim.dynasties.titles.values():
        if t.tier >= 3 and t.provinces:
            p = sim.world.provinces[t.provinces[0]]
            holder = pop.get(t.holder)
            capitals.append({"x": p.cx, "y": p.cy,
                             "name": t.name,
                             "ruler": holder.display_name() if holder else "?"})
    return {"armies": armies, "sieges": sieges, "capitals": capitals}


def province_payload(sim, pid: int) -> dict | None:
    w = sim.world
    if pid < 0 or pid >= len(w.provinces):
        return None
    p = w.provinces[pid]
    ruler = sim.dynasties.ruler_of_province(pid)
    stock = sim.economy.stock.get(pid, {})
    top = sorted(stock.items(), key=lambda kv: -kv[1])[:4]
    return {
        "name": p.name, "biome": p.biome, "holding": p.holding,
        "fort": p.fort_level, "development": round(p.development, 1),
        "population": len(sim.population.by_province.get(pid, ())),
        "ruler": ruler.display_name() if ruler else None,
        "goods": {g: round(v, 1) for g, v in top},
        "buildings": sim.economy.buildings.get(pid, []),
    }


# ---------------- HTTP handler ----------------

def make_handler(runner: SimRunner):
    sim = runner.sim

    class Handler(BaseHTTPRequestHandler):
        server_version = "CrusaderColonySim/0.1"

        def log_message(self, *args):  # keep Railway logs clean
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            try:
                if url.path == "/" or url.path == "/index.html":
                    html = (WEB_DIR / "index.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                elif url.path == "/api/state":
                    with runner.lock:
                        s = sim.summary()
                        s["paused"] = runner.paused
                        s["days_per_sec"] = runner.days_per_sec
                    self._json(s)
                elif url.path == "/api/map":
                    mode = qs.get("mode", ["biome"])[0]
                    with runner.lock:
                        self._json(map_payload(sim, mode))
                elif url.path == "/api/overlays":
                    with runner.lock:
                        self._json(overlays_payload(sim))
                elif url.path == "/api/chronicle":
                    since = int(qs.get("since", ["0"])[0])
                    with runner.lock:
                        ch = sim.bus.chronicle
                        self._json({"entries": ch[since:], "total": len(ch)})
                elif url.path == "/api/dialogue":
                    with runner.lock:
                        pop = list(sim.population.living())
                        if len(pop) >= 2:
                            a, b = sim.rng.sample(pop, 2)
                            war = any(w.active for w in sim.diplomacy.wars)
                            lines = sim.dialogue.converse(
                                a, b, turns=4,
                                context="war" if war else "peace")
                        else:
                            lines = []
                    self._json({"lines": lines,
                                "llm": sim.dialogue.online})
                elif url.path == "/api/province":
                    pid = int(qs.get("id", ["-1"])[0])
                    with runner.lock:
                        self._json(province_payload(sim, pid))
                elif url.path == "/api/province_xy":
                    x = int(float(qs.get("x", ["-1"])[0]))
                    y = int(float(qs.get("y", ["-1"])[0]))
                    with runner.lock:
                        if sim.world.in_bounds(x, y):
                            pid = sim.world.province_id[y * sim.world.w + x]
                            self._json(province_payload(sim, pid))
                        else:
                            self._json(None)
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # never kill the server on a bad request
                self._json({"error": str(e)}, 500)

        def do_POST(self):
            if self.path.startswith("/api/control"):
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    body = {}
                action = body.get("action")
                if action == "pause":
                    runner.paused = True
                elif action == "resume":
                    runner.paused = False
                elif action == "speed":
                    runner.days_per_sec = max(0.0, min(120.0,
                                               float(body.get("value", 15))))
                self._json({"paused": runner.paused,
                            "days_per_sec": runner.days_per_sec})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(sim, host: str = "0.0.0.0", port: int = 8080,
          days_per_sec: float = 15.0):
    runner = SimRunner(sim, days_per_sec)
    runner.start()
    server = ThreadingHTTPServer((host, port), make_handler(runner))
    print(f"Crusader Colony Sim web server on http://{host}:{port} "
          f"({len(sim.population.pawns)} pawns, "
          f"{len(sim.world.provinces)} provinces)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
