"""Queries behind the CLI and the MCP server, returning readable text.

Everything takes an open ``Store``. Output is plain text tuned to be read by
a person or a model: one card per line in lists, full detail on request.
"""
from __future__ import annotations

import difflib
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import knowledge
from .analysis import analyze, suggest
from .cards import CardPool, _key
from .models import Card, Deck
from .pipeline.store import Store

DECK_BUILDABLE = ("kind = 'card' AND released = 1 AND is_token = 0"
                  " AND COALESCE(card_type, 'Character') = 'Character' AND COALESCE(collectible, 1) = 1")


class NotFound(ValueError):
    pass


# --- lookups -----------------------------------------------------------------

def resolve(store: Store, name: str, kind: str = "card"):
    """Find a card/location by name or game id, tolerating punctuation and typos."""
    row = store.find(kind, name)
    if row is not None:
        return row
    rows = list(store.db.execute("SELECT * FROM entities WHERE kind = ?", (kind,)))
    by_key = {}
    for r in rows:
        for k in (_key(r["name"] or ""), _key(r["def_id"])):
            # Prefer the deck card over a game-mode version with the same name.
            if k not in by_key or (r["released"] and not r["is_token"] and not by_key[k]["released"]):
                by_key[k] = r
    k = _key(name)
    if k in by_key:
        return by_key[k]
    close = difflib.get_close_matches(k, list(by_key), n=3, cutoff=0.75)
    if len(close) == 1:
        return by_key[close[0]]
    hint = f" Did you mean: {', '.join(by_key[c]['name'] for c in close)}?" if close else ""
    raise NotFound(f"No {kind} named {name!r}.{hint}")


def _owned_label(store: Store, def_id: str, owned: dict[str, bool] | None = None) -> str:
    owned = store.owned() if owned is None else owned
    if not owned:
        return ""
    return " ✓owned" if owned.get(def_id) else " ✗not owned"


def card_line(r, owned: dict[str, bool] | None = None) -> str:
    tags = ", ".join(json.loads(r["tags"]))
    own = ""
    if owned:
        own = "  ✓owned" if owned.get(r["def_id"]) else "  ✗not owned"
    return (f"[{r['cost']}/{r['power']}] {r['name']}: {r['text'] or '(no ability)'}"
            + (f"  {{{tags}}}" if tags else "") + own)


def describe_card(store: Store, name: str, kind: str = "card") -> str:
    row = resolve(store, name, kind)
    def_id, cname = row["def_id"], row["name"]
    out = [f"{cname}  ({def_id})"]
    if kind == "card":
        out.append(f"  Cost {row['cost']}  Power {row['power']}")
    out.append(f"  {row['text'] or '(no ability)'}")
    extra = json.loads(row["extra"])

    out_links = store.links_from(def_id) if kind == "card" else []
    in_links = store.links_to(def_id) if kind == "card" else []
    in_pools = store.pools_containing(def_id) if kind == "card" else []
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
    elif kind == "card" and row["collectible"] == 0 and not created:
        flags.append("not collectible")
    if kind == "card" and _is_deck_buildable(row):
        flags.append("deck-buildable")
        own = _owned_label(store, def_id).strip()
        if own:
            flags.append(own)
    out.append(f"  Status: {', '.join(flags)};  sources: {', '.join(json.loads(row['sources']))}")
    if kind == "card":
        out.append(f"  Tags: {', '.join(json.loads(row['tags'])) or '-'}")
    if extra.get("keywords"):
        out.append(f"  Keywords: {', '.join(extra['keywords'])}  (see rules)")
    if row["release_date"]:
        when = "Released" if row["released"] else "Scheduled"
        note = {True: "", False: " (sources differ; earliest shown)", None: ""}[extra.get("release_date_agreed")]
        out.append(f"  {when}: {row['release_date']}{note}")
    if extra.get("series"):
        out.append(f"  Collection: {extra['series']}")
    if extra.get("patch"):
        out.append(f"  Last changed in game patch {extra['patch']}")

    def names(rows, id_key):
        found = [(r["name"] or r[id_key], r[id_key]) for r in rows]
        ns = [n for n, _ in found]
        return ", ".join(f"{n} ({i})" if ns.count(n) > 1 or n == cname else n for n, i in found)

    related = [{"name": l["name"], "to_id": l["to_id"]} for l in out_links
               if l["type"] not in ("creates", "version_of")]
    related += [{"name": l["name"], "to_id": l["from_id"]} for l in in_links
                if l["type"] not in ("creates", "version_of")]
    for label, rows, id_key in (
        ("Creates", [l for l in out_links if l["type"] == "creates"], "to_id"),
        ("Created by", [l for l in in_links if l["type"] == "creates"], "from_id"),
        ("Version of", version_of, "to_id"),
        ("Game-mode versions", [l for l in in_links if l["type"] == "version_of"], "from_id"),
        ("Related", related, "to_id"),
    ):
        if rows:
            out.append(f"  {label}: {names(rows, id_key)}")
    for r in store.pool_refs(def_id=def_id):
        size = len(store.pool_members(r["pool_id"]))
        verb = "Generates from" if r["relation"] == "generates" else "References"
        origin = "" if r["origin"] == "source" else f" [{r['origin']}]"
        out.append(f"  {verb}: {r['pool_name']} ({size} cards){origin}")
    makers = {l["from_id"] for l in in_links if l["type"] == "creates"}
    for p in in_pools:
        gens = [r for r in generators if r["pool_id"] == p["pool_id"] and r["def_id"] not in makers]
        if gens:
            out.append(f"  Can be generated by: {', '.join(g['card_name'] for g in gens)} (via {p['name']})")

    hist = [h for h in store.history(kind, def_id) if h["how"] != "new"]
    if hist:
        out.append("  History:")
        for h in hist:
            out.append(f"    {h['at'][:10]}  {h['field']}: {h['old']} → {h['new']}  [{h['how']}"
                       + (f", patch {h['patch']}" if h["patch"] else "") + "]")
    return "\n".join(out)


def _is_deck_buildable(r) -> bool:
    return (r["kind"] == "card" and r["released"] and not r["is_token"]
            and (r["card_type"] or "Character") == "Character" and (r["collectible"] is None or r["collectible"]))


# --- search ------------------------------------------------------------------

def search_cards(store: Store, *, text: str | None = None, cost: int | None = None,
                 min_cost: int | None = None, max_cost: int | None = None,
                 min_power: int | None = None, max_power: int | None = None,
                 tag: str | None = None, keyword: str | None = None, pool: str | None = None,
                 released_after: str | None = None, owned: str = "any",
                 include_non_deck: bool = False, sort: str = "cost", limit: int = 40) -> str:
    where = ["kind = 'card'"] if include_non_deck else [DECK_BUILDABLE]
    args: list = []
    if text:
        for word in text.split("|"):   # "a|b" = all of these phrases
            where.append("(name LIKE ? OR text LIKE ?)")
            args += [f"%{word.strip()}%"] * 2
    for col, op, val in (("cost", "=", cost), ("cost", ">=", min_cost), ("cost", "<=", max_cost),
                         ("power", ">=", min_power), ("power", "<=", max_power),
                         ("release_date", ">=", released_after)):
        if val is not None:
            where.append(f"{col} {op} ?")
            args.append(val)
    if tag:
        where.append("EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)")
        args.append(tag.lower())
    if keyword:
        where.append("EXISTS (SELECT 1 FROM json_each(json_extract(extra, '$.keywords')) WHERE value LIKE ?)")
        args.append(keyword)
    if pool:
        p = store.pool(pool)
        if p is None:
            raise NotFound(f"No pool {pool!r}. Use list_pools to see them.")
        where.append("def_id IN (SELECT def_id FROM pool_members WHERE pool_id = ?)")
        args.append(p["pool_id"])
    own = store.owned()
    ids = [d for d, o in own.items() if o]
    if owned == "owned":
        where.append(f"def_id IN ({','.join('?' * len(ids))})" if ids else "0")
        args += ids
    elif owned == "unowned" and ids:
        where.append(f"def_id NOT IN ({','.join('?' * len(ids))})")
        args += ids
    order = {"cost": "cost, name", "power": "power DESC, name", "name": "name",
             "newest": "release_date DESC, name", "oldest": "release_date, name"}.get(sort, "cost, name")
    rows = list(store.db.execute(f"SELECT * FROM entities WHERE {' AND '.join(where)} ORDER BY {order}", args))
    if not rows:
        return "No matching cards."
    head = f"{len(rows)} card(s)" + (f", showing {limit}" if len(rows) > limit else "") + ":"
    return "\n".join([head] + [card_line(r, own) for r in rows[:limit]])


def random_cards(store: Store, n: int = 5, *, tag: str | None = None, max_cost: int | None = None,
                 owned: str = "any", seed: int | None = None) -> str:
    rows = list(store.db.execute(f"SELECT * FROM entities WHERE {DECK_BUILDABLE}"))
    own = store.owned()
    if tag:
        rows = [r for r in rows if tag.lower() in json.loads(r["tags"])]
    if max_cost is not None:
        rows = [r for r in rows if r["cost"] <= max_cost]
    if owned == "owned":
        rows = [r for r in rows if own.get(r["def_id"])]
    elif owned == "unowned":
        rows = [r for r in rows if not own.get(r["def_id"])]
    picks = random.Random(seed).sample(rows, min(n, len(rows)))
    return "\n".join(card_line(r, own) for r in sorted(picks, key=lambda r: (r["cost"], r["name"]))) or "No cards."


def search_locations(store: Store, text: str | None = None, include_unreleased: bool = False) -> str:
    sql = "SELECT * FROM entities WHERE kind = 'location'" + ("" if include_unreleased else " AND released = 1")
    args = []
    if text:
        sql += " AND (name LIKE ? OR text LIKE ?)"
        args = [f"%{text}%"] * 2
    rows = list(store.db.execute(sql + " ORDER BY name", args))
    return "\n".join(f"{r['name']}: {r['text']}" for r in rows) or "No matching locations."


def list_pools(store: Store) -> str:
    lines = []
    for p in store.pools():
        gens = [r["card_name"] for r in store.pool_refs(pool_id=p["pool_id"]) if r["relation"] == "generates"]
        lines.append(f"{p['name']}  [{p['pool_id']}, {p['kind']}, {p['size']} cards]"
                     + (f"  generated by: {', '.join(gens)}" if gens else ""))
    return "\n".join(lines) or "No pools yet. Run a sync first."


def describe_pool(store: Store, pool: str) -> str:
    p = store.pool(pool)
    if p is None:
        raise NotFound(f"No pool {pool!r}. Use list_pools to see them.")
    out = [f"{p['name']}  [{p['pool_id']}, {p['kind']}]  {p['description'] or ''}"]
    for r in store.pool_refs(pool_id=p["pool_id"]):
        out.append(f"  {r['relation']}: {r['card_name']} [{r['origin']}]")
    members = store.pool_members(p["pool_id"])
    out.append(f"  {len(members)} cards:")
    out += [f"    [{m['cost']}/{m['power']}] {m['name']}: {m['text'] or '(no ability)'}" for m in members]
    return "\n".join(out)


def recent_changes(store: Store, days: int = 30) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = store.recent_history(since)
    if not rows:
        return f"No card changes recorded in the last {days} days."
    return "\n".join(f"{h['at'][:10]}  {h['name'] or h['def_id']}: {h['field']} {h['old']} → {h['new']}"
                     + (f" (patch {h['patch']})" if h["patch"] else "") for h in rows)


def rules(topic: str | None = None) -> str:
    if not topic:
        return "Rules reference sections (ask for any by name):\n" + knowledge.index()
    found = knowledge.lookup(topic)
    if not found:
        return f"No rules section matches {topic!r}.\n\n" + knowledge.index()
    return "\n".join(s.render() for s in found[:3])


# --- decks -------------------------------------------------------------------

def _deck_cards(store: Store, names: list[str]) -> tuple[list, list[str]]:
    rows, problems = [], []
    for n in names:
        try:
            r = resolve(store, n)
        except NotFound as e:
            problems.append(str(e))
            continue
        if not _is_deck_buildable(r):
            problems.append(f"{r['name']} can't go in a deck (token, Skill, game-mode or unreleased card).")
        rows.append(r)
    return rows, problems


def _to_card(r) -> Card:
    return Card(name=r["name"], cost=r["cost"] or 0, power=r["power"] or 0, ability=r["text"] or "",
                tags=frozenset(json.loads(r["tags"])), def_id=r["def_id"], release_date=r["release_date"])


def analyze_deck(store: Store, cards: list[str]) -> str:
    rows, problems = _deck_cards(store, cards)
    deck = Deck("deck", [_to_card(r) for r in rows])
    rep = analyze(deck)
    own = store.owned()
    out = [f"{len(rows)} cards; avg cost {rep.avg_cost}; total power {rep.total_power}",
           "Valid deck" if not rep.errors and not problems else "NOT a valid deck:"]
    out += [f"  ! {e}" for e in rep.errors + problems]
    out.append("Curve: " + "  ".join(f"{c if c < 6 else '6+'}:{n}" for c, n in rep.curve.items()))
    tags = Counter(t for c in deck.cards for t in c.tags if t not in ("zoo", "vanilla", "location"))
    out.append("Themes: " + ", ".join(f"{t} ×{n}" for t, n in tags.most_common(8)))
    kws = Counter(k for r in rows for k in json.loads(r["extra"]).get("keywords") or [])
    if kws:
        out.append("Keywords: " + ", ".join(f"{k} ×{n}" for k, n in kws.most_common()))
    out += [f"  * {w}" for w in rep.warnings]

    ids = {r["def_id"] for r in rows}
    made = [(r["name"], l["name"]) for r in rows for l in store.links_from(r["def_id"]) if l["type"] == "creates"]
    if made:
        out.append("Creates during the game: " + "; ".join(f"{a} → {b}" for a, b in made))
    refs = [(r["card_name"], r["relation"], r["pool_name"]) for i in ids for r in store.pool_refs(def_id=i)]
    if refs:
        out.append("Pools: " + "; ".join(f"{c} {rel} {p}" for c, rel, p in refs))
    if own:
        missing = [r["name"] for r in rows if not own.get(r["def_id"])]
        out.append("You own all of these." if not missing else f"Not owned ({len(missing)}): {', '.join(missing)}")
    out.append("Cards:")
    out += ["  " + card_line(r) for r in sorted(rows, key=lambda r: (r["cost"], r["name"]))]
    return "\n".join(out)


def suggest_for_deck(store: Store, cards: list[str], limit: int = 10, owned: str = "any") -> str:
    rows, _ = _deck_cards(store, cards)
    pool = CardPool.from_db(store.path)
    own = store.owned()
    if owned in ("owned", "unowned"):
        want = owned == "owned"
        pool = CardPool([c for c in pool if bool(own.get(c.def_id)) == want], pool.source)
    picks = suggest(Deck("deck", [_to_card(r) for r in rows]), pool, limit=limit)
    if not picks:
        return "No suggestions."
    return "\n".join(f"{score:>5}  [{c.cost}/{c.power}] {c.name}: {c.ability}"
                     + ((" ✓owned" if own.get(c.def_id) else " ✗not owned") if own else "")
                     for c, score in picks)


def save_deck(store: Store, name: str, cards: list[str], notes: str | None = None) -> str:
    rows, problems = _deck_cards(store, cards)
    store.save_deck(name, [r["def_id"] for r in rows], notes)
    msg = f"Saved deck {name!r} ({len(rows)} cards)."
    return msg + ("\n" + "\n".join(f"  ! {p}" for p in problems) if problems else "")


def list_decks(store: Store) -> str:
    rows = store.decks()
    if not rows:
        return "No saved decks."
    return "\n".join(f"{d['name']}  ({len(json.loads(d['cards']))} cards, updated {d['updated'][:10]})"
                     + (f" — {d['notes']}" if d["notes"] else "") for d in rows)


def show_deck(store: Store, name: str) -> str:
    d = store.deck(name)
    if d is None:
        raise NotFound(f"No saved deck {name!r}.")
    head = f"Deck: {d['name']}" + (f"\nNotes: {d['notes']}" if d["notes"] else "")
    return head + "\n" + analyze_deck(store, json.loads(d["cards"]))


# --- collection ------------------------------------------------------------

def set_owned(store: Store, cards: list[str], owned: bool = True) -> str:
    ok, problems = [], []
    for n in cards:
        try:
            r = resolve(store, n)
            ok.append(r)
        except NotFound as e:
            problems.append(str(e))
    store.set_owned([r["def_id"] for r in ok], owned)
    msg = f"Marked {len(ok)} card(s) as {'owned' if owned else 'not owned'}: {', '.join(r['name'] for r in ok)}"
    return msg + ("\n" + "\n".join(f"  ! {p}" for p in problems) if problems else "")


def collection_summary(store: Store) -> str:
    own = store.owned()
    rows = list(store.db.execute(f"SELECT * FROM entities WHERE {DECK_BUILDABLE}"))
    have = [r for r in rows if own.get(r["def_id"])]
    if not own:
        return (f"No collection recorded yet ({len(rows)} deck-buildable cards exist). "
                "Use set_owned to record cards you own.")
    by_series = Counter(json.loads(r["extra"]).get("series") or "?" for r in rows if not own.get(r["def_id"]))
    return (f"You own {len(have)} of {len(rows)} deck-buildable cards.\n"
            "Not owned by collection series: " + ", ".join(f"{s}: {n}" for s, n in sorted(by_series.items())))


# --- evals -----------------------------------------------------------------

def eval_questions() -> list[dict]:
    from importlib import resources

    return json.loads(resources.files("snap_assistant.knowledge").joinpath("evals.json").read_text())["questions"]


def check_evals(store: Store) -> str:
    """Flag eval questions whose card-text or stat assumptions a patch has broken."""
    out, stale = [], 0
    for q in eval_questions():
        problems = []
        for name, phrase in q.get("assumes", {}).items():
            try:
                r = resolve(store, name)
            except NotFound:
                problems.append(f"{name} not found")
                continue
            if phrase.lower() not in (r["text"] or "").lower():
                problems.append(f"{name} text no longer says {phrase!r} (now: {r['text']!r})")
        for name, stats in q.get("check_stats", {}).items():
            try:
                r = resolve(store, name)
            except NotFound:
                continue
            for stat, want in stats.items():
                if r[stat] != want:
                    problems.append(f"{name} {stat} is {r[stat]}, question assumes {want}")
        for section in q.get("rules", []):
            if not any(s.title == section for s in knowledge.sections()):
                problems.append(f"rules section {section!r} missing")
        stale += bool(problems)
        out.append(f"{'STALE' if problems else 'ok   '}  {q['id']}: {q['question']}")
        out += [f"         ! {p}" for p in problems]
    return f"{len(eval_questions())} questions, {stale} need updating\n" + "\n".join(out)
