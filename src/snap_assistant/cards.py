from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .models import Card


class CardPool:
    """A lookup of known cards, loaded from JSON."""

    def __init__(self, cards: list[Card]):
        self._by_key = {c.name.lower(): c for c in cards}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CardPool":
        if path is None:
            text = resources.files("snap_assistant.data").joinpath("cards.json").read_text()
        else:
            text = Path(path).read_text()
        return cls([Card.from_dict(d) for d in json.loads(text)])

    def get(self, name: str) -> Card:
        try:
            return self._by_key[name.strip().lower()]
        except KeyError:
            raise KeyError(f"Unknown card: {name!r}") from None

    def __contains__(self, name: str) -> bool:
        return name.strip().lower() in self._by_key

    def __iter__(self):
        return iter(self._by_key.values())

    def __len__(self) -> int:
        return len(self._by_key)

    def with_tag(self, tag: str) -> list[Card]:
        return [c for c in self if tag.lower() in c.tags]
