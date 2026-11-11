# Marvel Snap Deck Assistant

A small, dependency-free Python toolkit for building Marvel Snap decks:

- **Validate** decks (exactly 12 cards, no duplicates)
- **Analyze** energy curve, average cost, total power and archetype (by card tags)
- **Suggest** cards to add, ranked by tag synergy and curve gaps

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
snap-assistant analyze examples/destroy.txt
snap-assistant suggest examples/destroy.txt -n 5
snap-assistant cards --tag move
pytest
```

## Deck files

Plain text, one card name per line (case-insensitive). `#` starts a comment.

## Card data

`src/snap_assistant/data/cards.json` ships a small sample set. Card stats and
abilities change with balance patches, so treat it as seed data: extend it or
pass your own file with `--cards path/to/cards.json`. Each entry:

```json
{"name": "Knull", "cost": 6, "power": 0, "ability": "...", "tags": ["ongoing", "destroy"]}
```

Tags drive the archetype read and suggestions (e.g. `destroy`, `move`,
`ongoing`, `on-reveal`, `discard`, `zoo`).

## Layout

```
src/snap_assistant/
  models.py    Card, Deck, rule validation
  cards.py     CardPool (JSON loading, lookup, tag filter)
  analysis.py  curve/archetype analysis, suggestions
  cli.py       `snap-assistant` command
tests/         pytest suite
examples/      sample deck lists
```

## Ideas for next steps

- Import/export Snap's deck codes
- Pull card data from a maintained source instead of the bundled JSON
- Matchup notes and a web UI

*Fan project; not affiliated with Marvel, Second Dinner or Nuverse.*
