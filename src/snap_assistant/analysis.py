"""Deck analysis and simple card suggestions."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .cards import CardPool
from .models import Card, Deck

# A loose "healthy" curve target for a 6-turn game: cards per cost bucket (6+ grouped).
TARGET_CURVE = {1: 2, 2: 3, 3: 2, 4: 2, 5: 1, 6: 2}


@dataclass
class DeckReport:
    deck_name: str
    errors: list[str]
    curve: dict[int, int]
    avg_cost: float
    total_power: int
    archetypes: list[tuple[str, int]]
    warnings: list[str]


def energy_curve(cards: list[Card]) -> dict[int, int]:
    counts = Counter(min(c.cost, 6) for c in cards)
    return {cost: counts.get(cost, 0) for cost in range(0, 7)}


def archetypes(cards: list[Card], top: int = 3) -> list[tuple[str, int]]:
    """Most common tags in the deck — a rough read on its game plan."""
    return Counter(t for c in cards for t in c.tags).most_common(top)


def analyze(deck: Deck) -> DeckReport:
    cards = deck.cards
    curve = energy_curve(cards)
    warnings = []
    if curve[1] + curve[2] < 3:
        warnings.append("Few early plays (1-2 cost); you may fall behind on turns 1-2.")
    if curve[6] > 3:
        warnings.append("Top-heavy: more than three 6+ cost cards.")
    if sum(curve[c] for c in (4, 5, 6)) == 0 and cards:
        warnings.append("No late-game payoff (4+ cost).")
    return DeckReport(
        deck_name=deck.name,
        errors=deck.validate(),
        curve=curve,
        avg_cost=round(sum(c.cost for c in cards) / len(cards), 2) if cards else 0.0,
        total_power=sum(c.power for c in cards),
        archetypes=archetypes(cards),
        warnings=warnings,
    )


def suggest(deck: Deck, pool: CardPool, limit: int = 5) -> list[tuple[Card, float]]:
    """Rank cards not in the deck by tag synergy plus how much they fill curve gaps."""
    in_deck = {c.name for c in deck.cards}
    tag_weights = Counter(t for c in deck.cards for t in c.tags)
    curve = energy_curve(deck.cards)
    gaps = {cost: max(TARGET_CURVE.get(cost, 0) - curve.get(cost, 0), 0) for cost in TARGET_CURVE}

    scored = []
    for card in pool:
        if card.name in in_deck:
            continue
        synergy = sum(tag_weights[t] for t in card.tags)
        curve_fit = gaps.get(min(card.cost, 6), 0)
        score = synergy + 1.5 * curve_fit
        if score > 0:
            scored.append((card, round(score, 2)))
    scored.sort(key=lambda x: (-x[1], x[0].cost, x[0].name))
    return scored[:limit]
