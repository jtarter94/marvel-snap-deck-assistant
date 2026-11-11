"""SQLite storage for accepted card/location data, its history and sync runs."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .reconcile import Decision, Prior

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
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_changed TEXT NOT NULL,
    PRIMARY KEY (kind, def_id)
);
CREATE INDEX IF NOT EXISTS entities_name ON entities (kind, name COLLATE NOCASE);

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
                extra=json.loads(r["extra"]),
            )
        return out

    def entities(self, kind: str, released_only: bool = False, include_tokens: bool = True):
        sql = "SELECT * FROM entities WHERE kind = ?"
        if released_only:
            sql += " AND released = 1"
        if not include_tokens:
            sql += " AND is_token = 0"
        if kind == "card" and not include_tokens:
            # Game-mode Skills/Augments/Trinkets aren't deck-buildable.
            sql += (" AND COALESCE(json_extract(extra, '$.card_type'), 'Character') = 'Character'"
                    " AND COALESCE(json_extract(extra, '$.collectible'), 1) = 1")
        return list(self.db.execute(sql + " ORDER BY name COLLATE NOCASE", (kind,)))

    def find(self, kind: str, name_or_id: str):
        return self.db.execute(
            "SELECT * FROM entities WHERE kind = ? AND (name = ? COLLATE NOCASE OR def_id = ? COLLATE NOCASE)"
            " ORDER BY released DESC, is_token ASC LIMIT 1",
            (kind, name_or_id, name_or_id),
        ).fetchone()

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

    def apply(self, run_id: int, decisions: list[Decision]):
        """Write decisions in one transaction."""
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
                           tags, status, confirmed_fields, sources, extra, first_seen, last_seen, last_changed)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT (kind, def_id) DO UPDATE SET
                           name=excluded.name, cost=excluded.cost, power=excluded.power, text=excluded.text,
                           released=excluded.released, is_token=excluded.is_token, tags=excluded.tags,
                           status=excluded.status, confirmed_fields=excluded.confirmed_fields,
                           sources=excluded.sources, extra=excluded.extra,
                           last_seen=CASE WHEN ? THEN excluded.last_seen ELSE entities.last_seen END,
                           last_changed=CASE WHEN ? THEN excluded.last_changed ELSE entities.last_changed END""",
                    (d.kind, d.def_id, v.get("name"), v.get("cost"), v.get("power"), v.get("text"),
                     int(d.released), int(bool(d.extra.get("is_token"))), json.dumps(d.tags), d.status,
                     json.dumps(sorted(d.confirmed_fields)), json.dumps(sorted(d.sources)),
                     json.dumps(d.extra, sort_keys=True), ts, ts, ts,
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

    def _hist(self, run_id, d, field, old, new, how, patch, sources, ts):
        self.db.execute(
            "INSERT INTO history (run_id, kind, def_id, field, old, new, how, patch, sources, at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, d.kind, d.def_id, field, None if old is None else str(old),
             None if new is None else str(new), how, patch, json.dumps(sources), ts),
        )
