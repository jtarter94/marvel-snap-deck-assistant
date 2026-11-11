"""MCP server: lets Claude consult the card database, rules, collection and decks.

Run with `snap-assistant-mcp` (stdio). Needs the optional extra:
`pip install -e ".[mcp]"`. Reads the same database as the CLI
(SNAP_ASSISTANT_HOME / default location); run `snap-assistant sync` first.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import assistant as A
from .pipeline.store import Store, default_db_path

INSTRUCTIONS = """\
Marvel Snap deck-building assistant for a player who builds for fun: favour
creative, unconventional decks and interesting interactions over the meta.

Ground every claim about a card in its current text from get_card or
search_cards (cards change with patches; don't rely on memory). Before
explaining an interaction, check the relevant rules sections with `rules`;
sections marked "from-card-text" are inferred, so say when an answer depends
on them. Deck-buildable means released, collectible characters and Skills
(Skills like The Inversion or Web Sling go in decks too); tokens, generated
Skills (e.g. Polymorph) and game-mode versions only appear through card
effects (see pools and get_card's "Created by").
When the player has recorded a collection, point out cards they don't own so
they can plan Token spending, but never limit ideas to owned cards unless asked.
"""

mcp = FastMCP("snap-assistant", instructions=INSTRUCTIONS)


def _db_path() -> Path:
    return Path(os.environ.get("SNAP_ASSISTANT_DB") or default_db_path())


@contextmanager
def _store():
    path = _db_path()
    if not path.exists():
        raise RuntimeError(f"No card database at {path}. Run `snap-assistant sync` first.")
    s = Store(path)
    try:
        yield s
    finally:
        s.close()


def _run(fn, *args, **kwargs) -> str:
    with _store() as s:
        try:
            return fn(s, *args, **kwargs)
        except A.NotFound as e:
            return str(e)


# --- cards & locations ---------------------------------------------------------

@mcp.tool()
def search_cards(text: str | None = None, cost: int | None = None, min_cost: int | None = None,
                 max_cost: int | None = None, min_power: int | None = None, max_power: int | None = None,
                 tag: str | None = None, keyword: str | None = None, pool: str | None = None,
                 released_after: str | None = None, owned: str = "any", include_non_deck: bool = False,
                 sort: str = "cost", limit: int = 40) -> str:
    """Search cards. Defaults to deck-buildable cards.

    text: substring of name or ability text; use "a|b" to require several phrases.
    tag: derived theme tag, e.g. on-reveal, ongoing, destroy, discard, move, afflict,
      buff, ramp, cost-reduction, add-cards, steal, copy, end-of-turn, activate, zoo, vanilla.
    keyword: official keyword, e.g. "On Reveal", "Ongoing", "Activate", "Moveable", "Objective".
    pool: only cards in a pool (see list_pools), e.g. "all-skills".
    released_after: ISO date. owned: any | owned | unowned.
    include_non_deck: also include tokens, Skills, game-mode and unreleased cards.
    sort: cost | power | name | newest | oldest.
    """
    return _run(A.search_cards, text=text, cost=cost, min_cost=min_cost, max_cost=max_cost,
                min_power=min_power, max_power=max_power, tag=tag, keyword=keyword, pool=pool,
                released_after=released_after, owned=owned, include_non_deck=include_non_deck,
                sort=sort, limit=limit)


@mcp.tool()
def get_card(name: str) -> str:
    """Full detail for one card: text, cost/power, keywords, release date, what it creates or
    is created by, pools it generates from, game-mode versions, change history, ownership."""
    return _run(A.describe_card, name, "card")


@mcp.tool()
def get_cards(names: list[str]) -> str:
    """Full detail for several cards at once."""
    with _store() as s:
        out = []
        for n in names:
            try:
                out.append(A.describe_card(s, n, "card"))
            except A.NotFound as e:
                out.append(str(e))
        return "\n\n".join(out)


@mcp.tool()
def random_cards(n: int = 5, tag: str | None = None, max_cost: int | None = None,
                 owned: str = "any", seed: int | None = None) -> str:
    """Random deck-buildable cards, for inspiration ("build around one of these")."""
    return _run(A.random_cards, n, tag=tag, max_cost=max_cost, owned=owned, seed=seed)


@mcp.tool()
def search_locations(text: str | None = None, include_unreleased: bool = False) -> str:
    """Locations whose name or text contains `text` (all released ones if omitted)."""
    return _run(A.search_locations, text, include_unreleased)


@mcp.tool()
def get_location(name: str) -> str:
    """Full detail for one location."""
    return _run(A.describe_card, name, "location")


@mcp.tool()
def list_pools() -> str:
    """Card pools (All Skills, team pools, named pools like Merlin's Incantations) and which
    cards generate from them."""
    return _run(A.list_pools)


@mcp.tool()
def get_pool(pool: str) -> str:
    """Every card in a pool, plus which cards generate from or reference it."""
    return _run(A.describe_pool, pool)


@mcp.tool()
def recent_changes(days: int = 30) -> str:
    """Card changes (balance patches) recorded in the last `days` days."""
    return _run(A.recent_changes, days)


# --- rules ---------------------------------------------------------------------

@mcp.tool()
def rules(topic: str | None = None) -> str:
    """Rules reference: core rules, keywords, mechanics and interaction principles.
    Omit topic for the index. Examples: "reveal order", "Ongoing", "Merge", "front row"."""
    return A.rules(topic)


# --- decks ---------------------------------------------------------------------

@mcp.tool()
def analyze_deck(cards: list[str]) -> str:
    """Check a deck (12 card names): validity, curve, themes, keywords, created cards,
    pools, and which cards the player doesn't own."""
    return _run(A.analyze_deck, cards)


@mcp.tool()
def suggest_cards(cards: list[str], limit: int = 10, owned: str = "any") -> str:
    """Cards that share themes with a partial deck and fill curve gaps (a starting point,
    not a verdict; look for unusual synergies yourself too)."""
    return _run(A.suggest_for_deck, cards, limit, owned)


@mcp.tool()
def save_deck(name: str, cards: list[str], notes: str | None = None) -> str:
    """Save (or overwrite) a deck idea under a name, with optional notes on the plan."""
    return _run(A.save_deck, name, cards, notes)


@mcp.tool()
def list_decks() -> str:
    """Saved deck ideas."""
    return _run(A.list_decks)


@mcp.tool()
def get_deck(name: str) -> str:
    """A saved deck with its full analysis."""
    return _run(A.show_deck, name)


# --- collection --------------------------------------------------------------------

@mcp.tool()
def set_owned(cards: list[str], owned: bool = True) -> str:
    """Record that the player owns (or doesn't own) these cards."""
    return _run(A.set_owned, cards, owned)


@mcp.tool()
def collection_summary() -> str:
    """How many deck-buildable cards the player owns, and what's missing by collection series."""
    return _run(A.collection_summary)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
