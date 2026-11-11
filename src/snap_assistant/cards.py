from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from .models import Card


def _key(name: str) -> str:
    """Lookup key that ignores case, spacing and punctuation ("Ant-Man" == "ant man")."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


class CardPool:
    """A lookup of known cards, loaded from JSON."""

    def __init__(self, cards: list[Card], source: str = "bundled sample"):
        self._by_key = {_key(c.name): c for c in cards}
        # Also accept the game's internal id (e.g. "MisterNegative") for lookups.
        self._aliases = {_key(c.def_id): c for c in cards if c.def_id}
        self.source = source

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CardPool":
        if path is None:
            text = resources.files("snap_assistant.data").joinpath("cards.json").read_text()
        else:
            text = Path(path).read_text()
        return cls([Card.from_dict(d) for d in json.loads(text)],
                   source="bundled sample" if path is None else str(path))

    @classmethod
    def from_db(cls, path: str | Path, include_unreleased: bool = False) -> "CardPool":
        """Released, non-token cards from a synced database."""
        from .pipeline.store import Store

        store = Store(path)
        try:
            rows = store.entities("card", released_only=not include_unreleased, include_tokens=False)
        finally:
            store.close()
        return cls(
            [Card(name=r["name"], cost=r["cost"] or 0, power=r["power"] or 0, ability=r["text"] or "",
                  tags=frozenset(json.loads(r["tags"])), def_id=r["def_id"]) for r in rows],
            source=f"database {path}",
        )

    def get(self, name: str) -> Card:
        key = _key(name)
        card = self._by_key.get(key) or self._aliases.get(key)
        if card is None:
            raise KeyError(f"Unknown card: {name!r}")
        return card

    def __contains__(self, name: str) -> bool:
        key = _key(name)
        return key in self._by_key or key in self._aliases

    def __iter__(self):
        return iter(self._by_key.values())

    def __len__(self) -> int:
        return len(self._by_key)

    def with_tag(self, tag: str) -> list[Card]:
        return [c for c in self if tag.lower() in c.tags]
