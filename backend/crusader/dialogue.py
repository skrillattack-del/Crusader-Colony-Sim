"""LLM-powered NPC dialogue with a robust offline fallback.

Backend resolution order:
  1. OpenAI-compatible HTTP endpoint configured via environment:
       CCS_LLM_URL    e.g. https://api.openai.com/v1/chat/completions
       CCS_LLM_KEY    bearer token
       CCS_LLM_MODEL  model name
     (pure stdlib urllib - no dependencies)
  2. Offline personality-driven generator (trait templates + Markov
     chain trained on a built-in medieval corpus).

The simulation NEVER blocks on the network: requests run with a short
timeout and fall back silently to offline lines.
"""
from __future__ import annotations

import json
import os
import urllib.request

_CORPUS = """the crown weighs heavy on the brow that wears it
a sword is only as honest as the hand that wields it
winter comes for the proud and the humble alike
my house has held these lands since my grandfather's grandfather
the gods see all that men try to hide
gold opens gates that steel cannot
a kinsman's blood is worth more than a king's favor
the harvest was poor this year and the tithe collector grows fat
i would sooner trust a wolf than a smiling envoy
faith is the only armor that never rusts
the old ways die hard in these hills
my father died holding that bridge and so shall i if it comes to it
a woman's counsel is worth two knights in the field
the siege has made rats of us all
marry your daughter to my son and let the borders bleed no more
treason is just loyalty that lost the war
the ancestors watch us from the standing stones
i have buried three sons to this cursed war
plow the field first and philosophize after
the sea gives and the sea takes
"""

_TEMPLATES = {
    "brave":      ["{name} fears nothing — not siege, not storm, not {other}.",
                   "Draw your steel, {other}. Let us settle this as our fathers did."],
    "craven":     ["Surely there is no need for violence, {other}... is there?",
                   "{name} would very much like to be somewhere else."],
    "greedy":     ["Everything has a price, {other}. Even loyalty. Especially loyalty.",
                   "That is a fine purse you carry. How heavy is it, I wonder?"],
    "generous":   ["Take what you need, friend. Grain shared is famine halved.",
                   "My door is open to any who knock in peace."],
    "zealous":    ["The gods demand better of us, {other}. Kneel and repent.",
                   "I pray each dawn that {other} finds the true path."],
    "cynical":    ["Prayers did not fill last winter's granary, and they will not fill this one.",
                   "Gods? I see only men with crowns, {other}."],
    "ambitious":  ["This province is too small for the plans I carry, {other}.",
                   "One day they will write songs about {name}. One day soon."],
    "content":    ["A full belly, a warm hearth — what more could a soul want?",
                   "{name} hums an old harvest song and says little."],
    "wrathful":   ["Speak that again, {other}, and lose your tongue.",
                   "{name}'s hand rests on a dagger hilt, knuckles white."],
    "calm":       ["Anger is a poor counselor. Sit. Drink. Talk.",
                   "Storms pass, {other}. We need only outlast them."],
    "lustful":    ["You have fine eyes, {other}. The evening is long."],
    "chaste":     ["Keep your distance and your dignity, {other}."],
    "deceitful":  ["Of course I speak only truth, {other}. Would I lie to you?",
                   "{name} smiles, and remembers exactly where the exits are."],
    "honest":     ["I will not dress it up: these are hard times, {other}."],
    "sadistic":   ["The prisoners sing so beautifully when properly encouraged."],
    "compassionate": ["No one starves at my table while I have bread, {other}."],
    "diligent":   ["The fields will not plow themselves. Nor the ledgers balance."],
    "lazy":       ["Tomorrow is also a day, {other}. Why rush today?"],
}

_MOOD = {
    "war":   "The war has taken much from us all.",
    "peace": "These quiet years are a gift we did not earn.",
    "siege": "The walls still hold, but the larders do not.",
    "feast": "Eat! Drink! Tomorrow we may be bones.",
}


class DialogueEngine:
    def __init__(self, sim):
        self.sim = sim
        self.url = os.environ.get("CCS_LLM_URL")
        self.key = os.environ.get("CCS_LLM_KEY")
        self.model = os.environ.get("CCS_LLM_MODEL", "")
        # tiny Markov chain over the corpus
        words = _CORPUS.split()
        self.chain: dict[str, list[str]] = {}
        for a, b in zip(words, words[1:]):
            self.chain.setdefault(a, []).append(b)
        self._markov_starts = [w for w in words if w and w[0].isupper()]

    @property
    def online(self) -> bool:
        return bool(self.url and self.key)

    # ---------- public API ----------
    def speak(self, pawn, other=None, context: str | None = None) -> str:
        """Generate a line of dialogue for a pawn. Never raises."""
        if self.online:
            try:
                line = self._llm_line(pawn, other, context)
                if line:
                    return line
            except Exception:
                pass
        return self._offline_line(pawn, other, context)

    def converse(self, a, b, turns: int = 3, context: str | None = None) -> list[str]:
        out = []
        speaker, listener = a, b
        for _ in range(turns):
            line = self.speak(speaker, listener, context)
            for _try in range(4):  # avoid identical consecutive lines
                if not out or not line.endswith(out[-1].split(": ", 1)[-1]):
                    break
                line = self.speak(speaker, listener, context)
            out.append(f"{speaker.name}: {line}")
            speaker, listener = listener, speaker
        return out

    # ---------- offline ----------
    def _offline_line(self, pawn, other, context) -> str:
        rng = self.sim.rng
        other_name = other.name if other else "stranger"
        trait = rng.choice(pawn.personality) if pawn.personality else None
        lines = _TEMPLATES.get(trait or "content", _TEMPLATES["content"])
        line = rng.choice(lines).format(name=pawn.name, other=other_name)
        if context in _MOOD and rng.chance(0.4):
            line += " " + _MOOD[context]
        elif rng.chance(0.6):
            line += " " + self._markov(rng.randint(8, 16))
        return line

    def _markov(self, n: int) -> str:
        rng = self.sim.rng
        word = rng.choice(self._markov_starts or list(self.chain))
        out = [word]
        for _ in range(n - 1):
            nxt = self.chain.get(word)
            if not nxt:
                break
            word = rng.choice(nxt)
            out.append(word)
        text = " ".join(out)
        return text[0].upper() + text[1:] + "."

    # ---------- online ----------
    def _prompt(self, pawn, other, context) -> str:
        faith = self.sim.religion.faiths.get(pawn.faith)
        parts = [
            f"You are {pawn.display_name()}, a {pawn.job} in a medieval world, "
            f"year {self.sim.date.year}.",
            f"Personality: {', '.join(pawn.personality)}. "
            f"Traits: {', '.join(pawn.traits) or 'none'}.",
            f"Faith: {faith.name if faith else 'none'}. Ambition: {pawn.ambition}.",
        ]
        if other:
            parts.append(f"You are speaking to {other.display_name()} "
                         f"(opinion: {pawn.opinion_of(other)}).")
        if context:
            parts.append(f"Situation: {context}.")
        parts.append("Say one short in-character line (max 25 words). "
                     "No narration, no quotes.")
        return " ".join(parts)

    def _llm_line(self, pawn, other, context) -> str | None:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": self._prompt(pawn, other, context)}],
            "max_tokens": 60,
            "temperature": 0.9,
        }).encode()
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        text = data["choices"][0]["message"]["content"].strip()
        return text.strip('"').strip() or None
