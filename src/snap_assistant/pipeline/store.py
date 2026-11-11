"""SQLite storage for accepted card/location data, its history and sync runs."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

from .reconcile import Decision, Prior

if TYPE_CHECKING:
    from .links import Graph

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    kind TEXT NOT NULL,
    def_id TEXT NOT NULL,
    name TEXT,
    cost INTEGER,
    power INTEGER,
    text TEXT,
    released INTEGER NOT NULL DEFAULT 0,
    is_token INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    confirmed_fields TEXT NOT NULL DEFAULT '[]',
    sources TEXT NOT NULL DEFAULT '[]',
    extra TEXT NOT NULL DEFAULT '{}',
    release_date TEXT,
    card_type TEXT,               -- Character | Skill | Augment | Trinket (cards only)
    collectible INTEGER,          -- 0 for game-mode versions / created cards
    category TEXT,                -- marvelsnap.pro's grouping, when it has one
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_changed TEXT NOT NULL,
    PRIMARY KEY (kind, def_id)
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    kind TEXT NOT NULL,
    def_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT,
    how TEXT NOT NULL,
    patch TEXT,
    sources TEXT NOT NULL DEFAULT '[]',
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_entity ON history (kind, def_id);

-- Card graph, rebuilt every sync from the accepted data (see pipeline/links.py).
CREATE TABLE IF NOT EXISTS card_links (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    type TEXT NOT NULL,          -- creates | version_of | related | transforms_into ...
    origin TEXT NOT NULL,        -- source | inferred | manual
    PRIMARY KEY (from_id, to_id, type)
);
CREATE TABLE IF NOT EXISTS pools (
    pool_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,          -- rule | team | named | manual
    description TEXT
);
CREATE TABLE IF NOT EXISTS pool_members (
    pool_id TEXT NOT NULL REFERENCES pools(pool_id),
    def_id TEXT NOT NULL,
    PRIMARY KEY (pool_id, def_id)
);
CREATE TABLE IF NOT EXISTS pool_refs (
    def_id TEXT NOT NULL,
    pool_id TEXT NOT NULL REFERENCES pools(pool_id),
    relation TEXT NOT NULL,      -- generates | references
    origin TEXT NOT NULL,
    PRIMARY KEY (def_id, pool_id, relation)
);

-- Open issues as of the latest run (conflicts and held changes); replaced each run.
CREATE TABLE IF NOT EXISTS issues (
    kind TEXT NOT NULL,
    def_id TEXT NOT NULL,
    field TEXT NOT NULL,
    type TEXT NOT NULL,          -- conflict | held
    source_values TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (kind, def_id, field)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started TEXT NOT NULL,
    finished TEXT,
    status TEXT NOT NULL,        -- running | ok | partial | failed | dry-run
    sources TEXT NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL DEFAULT '{}'
);
"""


INDEXES = """
CREATE INDEX IF NOT EXISTS entities_name ON entities (kind, name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS entities_release ON entities (kind, release_date);
CREATE INDEX IF NOT EXISTS card_links_to ON card_links (to_id, type);
CREATE INDEX IF NOT EXISTS pool_members_card ON pool_members (def_id);
"""


# Keys older versions kept in `extra` that now live in their own tables.
_RETIRED_EXTRA = {"creates", "created_by", "related_cards"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_home() -> Path:
    if env := os.environ.get("SNAP_ASSISTANT_HOME"):
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "snap-assistant"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "snap-assistant"


def default_db_path() -> Path:
    return default_home() / "snap.db"


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Bring databases created by older versions up to date."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(entities)")}
        for col, typ in (("release_date", "TEXT"), ("card_type", "TEXT"),
                         ("collectible", "INTEGER"), ("category", "TEXT")):
            if col not in cols:
                self.db.execute(f"ALTER TABLE entities ADD COLUMN {col} {typ}")
        self.db.executescript(INDEXES)
        self.db.commit()

    def close(self):
        self.db.close()

    # --- reads -----------------------------------------------------------

    def priors(self) -> dict[tuple[str, str], Prior]:
        out = {}
        for r in self.db.execute("SELECT * FROM entities"):
            out[(r["kind"], r["def_id"])] = Prior(
                values={"name": r["name"], "cost": r["cost"], "power": r["power"], "text": r["text"]},
                released=bool(r["released"]),
                confirmed_fields=set(json.loads(r["confirmed_fields"])),
                sources=set(json.loads(r["sources"])),
                extra={k: v for k, v in json.loads(r["extra"]).items() if k not in _RETIRED_EXTRA},
            )
        return out

    def name_of(self, kind: str, def_id: str) -> str:
        r = self.db.execute("SELECT name FROM entities WHERE kind = ? AND def_id = ?", (kind, def_id)).fetchone()
        return r["name"] if r and r["name"] else def_id

    def entities(self, kind: str, released_only: bool = False, include_tokens: bool = True):
        sql = "SELECT * FROM entities WHERE kind = ?"
        if released_only:
            sql += " AND released = 1"
        if not include_tokens:
            sql += " AND is_token = 0"
        if kind == "card" and not include_tokens:
            # Game-mode Skills/Augments/Trinkets and game-mode versions aren't deck-buildable.
            sql += " AND COALESCE(card_type, 'Character') = 'Character' AND COALESCE(collectible, 1) = 1"
        return list(self.db.execute(sql + " ORDER BY name COLLATE NOCASE", (kind,)))

    def find(self, kind: str, name_or_id: str):
        return self.db.execute(
            "SELECT * FROM entities WHERE kind = ? AND (name = ? COLLATE NOCASE OR def_id = ? COLLATE NOCASE)"
            " ORDER BY released DESC, is_token ASC LIMIT 1",
            (kind, name_or_id, name_or_id),
        ).fetchone()

    def links_from(self, def_id: str):
        return list(self.db.execute(
            "SELECT l.*, e.name FROM card_links l LEFT JOIN entities e ON e.kind = 'card' AND e.def_id = l.to_id"
            " WHERE l.from_id = ? ORDER BY l.type, e.name", (def_id,)))

    def links_to(self, def_id: str):
        return list(self.db.execute(
            "SELECT l.*, e.name FROM card_links l LEFT JOIN entities e ON e.kind = 'card' AND e.def_id = l.from_id"
            " WHERE l.to_id = ? ORDER BY l.type, e.name", (def_id,)))

    def pools(self):
        return list(self.db.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM pool_members m WHERE m.pool_id = p.pool_id) AS size"
            " FROM pools p ORDER BY p.kind, p.name"))

    def pool(self, pool_id_or_name: str):
        return self.db.execute(
            "SELECT * FROM pools WHERE pool_id = ? COLLATE NOCASE OR name = ? COLLATE NOCASE",
            (pool_id_or_name, pool_id_or_name)).fetchone()

    def pool_members(self, pool_id: str):
        return list(self.db.execute(
            "SELECT e.* FROM pool_members m JOIN entities e ON e.kind = 'card' AND e.def_id = m.def_id"
            " WHERE m.pool_id = ? ORDER BY e.cost, e.name", (pool_id,)))

    def pool_refs(self, *, def_id: str | None = None, pool_id: str | None = None):
        sql = ("SELECT r.*, p.name AS pool_name, e.name AS card_name FROM pool_refs r"
               " JOIN pools p USING (pool_id)"
               " LEFT JOIN entities e ON e.kind = 'card' AND e.def_id = r.def_id WHERE 1=1")
        args = []
        if def_id:
            sql += " AND r.def_id = ?"
            args.append(def_id)
        if pool_id:
            sql += " AND r.pool_id = ?"
            args.append(pool_id)
        return list(self.db.execute(sql + " ORDER BY r.relation, p.name, e.name", args))

    def pools_containing(self, def_id: str):
        return list(self.db.execute(
            "SELECT p.* FROM pool_members m JOIN pools p USING (pool_id) WHERE m.def_id = ? ORDER BY p.name",
            (def_id,)))

    def history(self, kind: str, def_id: str):
        return list(self.db.execute(
            "SELECT * FROM history WHERE kind = ? AND def_id = ? ORDER BY id", (kind, def_id)))

    def issues(self):
        return list(self.db.execute(
            "SELECT i.*, e.name FROM issues i LEFT JOIN entities e USING (kind, def_id)"
            " ORDER BY i.type, e.name"))

    def last_run(self, status: tuple[str, ...] = ("ok", "partial")):
        q = ",".join("?" * len(status))
        return self.db.execute(
            f"SELECT * FROM runs WHERE status IN ({q}) ORDER BY id DESC LIMIT 1", status
        ).fetchone()

    def has_data(self) -> bool:
        return self.db.execute("SELECT 1 FROM entities WHERE kind = 'card' LIMIT 1").fetchone() is not None

    # --- writes ----------------------------------------------------------

    def start_run(self) -> int:
        cur = self.db.execute("INSERT INTO runs (started, status) VALUES (?, 'running')", (now(),))
        self.db.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, sources: dict, summary: dict):
        self.db.execute(
            "UPDATE runs SET finished = ?, status = ?, sources = ?, summary = ? WHERE id = ?",
            (now(), status, json.dumps(sources), json.dumps(summary), run_id),
        )
        self.db.commit()

    def apply(self, run_id: int, decisions: list[Decision], graph: "Graph | None" = None):
        """Write decisions (and the rebuilt card graph) in one transaction."""
        ts = now()
        with self.db:
            old_issues = {
                (r["kind"], r["def_id"], r["field"]): r["first_seen"]
                for r in self.db.execute("SELECT kind, def_id, field, first_seen FROM issues")
            }
            self.db.execute("DELETE FROM issues")
            for d in decisions:
                v = d.values
                changed = d.touched
                self.db.execute(
                    """INSERT INTO entities (kind, def_id, name, cost, power, text, released, is_token,
                           tags, status, confirmed_fields, sources, extra, release_date,
                           card_type, collectible, category, first_seen, last_seen, last_changed)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT (kind, def_id) DO UPDATE SET
                           release_date=excluded.release_date, card_type=excluded.card_type,
                           collectible=excluded.collectible, category=excluded.category,
                           name=excluded.name, cost=excluded.cost, power=excluded.power, text=excluded.text,
                           released=excluded.released, is_token=excluded.is_token, tags=excluded.tags,
                           status=excluded.status, confirmed_fields=excluded.confirmed_fields,
                           sources=excluded.sources, extra=excluded.extra,
                           last_seen=CASE WHEN ? THEN excluded.last_seen ELSE entities.last_seen END,
                           last_changed=CASE WHEN ? THEN excluded.last_changed ELSE entities.last_changed END""",
                    (d.kind, d.def_id, v.get("name"), v.get("cost"), v.get("power"), v.get("text"),
                     int(d.released), int(bool(d.extra.get("is_token"))), json.dumps(d.tags), d.status,
                     json.dumps(sorted(d.confirmed_fields)), json.dumps(sorted(d.sources)),
                     json.dumps(d.extra, sort_keys=True), d.extra.get("release_date"),
                     d.extra.get("card_type") if d.kind == "card" else None,
                     None if d.extra.get("collectible") is None else int(d.extra["collectible"]),
                     d.extra.get("category"), ts, ts, ts,
                     int(not d.missing_from), int(changed)),
                )
                patch = d.extra.get("patch")
                if d.is_new:
                    self._hist(run_id, d, "*", None, json.dumps(v, sort_keys=True), "new", patch, sorted(d.sources), ts)
                for c in d.changes:
                    self._hist(run_id, d, c.field, c.old, c.new, c.how, patch, c.sources, ts)
                for kind_, issues in (("conflict", d.conflicts), ("held", d.held)):
                    for f, vals in issues.items():
                        first = old_issues.get((d.kind, d.def_id, f), ts)
                        self.db.execute(
                            "INSERT INTO issues VALUES (?,?,?,?,?,?,?)",
                            (d.kind, d.def_id, f, kind_, json.dumps(vals), first, ts),
                        )

            if graph is not None:
                self._write_graph(graph)

    def _write_graph(self, g: "Graph"):
        for table in ("pool_refs", "pool_members", "pools", "card_links"):
            self.db.execute(f"DELETE FROM {table}")
        self.db.executemany("INSERT INTO card_links VALUES (?,?,?,?)",
                            [(a, b, t, o) for (a, b, t), o in g.links.items()])
        self.db.executemany("INSERT INTO pools VALUES (?,?,?,?)",
                            [(p.pool_id, p.name, p.kind, p.description) for p in g.pools.values()])
        self.db.executemany("INSERT INTO pool_members VALUES (?,?)",
                            [(p.pool_id, m) for p in g.pools.values() for m in sorted(p.members)])
        self.db.executemany("INSERT INTO pool_refs VALUES (?,?,?,?)",
                            [(c, p, r, o) for (c, p, r), o in g.refs.items() if p in g.pools])

    def _hist(self, run_id, d, field, old, new, how, patch, sources, ts):
        self.db.execute(
            "INSERT INTO history (run_id, kind, def_id, field, old, new, how, patch, sources, at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, d.kind, d.def_id, field, None if old is None else str(old),
             None if new is None else str(new), how, patch, json.dumps(sources), ts),
        )
