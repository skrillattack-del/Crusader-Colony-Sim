"""Tkinter 2D map viewer: biome / realm / faith / economy map modes,
animated armies & sieges, chronicle sidebar, click-to-inspect provinces.
"""
from __future__ import annotations

import tkinter as tk

from .worldgen import BIOME_COLORS

FAITH_PALETTE = ["#c0392b", "#2980b9", "#27ae60", "#f39c12", "#8e44ad",
                 "#16a085", "#d35400"]
REALM_PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6",
                 "#1abc9c", "#e67e22", "#95a5a6", "#fd79a8", "#00cec9",
                 "#6c5ce7", "#d63031"]


class MapViewer:
    def __init__(self, sim, scale: int = 4, days_per_frame: int = 3):
        self.sim = sim
        self.scale = scale
        self.days_per_frame = days_per_frame
        self.paused = False
        self.mode = "biome"
        self.root = tk.Tk()
        self.root.title("Crusader Colony Sim")
        w = sim.world
        self.canvas = tk.Canvas(self.root, width=w.w * scale,
                                height=w.h * scale, bg="#101820",
                                highlightthickness=0)
        self.canvas.pack(side=tk.LEFT)
        side = tk.Frame(self.root, width=340, bg="#1b2632")
        side.pack(side=tk.RIGHT, fill=tk.Y)
        self.info = tk.Label(side, text="", justify=tk.LEFT, anchor="nw",
                             bg="#1b2632", fg="#dfe6e9",
                             font=("Consolas", 10), wraplength=320)
        self.info.pack(fill=tk.X, padx=8, pady=8)
        self.chron = tk.Text(side, width=42, bg="#101820", fg="#b2bec3",
                             font=("Consolas", 9), state=tk.DISABLED)
        self.chron.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.photo = tk.PhotoImage(width=w.w, height=w.h)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW,
                                 tags=("map",))
        self.canvas.scale("map", 0, 0, scale, scale)
        self.canvas.bind("<Button-1>", self._click)
        self.root.bind("<space>", lambda e: self._toggle())
        self.root.bind("b", lambda e: self._set_mode("biome"))
        self.root.bind("r", lambda e: self._set_mode("realm"))
        self.root.bind("f", lambda e: self._set_mode("faith"))
        self.root.bind("e", lambda e: self._set_mode("economy"))
        self.root.bind("plus", lambda e: self._speed(1))
        self.root.bind("minus", lambda e: self._speed(-1))
        self.root.bind("d", lambda e: self._dialogue_sample())
        self._render_tiles()
        self._chron_len = 0

    # ---------- controls ----------
    def _toggle(self):
        self.paused = not self.paused

    def _speed(self, d):
        self.days_per_frame = max(1, min(30, self.days_per_frame + d))

    def _set_mode(self, mode):
        self.mode = mode
        self._render_tiles()

    def _dialogue_sample(self):
        rng = self.sim.rng
        pop = list(self.sim.population.living())
        if len(pop) < 2:
            return
        a, b = rng.sample(pop, 2)
        war = any(w.active for w in self.sim.diplomacy.wars)
        lines = self.sim.dialogue.converse(a, b, turns=4,
                                           context="war" if war else "peace")
        self.sim.bus.chronicle.append("--- conversation ---")
        self.sim.bus.chronicle.extend(lines)
        self._update_chronicle(force=True)

    # ---------- map painting ----------
    def _tile_color(self, i, x, y):
        w = self.sim.world
        mode = self.mode
        if mode == "biome":
            base = BIOME_COLORS[w.biome[i]]
            if w.river[i] and w.biome[i] not in ("ocean", "deep_ocean"):
                return BIOME_COLORS["river"]
            return base
        pid = w.province_id[i]
        if pid == -1:
            return BIOME_COLORS[w.biome[i]]
        if mode == "realm":
            tid = w.provinces[pid].owner_title
            return REALM_PALETTE[tid % len(REALM_PALETTE)] if tid is not None \
                else "#3d3d3d"
        if mode == "faith":
            from collections import Counter
            members = self.sim.population.by_province.get(pid, ())
            faiths = [self.sim.population.pawns[m].faith
                      for m in members if m in self.sim.population.pawns]
            if not faiths:
                return "#3d3d3d"
            f = Counter(faiths).most_common(1)[0][0]
            return FAITH_PALETTE[(f or 0) % len(FAITH_PALETTE)]
        if mode == "economy":
            stock = self.sim.economy.stock.get(pid)
            if not stock:
                return "#3d3d3d"
            val = sum(stock[g] * self.sim.economy.prices.get(g, 4.0)
                      for g in stock)
            heat = min(255, int(val * 8))
            return f"#{heat:02x}{min(255, heat + 60):02x}30"
        return "#3d3d3d"

    def _render_tiles(self):
        w = self.sim.world
        for y in range(w.h):
            row = []
            for x in range(w.w):
                row.append(self._tile_color(w.idx(x, y), x, y))
            self.photo.put("{" + " ".join(row) + "}", to=(0, y))

    # ---------- overlays ----------
    def _draw_overlays(self):
        self.canvas.delete("overlay")
        s = self.scale
        w = self.sim.world
        pop = self.sim.population
        # capitals
        dyn = self.sim.dynasties
        for title in dyn.titles.values():
            if title.tier >= 3 and title.provinces:
                p = w.provinces[title.provinces[0]]
                x, y = p.cx * s, p.cy * s
                self.canvas.create_text(x, y, text="👑" if title.tier == 3 else "★",
                                        font=("Arial", 8), tags="overlay")
        # armies
        for army in self.sim.war_engine.armies:
            p = w.provinces[army.province]
            x, y = p.cx * s, p.cy * s
            ruler = pop.get(army.ruler)
            color = "#ff6b6b" if ruler and any(
                wr.active and army.ruler in wr.attackers
                for wr in self.sim.diplomacy.wars) else "#74b9ff"
            self.canvas.create_polygon(
                x, y - 5, x + 5, y + 4, x - 5, y + 4,
                fill=color, outline="#000", tags="overlay")
            self.canvas.create_text(x, y - 10, text=str(army.size),
                                    font=("Arial", 6), fill="#fff",
                                    tags="overlay")
        # sieges
        for siege in self.sim.war_engine.sieges:
            p = siege.province
            x, y = p.cx * s, p.cy * s
            pct = siege.progress / max(1, siege.max_progress)
            self.canvas.create_oval(x - 7, y - 7, x + 7, y + 7,
                                    outline="#e17055", width=2,
                                    tags="overlay")
            self.canvas.create_arc(x - 7, y - 7, x + 7, y + 7,
                                   start=90, extent=-360 * pct,
                                   outline="#fdcb6e", width=2, style=tk.ARC,
                                   tags="overlay")

    # ---------- side panel ----------
    def _update_chronicle(self, force=False):
        ch = self.sim.bus.chronicle
        if len(ch) == self._chron_len and not force:
            return
        self._chron_len = len(ch)
        self.chron.config(state=tk.NORMAL)
        self.chron.delete("1.0", tk.END)
        self.chron.insert(tk.END, "\n".join(ch[-300:]))
        self.chron.see(tk.END)
        self.chron.config(state=tk.DISABLED)

    def _update_info(self):
        s = self.sim
        summ = s.summary()
        keys = ("b)biome r)realm f)faith e)economy  space)pause  "
                "+/-)speed  d)dialogue")
        text = (f"{summ['date']}   ({self.days_per_frame} days/frame)\n"
                f"Pawns: {summ['living_pawns']}  "
                f"(+{summ['births']} born / -{summ['deaths']} dead)\n"
                f"Kingdoms: {summ['kingdoms']}   Wars: {summ['active_wars']} "
                f"active / {summ['total_wars']} total\n"
                f"Faiths: {', '.join(f'{k}:{v}' for k, v in summ['faiths'].items())}\n"
                f"Innovations known: {summ['innovations_known_all_realms']}"
                f"/{summ['innovation_total']}   "
                f"Techniques: {summ['techniques_total']}\n"
                f"Crafting recipes: {summ['recipes_total']}\n"
                f"LLM dialogue: {'online' if s.dialogue.online else 'offline'}\n\n"
                f"{keys}")
        self.info.config(text=text)

    def _click(self, event):
        w = self.sim.world
        x, y = int(event.x / self.scale), int(event.y / self.scale)
        if not w.in_bounds(x, y):
            return
        pid = w.province_id[y * w.w + x]
        if pid == -1:
            return
        p = w.provinces[pid]
        ruler = self.sim.dynasties.ruler_of_province(pid)
        stock = self.sim.economy.stock.get(pid, {})
        top_goods = sorted(stock.items(), key=lambda kv: -kv[1])[:3]
        members = len(self.sim.population.by_province.get(pid, ()))
        info = (f"{p.name} — {p.biome}\n"
                f"Holding: {p.holding} (fort {p.fort_level}), "
                f"dev {p.development:.0f}\n"
                f"Pop: {members}  Ruler: "
                f"{ruler.display_name() if ruler else 'none'}\n"
                f"Goods: {', '.join(f'{g} {v:.0f}' for g, v in top_goods)}\n"
                f"Buildings: {', '.join(self.sim.economy.buildings.get(pid, [])) or '—'}")
        self.sim.bus.record(self.sim.date, info, "inspect")

    # ---------- main loop ----------
    def run(self):
        def frame():
            if not self.paused:
                for _ in range(self.days_per_frame):
                    self.sim.tick()
                self._draw_overlays()
                self._update_info()
                self._update_chronicle()
                if self.sim.date.is_new_year() and self.mode != "biome":
                    self._render_tiles()
            self.root.after(33, frame)
        frame()
        self.root.mainloop()
