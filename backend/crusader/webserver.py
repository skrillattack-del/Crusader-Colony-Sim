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
import os
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


def _find_frontend_dir() -> Path:
    """frontend/ lives beside backend/; allow env override for deploys."""
    env = os.environ.get("CCS_FRONTEND_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "frontend",   # repo_root/frontend
                 here.parents[1] / "frontend",   # backend/frontend
                 here.parent / "web"):           # legacy crusader/web
        if (cand / "index.html").exists():
            return cand
    return here.parents[2] / "frontend"


WEB_DIR = _find_frontend_dir()


class SimRunner:
    """Background ticking thread with a lock guarding all sim access."""

    def __init__(self, sim, days_per_sec: float = 15.0):
        self.sim = sim
        self.lock = threading.Lock()
        self.paused = False
        self.days_per_sec = days_per_sec
        self._stop = False
        from .battle_sim import BattleManager
        self.battles = BattleManager(sim)
        sim.war_engine.live_manager = self.battles

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        acc = 0.0
        last = time.perf_counter()
        while not self._stop:
            now = time.perf_counter()
            real_dt = now - last
            acc += real_dt * self.days_per_sec
            last = now
            n = int(acc)
            acc -= n
            with self.lock:
                # tactical layer always runs in real time (~10-30 Hz)
                self.battles.tick(min(real_dt, 0.25))
                if not self.paused and self.days_per_sec > 0 and n > 0:
                    for _ in range(min(n, 40)):
                        self.sim.tick()
            if n <= 0:
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


def overlays_payload(sim, battles=None) -> dict:
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
    fights = []
    if battles is not None:
        for b in battles.battles.values():
            fights.append({"id": b.bid, "x": b.province.cx, "y": b.province.cy,
                           "name": b.province.name, "phase": b.phase})
    return {"armies": armies, "sieges": sieges, "capitals": capitals,
            "fights": fights}


def province_payload(sim, pid: int) -> dict | None:
    w = sim.world
    if pid < 0 or pid >= len(w.provinces):
        return None
    p = w.provinces[pid]
    ruler = sim.dynasties.ruler_of_province(pid)
    stock = sim.economy.stock.get(pid, {})
    top = sorted(stock.items(), key=lambda kv: -kv[1])[:4]
    return {
        "pid": pid,
        "name": p.name, "biome": p.biome, "holding": p.holding,
        "fort": p.fort_level, "development": round(p.development, 1),
        "population": len(sim.population.by_province.get(pid, ())),
        "ruler": ruler.display_name() if ruler else None,
        "goods": {g: round(v, 1) for g, v in top},
        "buildings": sim.economy.buildings.get(pid, []),
    }


# ---------------- pawn (RimWorld-scale) payloads ----------------

def pawn_brief(sim, p) -> dict:
    return {
        "pid": p.pid,
        "name": p.display_name(),
        "female": p.female,
        "age": round(p.age(sim.date.day), 1),
        "job": p.job,
        "traits": p.traits[:3],
        "personality": p.personality,
        "is_ruler": p.is_ruler,
        "health": round(p.health, 1),
    }


def pawn_detail(sim, p) -> dict:
    pop = sim.population
    faith = sim.religion.faiths.get(p.faith)
    spouse = pop.get(p.spouse) if p.spouse is not None else None
    kids = [pop.get(c) for c in p.children[:6]]
    parents = []
    for par in (p.mother, p.father):
        q = pop.get(par) or pop.dead_by_pid.get(par)
        if q:
            parents.append(q.display_name())
    top_labor = sorted(p.labor.items(), key=lambda kv: -kv[1])[:4]
    return {
        **pawn_brief(sim, p),
        "house": p.house,
        "faith": faith.name if faith else None,
        "ambition": p.ambition,
        "skills": {k: round(v, 1) for k, v in p.skills.items()},
        "labor": {k: round(v, 1) for k, v in top_labor},
        "needs": {k: round(v, 2) for k, v in p.needs.items()},
        "stress": round(p.stress, 2),
        "traits_all": p.traits,
        "carriers": p.genome.carriers(),
        "techniques": p.techniques,
        "gold": round(p.gold, 1),
        "piety": round(p.piety, 1),
        "prestige": round(p.prestige, 1),
        "kills": p.kills,
        "spouse": spouse.display_name() if spouse else None,
        "children": [k.display_name() for k in kids if k],
        "parents": parents,
        "titles": [sim.dynasties.titles[t].full_name
                   for t in p.titles if t in sim.dynasties.titles],
        "claims": [sim.dynasties.titles[t].full_name
                   for t in p.claims if t in sim.dynasties.titles],
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
                        self._json(overlays_payload(sim, runner.battles))
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
                elif url.path == "/api/battles":
                    with runner.lock:
                        self._json({"battles": runner.battles.active()})
                elif url.path == "/api/battle":
                    bid = int(qs.get("id", ["-1"])[0])
                    with runner.lock:
                        b = runner.battles.get(bid)
                        self._json(b.snapshot() if b else None)
                elif url.path == "/api/pawns":
                    pid = int(qs.get("province", ["-1"])[0])
                    with runner.lock:
                        pop = sim.population
                        members = [pop.pawns[m] for m in
                                   pop.by_province.get(pid, ())
                                   if m in pop.pawns]
                        members.sort(key=lambda p: -p.prestige
                                     - p.skill_total())
                        self._json({"province": pid, "count": len(members),
                                    "pawns": [pawn_brief(sim, p)
                                              for p in members[:16]]})
                elif url.path == "/api/pawn":
                    pid = int(qs.get("id", ["-1"])[0])
                    with runner.lock:
                        p = sim.population.get(pid)
                        self._json(pawn_detail(sim, p) if p else None)
                elif url.path == "/api/pawn_say":
                    pid = int(qs.get("id", ["-1"])[0])
                    with runner.lock:
                        p = sim.population.get(pid)
                        if p is None:
                            self._json({"line": None})
                        else:
                            war = any(w.active for w in sim.diplomacy.wars)
                            line = sim.dialogue.speak(
                                p, context="war" if war else "peace")
                            self._json({"line": f"{p.name}: {line}",
                                        "llm": sim.dialogue.online})
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
