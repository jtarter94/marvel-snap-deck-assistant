"""Cross-validate sources and decide what the accepted data should be.

Rules, per entity (card or location) and per compared field:

* Every source that has a non-empty value agrees  -> accept it.
* Sources disagree                                 -> **conflict**: keep the
  previously accepted value (a brand-new entity takes the first source's
  value provisionally) until they agree again or an override settles it.
* Only one source has a value that differs from the accepted one:
    - if the field was ever confirmed by two sources, the change is **held**
      (status ``pending``) until a second source confirms it. This covers a
      source being down, or one site updating hours before the other.
    - otherwise (the other source never had this field, e.g. it leaves some
      ability text blank) the single source is accepted.
* An entity seen in only one source is ``provisional``.
* ``released`` is sticky and OR-ed: a card is released once either source
  says so (marvelsnap.pro lags on release day; the Zone lags on stats).
* Names are only compared for released, non-token cards. Generated cards
  (Evolved X, spells, effects) have an in-game name on marvelsnap.pro and a
  descriptive label on the Zone; there the first source's name is used.
* Overrides always win and are reported, including when the sources have
  caught up and the override can be removed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .sources import CARD, Record
from .tags import derive_tags

FIELDS = {CARD: ("name", "cost", "power", "text"), "location": ("name", "text")}

CONFIRMED = "confirmed"
PROVISIONAL = "provisional"
PENDING = "pending"
CONFLICT = "conflict"


@dataclass
class Prior:
    """What the database currently holds for an entity."""
    values: dict
    released: bool
    confirmed_fields: set[str]
    sources: set[str]
    extra: dict


@dataclass
class Change:
    field: str
    old: object
    new: object
    how: str          # new | confirmed | single-source | override
    sources: list[str]


@dataclass
class Decision:
    kind: str
    def_id: str
    values: dict
    released: bool
    tags: list[str]
    status: str
    confirmed_fields: set[str]
    sources: set[str]
    extra: dict
    is_new: bool = False
    changes: list[Change] = field(default_factory=list)
    conflicts: dict[str, dict[str, object]] = field(default_factory=dict)
    held: dict[str, dict[str, object]] = field(default_factory=dict)
    overridden: list[str] = field(default_factory=list)
    stale_overrides: list[str] = field(default_factory=list)
    missing_from: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.values.get("name") or self.def_id

    @property
    def touched(self) -> bool:
        return bool(self.is_new or self.changes)


def _present(v) -> bool:
    return v is not None and v != ""


def reconcile(
    records: dict[str, list[Record]],
    priors: dict[tuple[str, str], Prior],
    source_order: list[str],
    down_sources: set[str] = frozenset(),
    overrides: dict | None = None,
) -> list[Decision]:
    """``records`` maps each *up* source name to everything it returned."""
    overrides = overrides or {}
    by_key: dict[tuple[str, str], dict[str, Record]] = {}
    for src in source_order:
        for rec in records.get(src, []):
            by_key.setdefault((rec.kind, rec.def_id), {})[src] = rec

    up_sources = [s for s in source_order if s in records]
    decisions = []
    for key in sorted(set(by_key) | set(priors)):
        kind, def_id = key
        providers = by_key.get(key, {})
        prior = priors.get(key)
        ov = overrides.get(kind, {}).get(def_id, {})
        decisions.append(_decide(kind, def_id, providers, prior, ov, up_sources, down_sources))
    return decisions


def _decide(kind, def_id, providers, prior, ov, up_sources, down_sources) -> Decision:
    prior_vals = prior.values if prior else {}
    confirmed = set(prior.confirmed_fields) if prior else set()
    d = Decision(
        kind=kind, def_id=def_id, values={}, released=False, tags=[], status=PROVISIONAL,
        confirmed_fields=confirmed, sources=set(), extra={}, is_new=prior is None,
    )

    if not providers:
        # Not in any source that answered this run: keep what we have.
        d.values = dict(prior_vals)
        d.released = prior.released
        d.extra = dict(prior.extra)
        d.sources = set(prior.sources)
        d.missing_from = list(up_sources)
        d.tags = _tags(kind, d.values, ov)
        d.status = CONFIRMED if len(d.sources) >= 2 else PROVISIONAL
        return d

    order = list(providers)  # already in source priority order
    playable = (
        any(r.released for r in providers.values()) or (prior is not None and prior.released)
    ) and not any(r.extra.get("is_token") for r in providers.values())
    for f in FIELDS[kind]:
        vals = {s: getattr(providers[s], f) for s in order if _present(getattr(providers[s], f))}
        if f == "name" and not playable and len(vals) > 1:
            vals = {order[0]: vals[order[0]]} if order[0] in vals else dict([next(iter(vals.items()))])
        old = prior_vals.get(f)
        distinct = set(vals.values())

        if f in ov:
            new = ov[f]
            d.overridden.append(f)
            if len(distinct) == 1 and next(iter(distinct)) == new:
                d.stale_overrides.append(f)
            if len(vals) >= 2 and len(distinct) == 1:
                confirmed.add(f)
            d.values[f] = new
            if prior is not None and new != old:
                d.changes.append(Change(f, old, new, "override", []))
            continue

        if not vals:
            d.values[f] = old
            continue
        if len(distinct) > 1:
            d.conflicts[f] = vals
            d.values[f] = old if prior is not None and _present(old) else vals[order[0] if order[0] in vals else next(iter(vals))]
            continue

        new = next(iter(distinct))
        if len(vals) >= 2:
            confirmed.add(f)
        if prior is None or new == old:
            d.values[f] = new
            continue
        if len(vals) >= 2:
            d.changes.append(Change(f, old, new, "confirmed", list(vals)))
            d.values[f] = new
        elif f in (prior.confirmed_fields if prior else ()):
            d.held[f] = vals
            d.values[f] = old
        else:
            d.changes.append(Change(f, old, new, "single-source", list(vals)))
            d.values[f] = new

    said = [providers[s].released for s in order if providers[s].released is not None]
    d.released = bool((prior and prior.released) or any(said))

    d.extra = dict(prior.extra) if prior else {}
    for s in reversed(order):  # first source wins on shared keys
        d.extra.update({k: v for k, v in providers[s].extra.items() if v is not None})
    if "collectible" in ov:
        d.extra["collectible"] = bool(ov["collectible"])
        d.overridden.append("collectible")
    if "released" in ov:
        d.released = bool(ov["released"])
        d.overridden.append("released")

    kept_down = (prior.sources & set(down_sources)) if prior else set()
    d.sources = set(providers) | kept_down
    d.confirmed_fields = confirmed
    d.tags = _tags(kind, d.values, ov)

    if d.conflicts:
        d.status = CONFLICT
    elif d.held:
        d.status = PENDING
    elif len(d.sources) >= 2:
        d.status = CONFIRMED
    else:
        d.status = PROVISIONAL
    return d


def _tags(kind, values, ov) -> list[str]:
    if kind != CARD:
        return []
    tags = derive_tags(values.get("text") or "", values.get("cost"), values.get("power"))
    tags |= {t.lower() for t in ov.get("tags_add", [])}
    tags -= {t.lower() for t in ov.get("tags_remove", [])}
    return sorted(tags)
