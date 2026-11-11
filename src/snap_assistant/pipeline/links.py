"""How cards relate to each other: links between cards, and pools of cards.

All cards live in one ``entities`` table; this module derives the graph on
top of it each sync (it's rebuilt from scratch, so it never drifts):

* **Links** (card -> card): ``creates`` (Vampire Killmonger -> Vampiric
  Spear), ``version_of`` (Scarlet Witch - Brotherhood of Mutants -> Scarlet
  Witch), ``related`` (anything else the source links). Built from
  marvelsnap.pro's two-way ``connected_cards`` plus name rules.
* **Pools** (named sets of cards a card can pull from):
    - rule pools that grow by themselves, e.g. *All Skills*;
    - team pools from game-mode versions ("X - Spider-Verse");
    - named pools from a card's text + links ("Add an Incantation" + the
      three cards Merlin links to).
* **Pool refs** (card -> pool): ``generates`` (adds/gets cards from it) or
  ``references`` (other effects that mention it), inferred from text.

Each item records its origin (``source`` / ``inferred`` / ``manual``). The
overrides file can add or remove links and pool refs where inference is
wrong or the sources say nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .reconcile import Decision
from .sources import CARD

CREATES, VERSION_OF, RELATED = "creates", "version_of", "related"
GENERATES, REFERENCES = "generates", "references"

# Pools defined by a rule over card fields; membership updates every sync.
RULE_POOLS = {
    "all-skills": ("All Skills", "Every Skill card, wherever it comes from.",
                   lambda d: d.extra.get("card_type") == "Skill"),
}
# Text that means "pull from this rule pool".
RULE_POOL_TEXT = {
    "all-skills": re.compile(r"\brandom skill\b", re.I),
}

_TEAM_SUFFIX = re.compile(r"^(?P<base>.+?) - (?P<team>.+)$")
_CHAMPION = re.compile(r"^(?P<base>.+?) Champion$")
_GENERATE_VERB = re.compile(r"\b(?:add|adds|get|gets|create|creates|generate)\b", re.I)
_FROM_DECK = re.compile(r"\bfrom your deck\b", re.I)   # drawing your own cards isn't generating
_NAMED_POOL = re.compile(r"\b(?:[Aa]dd|[Gg]et) (?:a|an) (?P<word>[A-Z][\w-]+)\b(?! card)")


@dataclass
class Pool:
    pool_id: str
    name: str
    kind: str                 # rule | team | named | manual
    description: str
    members: set[str] = field(default_factory=set)


@dataclass
class Graph:
    links: dict[tuple[str, str, str], str] = field(default_factory=dict)      # (from, to, type) -> origin
    pools: dict[str, Pool] = field(default_factory=dict)
    refs: dict[tuple[str, str, str], str] = field(default_factory=dict)       # (card, pool, relation) -> origin


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def deck_buildable(d: Decision) -> bool:
    x = d.extra
    return (x.get("card_type") in (None, "Character") and not x.get("is_token")
            and x.get("collectible") is not False)


def build_graph(decisions: list[Decision], overrides: dict | None = None) -> Graph:
    overrides = overrides or {}
    cards = {d.def_id: d for d in decisions if d.kind == CARD}
    by_name: dict[str, list[Decision]] = {}
    for d in cards.values():
        by_name.setdefault(d.name.lower(), []).append(d)
    g = Graph()

    # --- versions: "X - Team" and "X Champion" are game-mode versions of X ---
    teams: dict[str, set[str]] = {}
    for d in cards.values():
        if deck_buildable(d) or d.extra.get("is_token"):
            continue
        m = _TEAM_SUFFIX.match(d.name) or _CHAMPION.match(d.name)
        if not m:
            continue
        base = [b for b in by_name.get(m["base"].lower(), []) if deck_buildable(b)]
        if base:
            g.links[(d.def_id, base[0].def_id, VERSION_OF)] = "inferred"
        if "team" in m.groupdict() and m["team"]:
            teams.setdefault(m["team"], set()).add(d.def_id)
    versions = {(a, b) for a, b, t in g.links if t == VERSION_OF}

    # --- source links, given a direction ---
    for a in cards.values():
        text = (a.values.get("text") or "").lower()
        for b_id in a.extra.get("related") or []:
            b = cards.get(b_id)
            if b is None or b_id == a.def_id or (a.def_id, b_id) in versions or (b_id, a.def_id) in versions:
                continue
            names_it = b.name.lower() in text
            if not deck_buildable(b) and (deck_buildable(a) or names_it):
                g.links[(a.def_id, b_id, CREATES)] = "source"
            elif deck_buildable(b) and not deck_buildable(a):
                continue          # the other card's pass records this as `creates`
            elif a.def_id < b_id:
                g.links[(a.def_id, b_id, RELATED)] = "source"

    # --- pools ---
    for pid, (name, desc, rule) in RULE_POOLS.items():
        g.pools[pid] = Pool(pid, name, "rule", desc, {d.def_id for d in cards.values() if rule(d)})
    for team, members in teams.items():
        pid = f"team-{_slug(team)}"
        g.pools[pid] = Pool(pid, team, "team", f"{team} game-mode cards", set(members))
    created = {}
    for (a, b, t) in g.links:
        if t == CREATES:
            created.setdefault(a, set()).add(b)
    for a_id, made in created.items():
        m = _NAMED_POOL.search(cards[a_id].values.get("text") or "")
        if len(made) >= 2 and m and m["word"].lower() not in by_name:
            word = m["word"]
            pid = f"{_slug(word)}-{_slug(a_id)}"
            g.pools[pid] = Pool(pid, f"{word} ({cards[a_id].name})", "named",
                                f"What {cards[a_id].name}'s text calls an {word}", set(made))
            g.refs[(a_id, pid, GENERATES)] = "inferred"

    # --- pool refs from text ---
    team_aliases = []
    for pid, pool in g.pools.items():
        if pool.kind == "team":
            words = pool.name.replace("The ", "").split()
            aliases = {pool.name, words[0]} if len(words[0]) >= 5 else {pool.name}
            for alias in aliases:
                team_aliases.append((pid, re.compile(rf"\b{re.escape(alias)}\b (?:cards?|characters?)", re.I)))
    for d in cards.values():
        text = d.values.get("text") or ""
        for sentence in re.split(r"(?<=[.!])\s+", text):
            relation = (GENERATES if _GENERATE_VERB.search(sentence) and not _FROM_DECK.search(sentence)
                        else REFERENCES)
            for pid, rx in RULE_POOL_TEXT.items():
                if rx.search(sentence):
                    g.refs[(d.def_id, pid, relation)] = "inferred"
            for pid, rx in team_aliases:
                if rx.search(sentence):
                    g.refs[(d.def_id, pid, relation)] = "inferred"

    _apply_overrides(g, overrides, cards)
    return g


def _apply_overrides(g: Graph, overrides: dict, cards: dict):
    for p in overrides.get("pools", []):
        pool = g.pools.setdefault(p["id"], Pool(p["id"], p.get("name", p["id"]), "manual", p.get("description", "")))
        pool.members |= {m for m in p.get("members", []) if m in cards}
        pool.members -= set(p.get("remove_members", []))
    for link in overrides.get("links", []):
        key = (link["from"], link["to"], link.get("type", CREATES))
        if link.get("remove"):
            g.links.pop(key, None)
        else:
            g.links[key] = "manual"
    for ref in overrides.get("pool_refs", []):
        key = (ref["card"], ref["pool"], ref.get("relation", GENERATES))
        if ref.get("remove"):
            g.refs.pop(key, None)
        else:
            g.refs[key] = "manual"
