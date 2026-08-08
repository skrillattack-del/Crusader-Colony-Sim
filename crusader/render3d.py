"""Pure-Python software 3D renderer: perspective projection, z-sorted
shaded polygons, orbiting camera, articulated low-poly knights with
walk / attack / idle animation. No dependencies beyond tkinter.
"""
from __future__ import annotations

import math
import tkinter as tk


# ---------- tiny vector/matrix helpers ----------
def _rot_y(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)


def _rot_z(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def _rot_x(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c)


def box_faces(cx, cy, cz, sx, sy, sz):
    """8-vertex box -> 6 quad faces (each 4 verts)."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
         (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
         (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
         (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
    return [(v[0], v[1], v[2], v[3]), (v[5], v[4], v[7], v[6]),
            (v[4], v[0], v[3], v[7]), (v[1], v[5], v[6], v[2]),
            (v[3], v[2], v[6], v[7]), (v[4], v[5], v[1], v[0])]


def limb(ox, oy, oz, length, thick, angle_z, angle_x=0.0):
    """A limb: box rotated about its shoulder/hip joint."""
    verts = box_faces(0, -length / 2, 0, thick, length, thick)
    out = []
    for face in verts:
        nf = []
        for v in face:
            v = _rot_x(v, angle_x)
            v = _rot_z(v, angle_z)
            nf.append((v[0] + ox, v[1] + oy, v[2] + oz))
        out.append(nf)
    return out


class Knight:
    """Articulated low-poly humanoid."""

    def __init__(self, x, z, color, armor="#7f8c8d", facing=0.0):
        self.x, self.z = x, z
        self.color = color
        self.armor = armor
        self.facing = facing
        self.phase = 0.0
        self.mode = "idle"        # idle | walk | attack
        self.attack_t = 0.0

    def faces(self):
        t = self.phase
        faces = []
        walk = self.mode == "walk"
        swing = math.sin(t * 6) * (0.55 if walk else 0.05)
        bob = abs(math.sin(t * 6)) * 0.04 if walk else 0.0
        hip_y = 0.95 + bob
        # legs
        faces += limb(self.x - 0.12, hip_y, self.z, 0.85, 0.16, swing)
        faces += limb(self.x + 0.12, hip_y, self.z, 0.85, 0.16, -swing)
        # torso
        faces += box_faces(self.x, hip_y + 0.45, self.z, 0.5, 0.7, 0.3)
        # head + helm
        faces += box_faces(self.x, hip_y + 1.05, self.z, 0.28, 0.28, 0.28)
        faces += box_faces(self.x, hip_y + 1.2, self.z, 0.32, 0.1, 0.32)
        # arms
        if self.mode == "attack":
            a = -2.2 + min(self.attack_t * 8, 1.0) * 2.6   # overhead chop
            faces += limb(self.x - 0.33, hip_y + 0.75, self.z, 0.7, 0.13, a)
            faces += limb(self.x + 0.33, hip_y + 0.75, self.z, 0.7, 0.13,
                          -0.3)
            # sword follows right arm
            tip_x = self.x - 0.33 - math.sin(-a) * 0.7
            tip_y = hip_y + 0.75 - math.cos(a) * 0.7
            faces += box_faces(tip_x - math.sin(-a) * 0.5,
                               tip_y - math.cos(a) * 0.5, self.z,
                               0.06, 1.0, 0.06)
        else:
            faces += limb(self.x - 0.33, hip_y + 0.75, self.z, 0.7, 0.13,
                          -swing * 0.8)
            faces += limb(self.x + 0.33, hip_y + 0.75, self.z, 0.7, 0.13,
                          swing * 0.8)
            # sword held low
            faces += box_faces(self.x + 0.4, hip_y + 0.15, self.z,
                               0.06, 0.9, 0.06)
        # rotate whole body around y
        out = []
        for face in faces:
            nf = []
            for vx, vy, vz in face:
                rx, ry, rz = _rot_y((vx - self.x, vy, vz - self.z), self.facing)
                nf.append((rx + self.x, ry, rz + self.z))
            out.append(nf)
        return out


class Scene3D:
    def __init__(self, sim=None, width=960, height=620):
        self.sim = sim
        self.root = tk.Tk()
        self.root.title("Crusader Colony Sim — 3D battlefield")
        self.canvas = tk.Canvas(self.root, width=width, height=height,
                                bg="#0d1520", highlightthickness=0)
        self.canvas.pack()
        self.w, self.h = width, height
        self.cam_yaw = 0.6
        self.cam_dist = 14.0
        self.cam_height = 6.0
        self.t = 0.0
        self.knights = [
            Knight(-2.5, 0, "#c0392b", facing=math.pi / 2),
            Knight(-1.2, 1.5, "#c0392b", facing=math.pi / 2),
            Knight(-3.8, 1.2, "#c0392b", facing=math.pi / 2),
            Knight(2.5, 0, "#2980b9", facing=-math.pi / 2),
            Knight(1.2, 1.5, "#2980b9", facing=-math.pi / 2),
            Knight(3.8, 1.2, "#2980b9", facing=-math.pi / 2),
        ]
        self.knights[0].mode = "attack"
        self.knights[3].mode = "attack"
        for k in (self.knights[1], self.knights[2],
                  self.knights[4], self.knights[5]):
            k.mode = "walk"
        self.hud = self.canvas.create_text(
            10, 10, anchor=tk.NW, fill="#dfe6e9",
            font=("Consolas", 10), text="")
        self.root.bind("<Left>", lambda e: self._orbit(-0.15))
        self.root.bind("<Right>", lambda e: self._orbit(0.15))
        self.root.bind("<Up>", lambda e: self._zoom(-1))
        self.root.bind("<Down>", lambda e: self._zoom(1))

    def _orbit(self, d):
        self.cam_yaw += d

    def _zoom(self, d):
        self.cam_dist = max(6, min(30, self.cam_dist + d))

    def _project(self, v):
        # world -> camera (orbit around origin)
        x, y, z = v[0], v[1] - self.cam_height, v[2]
        x, y, z = _rot_y((x, y, z), -self.cam_yaw)
        z += self.cam_dist
        if z < 0.5:
            z = 0.5
        f = 520 / z
        return (self.w / 2 + x * f, self.h * 0.62 - y * f, z)

    def _shade(self, face):
        # lambert vs fixed sun
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = face[0], face[1], face[2]
        ux, uy, uz = x2 - x1, y2 - y1, z2 - z1
        vx, vy, vz = x3 - x1, y3 - y1, z3 - z1
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        lx, ly, lz = 0.5, 0.75, 0.42
        d = max(0.0, (nx * lx + ny * ly + nz * lz) / ln)
        return 0.25 + 0.75 * d

    def _draw_face(self, face, base_color):
        pts = [self._project(v) for v in face]
        depth = sum(p[2] for p in pts) / len(pts)
        shade = self._shade(face)
        r = int(int(base_color[1:3], 16) * shade)
        g = int(int(base_color[3:5], 16) * shade)
        b = int(int(base_color[5:7], 16) * shade)
        color = f"#{r:02x}{g:02x}{b:02x}"
        poly = [(p[0], p[1]) for p in pts]
        return depth, color, poly

    def render(self):
        self.canvas.delete("scene")
        draw_list = []
        # ground grid
        for gx in range(-8, 9, 2):
            for gz in range(-8, 9, 2):
                face = [(gx, 0, gz), (gx + 2, 0, gz),
                        (gx + 2, 0, gz + 2), (gx, 0, gz + 2)]
                col = "#2d5a34" if (gx + gz) % 4 == 0 else "#275030"
                draw_list.append(self._draw_face(face, col))
        # castle backdrop
        for bx, bz, sx, sy, sz in [(-8, -10, 2, 6, 2), (-3, -11, 6, 3.5, 2),
                                   (2, -10, 2, 7, 2)]:
            for face in box_faces(bx, sy / 2, bz, sx, sy, sz):
                draw_list.append(self._draw_face(face, "#6d6560"))
        # crenellations
        for i in range(3):
            for face in box_faces(-8 + i * 0.8 - 0.8, 6.3, -10, 0.5, 0.6, 0.5):
                draw_list.append(self._draw_face(face, "#6d6560"))
        # knights
        for k in self.knights:
            k.phase = self.t
            if k.mode == "attack":
                k.attack_t = (k.attack_t + 0.03) % 1.6
            if k.mode == "walk":
                k.x += math.sin(k.facing) * 0.02
                k.z += math.cos(k.facing) * 0.02
                if abs(k.x) > 6:
                    k.facing += math.pi
            for face in k.faces():
                draw_list.append(self._draw_face(face, k.color))
        draw_list.sort(key=lambda d: -d[0])
        for _d, color, poly in draw_list:
            self.canvas.create_polygon(poly, fill=color, outline="",
                                       tags="scene")
        # HUD from sim
        hud = "←/→ orbit   ↑/↓ zoom   software renderer, pure Python"
        if self.sim is not None:
            s = self.sim.summary()
            hud = (f"{s['date']}  pawns {s['living_pawns']}  "
                   f"wars {s['active_wars']}  —  {hud}")
        self.canvas.itemconfig(self.hud, text=hud)
        self.canvas.tag_raise(self.hud)

    def run(self):
        def frame():
            self.t += 0.05
            self.render()
            self.root.after(33, frame)
        frame()
        self.root.mainloop()
