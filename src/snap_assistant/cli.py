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


def _names(rows, own_name: str, key: str = "name", id_key: str = "to_id") -> str:
    """Comma-separated names, adding the game id where names repeat (Nico's spells)."""
    found = [(r[key] or r[id_key], r[id_key]) for r in rows]
    names = [n for n, _ in found]
    return ", ".join(f"{n} ({i})" if names.count(n) > 1 or n == own_name else n for n, i in found)


def cmd_show(args):
    from .pipeline.store import Store

    store = Store(args.db)
    try:
        row = store.find(args.kind, args.name)
        if row is None:
            raise SystemExit(f"No {args.kind} named {args.name!r} in {args.db}")
        def_id, name = row["def_id"], row["name"]
        print(f"{name}  ({def_id})")
        if args.kind == "card":
            print(f"  Cost {row['cost']}  Power {row['power']}")
        print(f"  {row['text'] or '(no ability)'}")
        extra = json.loads(row["extra"])

        out_links = store.links_from(def_id) if args.kind == "card" else []
        in_links = store.links_to(def_id) if args.kind == "card" else []
        in_pools = store.pools_containing(def_id) if args.kind == "card" else []
        generators = [r for p in in_pools for r in store.pool_refs(pool_id=p["pool_id"])
                      if r["relation"] == "generates" and r["def_id"] != def_id]
        created = any(l["type"] == "creates" for l in in_links) or bool(generators)
        version_of = [l for l in out_links if l["type"] == "version_of"]

        flags = [row["status"], "released" if row["released"] else
                 "created in game" if created and not version_of else "unreleased"]
        if row["is_token"]:
            flags.append("token")
        if row["card_type"] not in (None, "Character"):
            flags.append(row["card_type"] if created else f"{row['card_type']} (game mode)")
        elif version_of:
            flags.append("game-mode version")
        elif args.kind == "card" and row["collectible"] == 0 and not created:
            flags.append("not collectible")
        print(f"  Status: {', '.join(flags)};  sources: {', '.join(json.loads(row['sources']))}")
        if args.kind == "card":
            print(f"  Tags: {', '.join(json.loads(row['tags'])) or '-'}")
        if row["release_date"]:
            when = "Released" if row["released"] else "Scheduled"
            note = {True: "", False: " (sources differ; earliest shown)", None: ""}[extra.get("release_date_agreed")]
            print(f"  {when}: {row['release_date']}{note}")
        if extra.get("patch"):
            print(f"  Last changed in game patch {extra['patch']}")

        sections = [
            ("Creates", [l for l in out_links if l["type"] == "creates"], "to_id"),
            ("Created by", [l for l in in_links if l["type"] == "creates"], "from_id"),
            ("Version of", version_of, "to_id"),
            ("Game-mode versions", [l for l in in_links if l["type"] == "version_of"], "from_id"),
            ("Related", [l for l in out_links if l["type"] not in ("creates", "version_of")]
                        + [l for l in in_links if l["type"] not in ("creates", "version_of")], None),
        ]
        for label, rows, id_key in sections:
            if not rows:
                continue
            if id_key is None:   # related: show whichever end isn't this card
                rows = [{"name": l["name"], "to_id": l["to_id"] if l["from_id"] == def_id else l["from_id"]}
                        for l in rows]
                id_key = "to_id"
            print(f"  {label}: {_names(rows, name, id_key=id_key)}")
        for r in store.pool_refs(def_id=def_id):
            size = len(store.pool_members(r["pool_id"]))
            verb = "Generates from" if r["relation"] == "generates" else "References"
            origin = "" if r["origin"] == "source" else f" [{r['origin']}]"
            print(f"  {verb}: {r['pool_name']} ({size} cards){origin}")
        makers = {l["from_id"] for l in in_links if l["type"] == "creates"}
        for p in in_pools:
            gens = [r for r in generators if r["pool_id"] == p["pool_id"] and r["def_id"] not in makers]
            if gens:
                print(f"  Can be generated by: {', '.join(g['card_name'] for g in gens)} (via {p['name']})")

        hist = [h for h in store.history(args.kind, def_id) if h["how"] != "new"]
        if hist:
            print("  History:")
            for h in hist:
                print(f"    {h['at'][:10]}  {h['field']}: {h['old']} → {h['new']}  [{h['how']}"
                      + (f", patch {h['patch']}" if h["patch"] else "") + "]")
    finally:
        store.close()


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
