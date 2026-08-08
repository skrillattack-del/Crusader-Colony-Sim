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

This project is in the design / pre-production phase. The document describes the intended architecture, mathematical foundations, and design goals. The document does not specify a current implementation language, build system, or release timeline.

---

## Reference

Full design document: [Crusader_Colony_Sim.pdf](Crusader_Colony_Sim.pdf)
