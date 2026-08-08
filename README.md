# Crusader Colony Sim

> ⚔ Core vision: **CK3-scale people and politics** + **RimWorld-style pawns and bodies** + **live RTS/open-world simulation** + **shonen-grade combat expressiveness** + **browser-native execution.**

Crusader Colony Sim is a multiscale agent simulation where bodies, societies, combat techniques, and history emerge from composable mathematical systems rather than scripted content.

---

## Overview

Pawns in Crusader Colony Sim are richly modelled entities whose every ability, injury, and action flows through a unified graph-based system. Rather than hard-coded stats or scripted superpowers, the game derives emergent behaviour from a small set of composable laws applied consistently across every scale — from a single sword strike measured in milliseconds to dynastic empires spanning centuries.

---

## Pawn Model

Each pawn is defined as a tuple of interconnected graph components:

| Symbol | Component | Governing question |
|--------|-----------|-------------------|
| **B** | Body topology | What are you made of? |
| **K** | Kinematics | How can you move? |
| **M** | Material / physical state | What condition are you in? |
| **C** | Cognition | What do you perceive, know, and decide? |
| **S** | Skills | What have you learned to do? |
| **R** | Relationships | Who matters to you, and how? |
| **I** | Inventory / equipment | What do you possess and wield? |
| **G** | Goals | What are you trying to achieve? |

This abstraction lets a sword technique, telekinetic shove, cursed-energy blast, broken arm, prosthetic leg, cape, shield, giant hammer, or bizarre anime stance all interact with the **same underlying pawn system**.

---

## Foundational Body Graphs

Pawn bodies are modelled as three layered graphs:

### G₁ — Anatomical Graph
- **Nodes:** body parts, organs, tissues, prosthetics  
- **Edges:** attachment, containment, coverage, support  
- **State:** HP, integrity, capacity, impairment  
- **Governs:** what you can do.

### G₂ — Kinematic Graph
- **Nodes:** joints and articulated links  
- **Edges:** degrees of freedom, movement limits, mechanical coupling  
- **State:** mass, inertia, pose, velocity  
- **Governs:** how you move.

### G₃ — Conduit Graph
- **Nodes:** channels, reservoirs, sources, and sinks  
- **Edges:** flow paths and transfer relationships  
- **State:** capacity, throughput, saturation, integrity  
- **Governs:** what impossible things you can do — and what they cost.

The body representation is abstract enough to serve a human, horse, dragon, robot, giant, slime, or cursed puppet using the same machinery.

---

## Combat as State Transformation

Combat is modelled as state transformations over articulated bodies and the surrounding world. An attack is expressed as:

```
A : (Pattacker, Pdefender, W, t) → Δ(Pattacker, Pdefender, W)
```

A technique does not set values directly — it declares a **routing**: a required flow from source to effector across G₃. Solving for actual per-channel throughput is a flow problem on a weighted graph (a Laplacian solve — Kirchhoff's laws for ki).

This produces a **combat grammar** rather than an ability list:

| Ability | Decomposition |
|---------|--------------|
| Sword slash | muscular energy → kinetic → blade → arc → body |
| Fire blast | internal energy → thermal → plasma/fire → cone → area |
| Gravity technique | ability resource → gravitational field → space → radial field → entities |
| Teleport strike | resource → spatial transform → pawn → point-to-point → self |

---

## Simulation Scales

The simulation runs across three nested scales that form a closed loop:

> **combat → injury → relationship → politics → war → combat**  
> A duel can literally change history.

### 🧍 Pawn Scale
Milliseconds to seconds. Bodies, attacks, movement, wounds, perception, projectiles.

### 🏰 Colony Scale
Minutes to months. Jobs, production, construction, logistics, families, social structures, factions.

### 👑 Dynasty / World Scale
Years to centuries. Inheritance, diplomacy, religion, ideology, wars, migration, technological change.

---

## Layer Budget

Each layer's output becomes the next layer's setpoint; only the physical layer sends signals back upward.

| Layer | Rate | State | Output |
|-------|------|-------|--------|
| Strategic (CK3) | ~1 Hz | dynasty, claims, opinions, traits, stress | → operational orders |
| Operational (RTS) | ~10 Hz | armies, supply, sieges, flow fields, influence | → tactical jobs |
| Tactical (RimWorld) | 10–30 Hz | pawn utility/GOAP, needs, jobs, frame-data adjudication | → move invocations + task objectives |
| Physical (bodies) | 120 Hz fixed | articulated dynamics, PD tracking, G₃ flow | → torques, contacts; ↑ veto signal only |

---

## Capability Algebra

The general capability algebra is:

```
Ability = Source × Transformation × Carrier × Geometry × Target × Constraint
```

The shonen/anime inspiration becomes a formal system rather than a collection of special-case superpowers. Without special-casing anything, the model naturally produces effects such as:

- **Gear Second** — deliberately over-drive the cardiovascular trunk (a parameter regime, not a scripted state).
- **Eight Inner Gates** — sequential release of capacity limiters, each raising capacity while multiplying throughput.
- **Gentle Fist** — a damage type targeting G₃ edges instead of G₁ parts; an entire martial school from one damage channel.
- **Bloodline techniques** — high inherited capacity concentrated in a region; dynastic genetics become mechanically real, fusing with CK3-style inheritance.

---

## World Laws

The foundational rules shared by every entity and system:

- **Space and geometry** — position, distance, shape, collision, and spatial relationships  
- **Time and simulation ticks** — ordering, duration, scheduling, and rates of change  
- **Matter, terrain, and structures** — physical composition and the world's persistent form  
- **Resources and energy** — storage, transfer, consumption, and regeneration  
- **Information propagation** — how signals, knowledge, and effects travel  
- **Visibility and uncertainty** — what can be perceived, inferred, hidden, or mistaken  

---

## Development Status

**Playable pure-Python vertical slice implemented** (stdlib only, zero dependencies).

```
backend/
  main.py                CLI entry (gui / headless / 3d / web modes)
  crusader/
    engine.py            calendar clock, deterministic RNG, event bus, scheduler
    worldgen.py          fBm value-noise continents, biomes, rivers, provinces
    genetics.py          diploid allele traits, polygenic loci, inbreeding
    pawn.py              B/K/M/C/S/R/I/G pawn model, personality, opinions
    population.py        1000+ pawn daily utility AI, matchmaking, births, deaths
    dynasty.py           houses, titles, CK3 succession laws, claims, elections
    religion.py          faiths, tenets, doctrines, fervor, conversion
    diplomacy.py         ruler opinions, alliances, casus belli, peace terms
    war.py               armies, terrain battles, full siege phases
    economy.py           14 goods, supply/demand prices, taxes, buildings
    tech.py              144 innovations (4 eras) + 30 combat-grammar techniques
    crafting.py          83-recipe crafting DAG (raw -> component -> equipment)
    dialogue.py          LLM dialogue (OpenAI-compatible, stdlib) + offline fallback
    render2d.py          tkinter map viewer: biome/realm/faith/economy modes
    render3d.py          software 3D renderer: animated low-poly knights
    webserver.py         stdlib HTTP + JSON API, background sim thread
frontend/
  index.html             browser UI: canvas map, province/pawn inspector, chronicle
Dockerfile               production image (serves frontend/ from backend/)
railway.toml             Railway build + healthcheck config
```

### Run it

```bash
python backend/main.py --mode headless --pawns 1000 --years 20   # benchmark + chronicle
python backend/main.py --mode gui --pawns 1000                   # live 2D map (desktop)
python backend/main.py --mode 3d                                 # 3D animated battlefield
python backend/main.py --mode web --port 8080                    # browser UI + JSON API
python backend/main.py --mode headless --years 50 --save world.pkl
python backend/main.py --mode gui --load world.pkl
```

GUI keys: `b/r/f/e` map modes · `space` pause · `+/-` speed · `d` sample dialogue · click a province to inspect.

LLM dialogue is optional: set `CCS_LLM_URL`, `CCS_LLM_KEY`, `CCS_LLM_MODEL`
for any OpenAI-compatible endpoint; otherwise a personality-driven offline
generator (trait templates + Markov chain) is used.

Verified: 1000+ pawns at ~70-85 simulated days/s; succession, partition,
holy wars, sieges, era progression and save/load round-trip all exercised
over 20-year headless runs.

---

## Docker / Railway deployment

The container runs the **web mode** (browser UI + JSON API). The desktop
tkinter modes (`gui`, `3d`) are local-only — servers have no display.

### Local Docker

```bash
docker build -t crusader-colony-sim .
docker run -p 8080:8080 crusader-colony-sim
# open http://localhost:8080
```

Useful env vars: `PORT` (default 8080), `PAWNS` (default 1000),
`MAP_SIZE` (default 192), `DAYS_PER_SEC` (default 15),
plus optional `CCS_LLM_URL` / `CCS_LLM_KEY` / `CCS_LLM_MODEL` for LLM dialogue.

### Railway

The repo includes `railway.toml` + `Dockerfile` — zero config needed:

1. Push this folder to a GitHub repo.
2. Railway dashboard → **New Project → Deploy from GitHub repo**.
3. Railway auto-detects the Dockerfile, builds, and injects `$PORT`.
4. Healthcheck runs against `/api/state` (configured in `railway.toml`).

Or with the CLI: `railway up`.

Note: the filesystem is ephemeral on Railway — `world.pkl` saves do not
survive redeploys unless you attach a Volume and save there.

### API

| Endpoint | Purpose |
|---|---|
| `GET /` | single-page map UI |
| `GET /api/state` | world summary JSON (healthcheck) |
| `GET /api/map?mode=biome\|realm\|faith\|economy` | palette + base64 tiles |
| `GET /api/overlays` | armies, sieges, capitals |
| `GET /api/chronicle?since=N` | event feed (incremental) |
| `GET /api/province_xy?x=X&y=Y` | province detail |
| `GET /api/pawns?province=N` | pawns living in a province |
| `GET /api/pawn?id=N` | full pawn sheet (genes, skills, needs, titles) |
| `GET /api/pawn_say?id=N` | one in-character dialogue line |
| `GET /api/dialogue` | sample NPC conversation |
| `POST /api/control` | `{"action":"pause"\|"resume"\|"speed","value":N}` |

---

## Reference

Full design document: [Crusader_Colony_Sim.pdf](Crusader_Colony_Sim.pdf)
