"""Derive archetype tags from ability text.

These drive the archetype read and suggestions, so new cards get useful tags
the moment they appear in the data. Rules are deliberately simple and
readable; fix a misfire for one card with ``tags_add`` / ``tags_remove`` in
the overrides file rather than making a regex clever.
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, str]] = [
    ("on-reveal", r"\bon reveal\b"),
    ("ongoing", r"\bongoing\b"),
    ("activate", r"\bactivate\b"),
    ("end-of-turn", r"\bend of (?:each |the |your |that )?turn\b"),
    ("game-start", r"\bgame start\b"),
    ("destroy", r"\bdestroy"),
    ("discard", r"\bdiscard"),
    ("move", r"\bmoves?\b|\bmoving\b|\bmoved\b"),
    ("afflict", r"-\d+ power\b"),
    ("buff", r"\+\d+ power\b"),
    ("bounce", r"\breturns? (?:it|them|this|a card|.{0,30}) to your hand\b"),
    ("ramp", r"\+\d+ (?:max )?energy\b|\bmax energy\b"),
    ("cost-reduction", r"\bcosts? \d+ less\b|\bcosts? less\b|-\d+ cost\b"),
    ("cost-increase", r"\+\d+ cost\b"),
    ("add-cards", r"\badd (?:a|an|two|three|\d+|copies|copy|the|it|them|one)\b.{0,60}\b(?:to|into) (?:your|their|each|the other) (?:hand|deck)\b|\badd .{0,40}\bhere\b|\bget (?:a|an|another|\d+) [A-Z]"),
    ("copy", r"\bcop(?:y|ies)\b"),
    ("steal", r"\bsteal"),
    ("location", r"\blocation\b"),
    ("deck-manipulation", r"\byour deck\b"),
]
_COMPILED = [(tag, re.compile(rx, re.IGNORECASE)) for tag, rx in _RULES]


def derive_tags(text: str, cost: int | None = None, power: int | None = None) -> set[str]:
    tags = {tag for tag, rx in _COMPILED if rx.search(text or "")}
    if not text:
        tags.add("vanilla")
    # Cheap, high-power bodies with little text are the core of "zoo" decks.
    if cost is not None and cost <= 2 and power is not None and power >= cost + 1:
        tags.add("zoo")
    return tags
