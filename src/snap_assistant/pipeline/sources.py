"""Card/location data sources.

Each source turns its site's raw JSON into a list of ``Record``s keyed by the
game's internal id (``CardDefId``), which both sites expose. Parsing is kept
separate from fetching so it can be tested against saved fixtures.

Neither endpoint is an official API; both are free and unauthenticated. We
identify ourselves honestly and only fetch a handful of times a day.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Callable

from .. import __version__
from .text import clean_name, clean_text, to_int

# Plausible real dates only: drops 0, year-1 and 2038-style placeholder values.
_MIN_TS, _MAX_TS = 1_500_000_000, 2_000_000_000


def _date(ts) -> str | None:
    """Unix timestamp -> ISO date, or None for missing/placeholder values."""
    t = to_int(ts)
    if t is None or not _MIN_TS < t < _MAX_TS:
        return None
    return datetime.fromtimestamp(t, timezone.utc).date().isoformat()


def _earliest(dates) -> str | None:
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        out = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


USER_AGENT = f"snap-assistant/{__version__} (personal deck-building tool; a few requests/day)"

CARD = "card"
LOCATION = "location"


@dataclass
class Record:
    kind: str
    def_id: str
    name: str
    text: str
    cost: int | None = None
    power: int | None = None
    released: bool | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Source:
    name: str
    urls: dict[str, str]                       # kind -> url
    parsers: dict[str, Callable[[object], list[Record]]]

    def parse(self, raw_by_kind: dict[str, object]) -> dict[str, list[Record]]:
        return {kind: self.parsers[kind](raw) for kind, raw in raw_by_kind.items()}


def http_get_json(url: str, timeout: float = 30, retries: int = 3) -> object:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                              "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            return json.loads(body)
        except Exception as e:  # network errors, bad JSON, HTTP errors
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


# --- marvelsnap.pro --------------------------------------------------------

def _pro_cards(raw) -> list[Record]:
    out = []
    for v in raw.values():
        series = v.get("CardSeriesDefId") or ""
        series = "" if series == "None" else series
        out.append(Record(
            kind=CARD,
            def_id=v["CardDefId"],
            name=clean_name(v.get("name")),
            text=clean_text(v.get("description")),
            cost=to_int(v.get("cost")),
            power=to_int(v.get("power")),
            # No explicit flag: a card people have played has been released.
            released=(to_int(v.get("use_count")) or 0) > 0,
            extra={
                # Character, or a game-mode Skill/Augment/Trinket (not deck-buildable)
                "card_type": v.get("type") or "Character",
                "is_token": v.get("is_Token") == "1",
                "patch": v.get("wasChangedIn") or v.get("wasAddedIn") or None,
                "series": series.replace("Series", "Series ") if series else None,
                # Game-mode versions (Champions, "Hulk - Avengers", ...) have no
                # collection series and can't go in a normal deck.
                "collectible": bool(series),
                # When the card entered its *current* pool (Season Pass/Series).
                # Later than the true release for cards that changed Series.
                "pool_date": _earliest(_date(x.get("StartDate"))
                                       for x in _json_list(v.get("SeriesStartDates"))
                                       if isinstance(x, dict)),
                # Linked cards, in both directions (Vampire Killmonger <-> Vampiric
                # Spear). reconcile works out which one creates the other.
                "related": [c for c in _json_list(v.get("connected_cards")) if isinstance(c, str)],
            },
        ))
    return out


def _pro_locations(raw) -> list[Record]:
    return [
        Record(
            kind=LOCATION,
            def_id=v["CardDefId"],
            name=clean_name(v.get("name")),
            text=clean_text(v.get("description")),
            released=v.get("released") == "1",
            extra={"patch": v.get("wasChangedIn") or v.get("wasAddedIn") or None,
                   "rarity": v.get("rarity") or None,
                   "pool_date": _earliest(_date(x.get("date")) for x in v.get("dates") or []
                                          if isinstance(x, dict) and x.get("type") == "Base")},
        )
        for v in raw.values()
    ]


# --- marvelsnapzone.com ----------------------------------------------------

def _zone_items(raw) -> list[dict]:
    return raw["success"]["cards"]


def _zone_cards(raw) -> list[Record]:
    return [
        Record(
            kind=CARD,
            def_id=c["carddefid"],
            name=clean_name(c.get("name")),
            text=clean_text(c.get("ability")),
            cost=to_int(c.get("cost")),
            power=to_int(c.get("power")),
            released=c.get("status") == "released",
            extra={"art": c.get("art") or None,
                   # Earliest dated art variant: the card's base art ships on release day.
                   "art_date": _earliest(_date(x.get("ReleaseDate"))
                                         for x in c.get("variants") or [] if isinstance(x, dict))},
        )
        for c in _zone_items(raw)
        if c.get("type") == "Character" and c.get("carddefid")
    ]


def _zone_locations(raw) -> list[Record]:
    return [
        Record(
            kind=LOCATION,
            def_id=c["carddefid"],
            name=clean_name(c.get("name")),
            text=clean_text(c.get("ability")),
            released=c.get("status") == "released",
        )
        for c in _zone_items(raw)
        if c.get("carddefid")
    ]


MARVELSNAP_PRO = Source(
    name="marvelsnap.pro",
    urls={
        CARD: "https://marvelsnap.pro/snap/do.php?cmd=getcards",
        LOCATION: "https://marvelsnap.pro/snap/do.php?cmd=getlocations",
    },
    parsers={CARD: _pro_cards, LOCATION: _pro_locations},
)

MARVELSNAPZONE = Source(
    name="marvelsnapzone.com",
    urls={
        CARD: "https://marvelsnapzone.com/getinfo/?searchtype=cards&searchcardstype=true",
        LOCATION: "https://marvelsnapzone.com/getinfo/?searchtype=locations&searchcardstype=true",
    },
    parsers={CARD: _zone_cards, LOCATION: _zone_locations},
)

# Order matters only as a tie-breaker when a brand-new entity has a conflict
# and there is no previous value to hold: the first source wins provisionally.
DEFAULT_SOURCES = [MARVELSNAP_PRO, MARVELSNAPZONE]
