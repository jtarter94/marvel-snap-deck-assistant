from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

DECK_SIZE = 12


@dataclass(frozen=True)
class Card:
    name: str
    cost: int
    power: int
    ability: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)
    def_id: str = ""
    release_date: str | None = None   # ISO date, when known (synced data only)

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        return cls(
            name=d["name"],
            cost=int(d["cost"]),
            power=int(d["power"]),
            ability=d.get("ability", ""),
            tags=frozenset(t.lower() for t in d.get("tags", [])),
            def_id=d.get("def_id", ""),
            release_date=d.get("release_date"),
        )


@dataclass
class Deck:
    name: str
    cards: list[Card]

    def validate(self) -> list[str]:
        """Return a list of rule violations (empty if the deck is legal)."""
        errors = []
        if len(self.cards) != DECK_SIZE:
            errors.append(f"Deck has {len(self.cards)} cards; needs exactly {DECK_SIZE}.")
        dupes = [n for n, c in Counter(c.name for c in self.cards).items() if c > 1]
        if dupes:
            errors.append(f"Duplicate cards: {', '.join(sorted(dupes))}.")
        return errors

    @property
    def is_valid(self) -> bool:
        return not self.validate()
