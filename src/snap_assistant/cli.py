"""Command-line interface.

Deck files are plain text, one card name per line. Blank lines and lines
starting with '#' are ignored.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import analyze, suggest
from .cards import CardPool
from .models import Deck


def load_deck(path: Path, pool: CardPool) -> Deck:
    names = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    unknown = [n for n in names if n not in pool]
    if unknown:
        raise SystemExit(f"Unknown card(s): {', '.join(unknown)}")
    return Deck(name=path.stem, cards=[pool.get(n) for n in names])


def cmd_analyze(args, pool):
    deck = load_deck(Path(args.deck), pool)
    r = analyze(deck)
    print(f"Deck: {r.deck_name}  ({len(deck.cards)} cards)")
    print("Valid: yes" if not r.errors else "Valid: NO")
    for e in r.errors:
        print(f"  ! {e}")
    print(f"Avg cost: {r.avg_cost}   Total power: {r.total_power}")
    print("Curve:")
    for cost, n in r.curve.items():
        label = f"{cost}+" if cost == 6 else f"{cost} "
        print(f"  {label} | {'#' * n} {n}")
    if r.archetypes:
        print("Archetype: " + ", ".join(f"{t} ({n})" for t, n in r.archetypes))
    for w in r.warnings:
        print(f"  * {w}")


def cmd_suggest(args, pool):
    deck = load_deck(Path(args.deck), pool)
    for card, score in suggest(deck, pool, limit=args.limit):
        print(f"{score:>5}  [{card.cost}/{card.power}] {card.name} — {card.ability}")


def cmd_cards(args, pool):
    cards = pool.with_tag(args.tag) if args.tag else list(pool)
    for c in sorted(cards, key=lambda c: (c.cost, c.name)):
        print(f"[{c.cost}/{c.power}] {c.name}: {c.ability}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="snap-assistant", description=__doc__)
    p.add_argument("--cards", help="Path to a custom cards.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="Validate a deck and show its curve")
    a.add_argument("deck")
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("suggest", help="Suggest cards to add")
    s.add_argument("deck")
    s.add_argument("-n", "--limit", type=int, default=5)
    s.set_defaults(func=cmd_suggest)

    c = sub.add_parser("cards", help="List known cards")
    c.add_argument("--tag")
    c.set_defaults(func=cmd_cards)

    args = p.parse_args(argv)
    pool = CardPool.load(args.cards)
    args.func(args, pool)
    return 0


if __name__ == "__main__":
    sys.exit(main())
