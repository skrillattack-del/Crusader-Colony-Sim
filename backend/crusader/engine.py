"""Engine core: calendar clock, deterministic RNG, event bus, scheduler.

Time model: 1 tick = 1 day. 12 months x 30 days = 360-day year.
"""
from __future__ import annotations

import random
from collections import defaultdict

DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR

MONTH_NAMES = [
    "Januar", "Februar", "Mars", "Aprel", "Mai", "Juni",
    "Juli", "August", "Septem", "Octob", "Novem", "Decem",
]


class GameDate:
    """Absolute day counter with calendar conversion."""

    __slots__ = ("day",)

    def __init__(self, day: int = 0):
        self.day = day

    @property
    def year(self) -> int:
        return 867 + self.day // DAYS_PER_YEAR  # CK3-style start date

    @property
    def month(self) -> int:
        return (self.day % DAYS_PER_YEAR) // DAYS_PER_MONTH

    @property
    def day_of_month(self) -> int:
        return self.day % DAYS_PER_MONTH + 1

    def is_new_month(self) -> bool:
        return self.day % DAYS_PER_MONTH == 0

    def is_new_year(self) -> bool:
        return self.day % DAYS_PER_YEAR == 0

    def age_years(self, birth_day: int) -> int:
        return (self.day - birth_day) // DAYS_PER_YEAR

    def __str__(self) -> str:
        return f"{self.day_of_month} {MONTH_NAMES[self.month]}, {self.year}"


class RNG(random.Random):
    """Deterministic simulation RNG with convenience helpers."""

    def chance(self, p: float) -> bool:
        return self.random() < p

    def weighted(self, items_weights):
        """items_weights: iterable of (item, weight)."""
        items, weights = zip(*items_weights)
        return self.choices(items, weights=weights, k=1)[0]

    def spread(self, base: float, pct: float = 0.2) -> float:
        """base +/- pct jitter."""
        return base * (1.0 + self.uniform(-pct, pct))


class EventBus:
    """Simple pub/sub for decoupled systems + chronicle log."""

    def __init__(self, chronicle_size: int = 4000):
        self._subs = defaultdict(list)
        self.chronicle: list[str] = []

    def subscribe(self, event: str, fn):
        self._subs[event].append(fn)

    def emit(self, event: str, **data):
        for fn in self._subs.get(event, ()):
            fn(**data)

    def record(self, date: GameDate, text: str, category: str = "world"):
        entry = f"[{date}] {text}"
        self.chronicle.append(entry)
        if len(self.chronicle) > 4000:
            del self.chronicle[:1000]
        self.emit("chronicle", text=entry, category=category)


class Scheduler:
    """Day-based scheduler: schedule(callable, delay_days) or every(interval)."""

    def __init__(self):
        self._tasks: list[list] = []  # [next_day, interval_or_None, fn]

    def schedule(self, day: int, delay: int, fn):
        self._tasks.append([day + delay, None, fn])

    def every(self, day: int, interval: int, fn):
        self._tasks.append([day + interval, interval, fn])

    def run_due(self, day: int):
        due = [t for t in self._tasks if t[0] <= day]
        self._tasks = [t for t in self._tasks if t[0] > day]
        for t in due:
            t[2]()
            if t[1] is not None:
                t[0] = day + t[1]
                self._tasks.append(t)
