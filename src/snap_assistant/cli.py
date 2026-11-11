"""Command-line interface.

Deck files are plain text, one card name per line. Blank lines and lines
starting with '#' are ignored.

Card data comes from the synced database when one exists (run
`snap-assistant sync`), otherwise from the small bundled sample.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from importlib import resources
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


def load_pool(args) -> CardPool:
    if args.cards:
        return CardPool.load(args.cards)
    from .pipeline.store import Store

    db = Path(args.db)
    if db.exists():
        store = Store(db)
        has = store.has_data()
        store.close()
        if has:
            return CardPool.from_db(db)
    print("(No synced database yet; using the bundled sample cards. "
          "Run `snap-assistant sync` for the full card list.)", file=sys.stderr)
    return CardPool.load()


def load_overrides(path: str | None) -> dict:
    text = Path(path).read_text() if path else \
        resources.files("snap_assistant.data").joinpath("overrides.json").read_text()
    data = json.loads(text)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def cmd_analyze(args):
    pool = load_pool(args)
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


def cmd_suggest(args):
    pool = load_pool(args)
    deck = load_deck(Path(args.deck), pool)
    for card, score in suggest(deck, pool, limit=args.limit):
        print(f"{score:>5}  [{card.cost}/{card.power}] {card.name} — {card.ability}")


def cmd_cards(args):
    pool = load_pool(args)
    cards = pool.with_tag(args.tag) if args.tag else list(pool)
    if args.search:
        q = args.search.lower()
        cards = [c for c in cards if q in c.name.lower() or q in c.ability.lower()]
    if args.newest:
        dated = sorted((c for c in cards if c.release_date), key=lambda c: c.release_date, reverse=True)
        if not dated:
            raise SystemExit("No release dates available. Run `snap-assistant sync` first.")
        for c in dated[:args.newest]:
            print(f"{c.release_date}  [{c.cost}/{c.power}] {c.name}: {c.ability}")
        return
    for c in sorted(cards, key=lambda c: (c.cost, c.name)):
        print(f"[{c.cost}/{c.power}] {c.name}: {c.ability}")


def cmd_locations(args):
    from .pipeline.store import Store

    store = Store(args.db)
    rows = store.entities("location", released_only=not args.all)
    store.close()
    if args.search:
        q = args.search.lower()
        rows = [r for r in rows if q in r["name"].lower() or q in (r["text"] or "").lower()]
    if not rows:
        print("No locations found. Run `snap-assistant sync` first." if not args.search else "No matches.")
    for r in rows:
        print(f"{r['name']}: {r['text']}")


def _with_store(args, fn, *a, **kw):
    from .assistant import NotFound
    from .pipeline.store import Store

    store = Store(args.db)
    try:
        print(fn(store, *a, **kw))
    except NotFound as e:
        raise SystemExit(str(e)) from None
    finally:
        store.close()


def cmd_show(args):
    from .assistant import describe_card

    _with_store(args, describe_card, args.name, args.kind)


def cmd_own(args):
    from .assistant import set_owned

    _with_store(args, set_owned, args.cards, not args.remove)


def cmd_collection(args):
    from .assistant import collection_summary

    _with_store(args, collection_summary)


def cmd_evals(args):
    from .assistant import check_evals

    _with_store(args, check_evals)


def cmd_rules(args):
    from .assistant import rules

    print(rules(" ".join(args.topic) if args.topic else None))


def cmd_pools(args):
    from .pipeline.store import Store

    store = Store(args.db)
    try:
        if not args.pool:
            pools = store.pools()
            if not pools:
                print("No pools yet. Run `snap-assistant sync` first.")
            for p in pools:
                refs = store.pool_refs(pool_id=p["pool_id"])
                gens = [r["card_name"] for r in refs if r["relation"] == "generates"]
                print(f"{p['name']}  [{p['pool_id']}, {p['kind']}, {p['size']} cards]"
                      + (f"  generated by: {', '.join(gens)}" if gens else ""))
            return
        p = store.pool(args.pool)
        if p is None:
            raise SystemExit(f"No pool {args.pool!r}. Run `snap-assistant pools` to list them.")
        print(f"{p['name']}  [{p['pool_id']}, {p['kind']}]  {p['description'] or ''}")
        for r in store.pool_refs(pool_id=p["pool_id"]):
            print(f"  {r['relation']}: {r['card_name']} [{r['origin']}]")
        members = store.pool_members(p["pool_id"])
        print(f"  {len(members)} cards:")
        for m in members:
            print(f"    [{m['cost']}/{m['power']}] {m['name']}: {m['text'] or '(no ability)'}")
    finally:
        store.close()


def cmd_issues(args):
    from .pipeline.store import Store

    store = Store(args.db)
    rows = store.issues()
    store.close()
    if not rows:
        print("No open conflicts or held changes.")
    for r in rows:
        vals = "; ".join(f"{s}: {v}" for s, v in json.loads(r["source_values"]).items())
        print(f"[{r['type']}] {r['name'] or r['def_id']} ({r['kind']}) {r['field']} — {vals}"
              f"  (since {r['first_seen'][:10]})")


def cmd_sync(args):
    from .pipeline.notify import notify
    from .pipeline.store import Store
    from .pipeline.sync import RunLock, sync

    home = Path(args.db).parent
    with RunLock(home / "sync.lock"):
        store = Store(args.db)
        try:
            result = sync(store, overrides=load_overrides(args.overrides),
                          raw_dir=home / "raw", dry_run=args.dry_run)
        finally:
            store.close()

    if not args.dry_run:
        reports = home / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        (reports / f"{stamp}.md").write_text(result.report)
        (reports / "latest.md").write_text(result.report)
    if not args.quiet:
        print(result.report)

    if args.notify and result.noteworthy:
        ds = result.decisions
        bits = []
        if (n := sum(d.is_new for d in ds)):
            bits.append(f"{n} new")
        if (n := sum(bool(d.changes) for d in ds)):
            bits.append(f"{n} changed")
        if result.new_issue_count:
            bits.append(f"{result.new_issue_count} new conflicts")
        down = [s.name for s in result.sources if not s.ok]
        if down:
            bits.append(f"source problem: {', '.join(down)}")
        title = "Snap data: sync failed" if result.status == "failed" else "Snap data updated"
        notify(title, (", ".join(bits) or result.status) + " — see reports/latest.md")
    return 2 if result.status == "failed" else 0


def main(argv=None):
    from .pipeline.store import default_db_path

    p = argparse.ArgumentParser(prog="snap-assistant", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cards", help="Use a cards.json file instead of the database")
    p.add_argument("--db", default=str(default_db_path()),
                   help="SQLite database path (default: %(default)s; or set SNAP_ASSISTANT_HOME)")
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
    c.add_argument("--search", help="Match name or ability text")
    c.add_argument("--newest", type=int, metavar="N", help="The N most recently released cards")
    c.set_defaults(func=cmd_cards)

    lo = sub.add_parser("locations", help="List locations from the database")
    lo.add_argument("--search", help="Match name or text")
    lo.add_argument("--all", action="store_true", help="Include unreleased locations")
    lo.set_defaults(func=cmd_locations)

    sh = sub.add_parser("show", help="Show one card/location with its change history")
    sh.add_argument("name", help="Name or game id")
    sh.add_argument("--location", dest="kind", action="store_const", const="location", default="card")
    sh.set_defaults(func=cmd_show)

    po = sub.add_parser("pools", help="List card pools, or show one pool's cards")
    po.add_argument("pool", nargs="?", help="Pool id or name")
    po.set_defaults(func=cmd_pools)

    ow = sub.add_parser("own", help="Record cards you own (use --remove to unmark)")
    ow.add_argument("cards", nargs="+", help="Card names; quote names with spaces")
    ow.add_argument("--remove", action="store_true")
    ow.set_defaults(func=cmd_own)

    co = sub.add_parser("collection", help="How much of the card pool you own")
    co.set_defaults(func=cmd_collection)

    ru = sub.add_parser("rules", help="Look up a rule or keyword (no topic: list sections)")
    ru.add_argument("topic", nargs="*")
    ru.set_defaults(func=cmd_rules)

    ev = sub.add_parser("evals", help="Check the rules test questions still match current card text")
    ev.set_defaults(func=cmd_evals)

    i = sub.add_parser("issues", help="List open conflicts and changes awaiting confirmation")
    i.set_defaults(func=cmd_issues)

    y = sub.add_parser("sync", help="Fetch, cross-validate and store the latest card/location data")
    y.add_argument("--dry-run", action="store_true", help="Fetch and compare but write nothing")
    y.add_argument("--notify", action="store_true", help="macOS notification when something changes")
    y.add_argument("--overrides", help="Overrides JSON (default: the bundled data/overrides.json)")
    y.add_argument("-q", "--quiet", action="store_true", help="Don't print the report")
    y.set_defaults(func=cmd_sync)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
